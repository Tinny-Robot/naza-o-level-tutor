"""Isolated llama.cpp memory, speed, and answer-quality benchmark.

Each configuration runs in a fresh subprocess so VmHWM and llama.cpp state do
not leak between experiments. Production defaults and application code are not
modified. The full evaluation set is used by default; ``--limit`` provides a
deterministic, evenly-spaced pilot drawn from the same ``data/eval/qa.json``.

Examples:

    .venv/bin/python scripts/benchmark_inference.py --config baseline
    .venv/bin/python scripts/benchmark_inference.py --config all --limit 4
    .venv/bin/python scripts/benchmark_inference.py --config best --limit 4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MethodType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import (  # noqa: E402
    CONTEXT_LENGTH,
    FLASH_ATTN,
    MAX_CONTEXT_TOKENS,
    MAX_TOKENS,
    MODEL_NAME,
    MODEL_PATH,
    QA_PATH,
    SWA_FULL,
    TEMPERATURE,
    THREADS,
    TOP_K,
)
from app.generation.llm import LlamaCppLLM, strip_reasoning  # noqa: E402
from app.generation.pipeline import GenerationPipeline  # noqa: E402
from app.generation.prompt_manager import get_prompt_manager  # noqa: E402
from app.generation.rag import RetrievalService  # noqa: E402
from app.ingestion.embedder import get_embedder  # noqa: E402
from app.retrieval.search import get_retriever  # noqa: E402
from app.utils.offline import enable_offline_mode, run_self_check  # noqa: E402

BENCHMARK_DIR = PROJECT_ROOT / "data" / "benchmarks"
COMPETITION_LIMIT_MIB = 7 * 1024
DETERMINISTIC_SEED = 2026
DEFAULT_SAMPLE_INTERVAL_S = 0.05


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    description: str
    n_ctx: int
    use_mmap: bool
    use_mlock: bool
    type_k: str
    type_v: str
    n_batch: int = 512
    n_ubatch: int = 512


def _configs() -> dict[str, ExperimentConfig]:
    base = {
        "n_ctx": CONTEXT_LENGTH,
        "use_mmap": True,
        "use_mlock": False,
        "type_k": "F16",
        "type_v": "F16",
    }
    return {
        "baseline": ExperimentConfig(
            name="baseline",
            description="Current production llama.cpp defaults made explicit",
            **base,
        ),
        "mmap": ExperimentConfig(
            name="mmap",
            description="Mmap enabled and mlock disabled; identical to current production",
            **base,
        ),
        "mmap_kv": ExperimentConfig(
            name="mmap_kv",
            description="Mmap with Q8_0 K/V cache",
            **{**base, "type_k": "Q8_0", "type_v": "Q8_0"},
        ),
        "mmap_kv_q4": ExperimentConfig(
            name="mmap_kv_q4",
            description="Mmap with aggressive Q4_0 K/V cache",
            **{**base, "type_k": "Q4_0", "type_v": "Q4_0"},
        ),
        "mmap_context_4096": ExperimentConfig(
            name="mmap_context_4096",
            description="Mmap with F16 KV and controlled 4096 context",
            **base,
        ),
        "mmap_context_3072": ExperimentConfig(
            name="mmap_context_3072",
            description="Mmap with F16 KV and controlled 3072 context",
            **{**base, "n_ctx": 3072},
        ),
        "mmap_context_2048": ExperimentConfig(
            name="mmap_context_2048",
            description="Mmap with F16 KV and controlled 2048 context",
            **{**base, "n_ctx": 2048},
        ),
    }


def _status_memory() -> dict[str, float]:
    values: dict[str, float] = {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                key, raw, _unit = line.split()[:3]
                values[key.rstrip(":").lower() + "_mib"] = int(raw) / 1024.0
    except OSError:
        pass
    return values


class MemorySampler:
    def __init__(self, interval_s: float = DEFAULT_SAMPLE_INTERVAL_S) -> None:
        self.interval_s = interval_s
        self.samples_mib: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            rss = _status_memory().get("vmrss_mib")
            if rss is not None:
                self.samples_mib.append(rss)
            self._stop.wait(self.interval_s)

    def __enter__(self) -> MemorySampler:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def summary(self) -> dict[str, float | None]:
        if not self.samples_mib:
            return {"average_rss_mib": None, "sampled_peak_rss_mib": None}
        return {
            "average_rss_mib": statistics.fmean(self.samples_mib),
            "sampled_peak_rss_mib": max(self.samples_mib),
        }


def _ggml_type(name: str) -> int:
    import llama_cpp

    attr = f"GGML_TYPE_{name.upper()}"
    if not hasattr(llama_cpp, attr):
        raise ValueError(f"Installed llama_cpp does not expose {attr}")
    return int(getattr(llama_cpp, attr))


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _keyword_score(answer: str, keywords: list[str]) -> float:
    clean_keywords = [_normalise(str(keyword)) for keyword in keywords]
    clean_keywords = [keyword for keyword in clean_keywords if keyword]
    if not clean_keywords:
        return 0.0
    normalised_answer = _normalise(answer)
    return sum(keyword in normalised_answer for keyword in clean_keywords) / len(
        clean_keywords
    )


def _label_relevances(
    results: list[dict[str, Any]], *, subject: str, expected_keywords: list[str]
) -> list[bool]:
    """Mirror the project's retrieval relevance rule without importing its broken loader."""
    expected_subject = (subject or "").strip().lower()
    keywords = [str(keyword).strip().lower() for keyword in expected_keywords if str(keyword).strip()]
    labels: list[bool] = []
    for result in results:
        metadata = result.get("metadata") or {}
        document_subject = str(metadata.get("subject") or "").strip().lower()
        haystack = " ".join(
            [
                str(result.get("text") or ""),
                str(metadata.get("topic") or ""),
                document_subject,
            ]
        ).lower()
        keyword_hit = any(keyword in haystack for keyword in keywords)
        subject_hit = bool(expected_subject) and document_subject == expected_subject
        labels.append((subject_hit and (not keywords or keyword_hit)) or keyword_hit)
    return labels


def _load_items(limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = QA_PATH.read_bytes()
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError(f"Expected a list in {QA_PATH}")
    total = len(items)
    if limit <= 0 or limit >= total:
        selected = items
        method = "full"
    elif limit == 1:
        selected = [items[0]]
        method = "first_item"
    else:
        indexes = [round(index * (total - 1) / (limit - 1)) for index in range(limit)]
        selected = [items[index] for index in indexes]
        method = "evenly_spaced"
    return selected, {
        "dataset_path": str(QA_PATH.relative_to(PROJECT_ROOT)),
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "dataset_total_questions": total,
        "questions_evaluated": len(selected),
        "selection_method": method,
        "selected_ids": [item.get("id") for item in selected],
    }


def _cpu_info() -> dict[str, Any]:
    model = platform.processor()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    mem_total_kib = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_total_kib = int(line.split()[1])
                break
    except OSError:
        pass
    return {
        "cpu_model": model,
        "logical_cpus": os.cpu_count(),
        "benchmark_threads": THREADS,
        "ram_total_gib": mem_total_kib / (1024**2),
        "platform": platform.platform(),
    }


def _llama_info() -> dict[str, Any]:
    import llama_cpp

    version = getattr(llama_cpp, "__version__", "unknown")
    bundled_commits = {"0.3.34": "e3546c794"}
    system_info = ""
    if hasattr(llama_cpp, "llama_print_system_info"):
        system_info = llama_cpp.llama_print_system_info().decode(errors="replace")
    return {
        "llama_cpp_python_version": version,
        "llama_cpp_commit": bundled_commits.get(
            version, "not identified for installed wheel"
        ),
        "llama_system_info": system_info,
    }


def _install_benchmark_init(config: ExperimentConfig) -> Any:
    import app.generation.llm as llm_module
    from llama_cpp import Llama

    original_init = llm_module.LlamaCppLLM.__init__

    def benchmark_init(
        self: LlamaCppLLM,
        *,
        model_path: str | Path | None = None,
        n_ctx: int = config.n_ctx,
        n_threads: int = THREADS,
        temperature: float = TEMPERATURE,
        max_tokens: int = MAX_TOKENS,
        model_name: str = MODEL_NAME,
        flash_attn: bool = FLASH_ATTN,
        swa_full: bool = SWA_FULL,
    ) -> None:
        path = MODEL_PATH if model_path is None else Path(model_path)
        kwargs = {
            "model_path": str(path),
            "n_ctx": n_ctx,
            "n_threads": n_threads,
            "n_threads_batch": n_threads,
            "n_gpu_layers": 0,
            "n_batch": config.n_batch,
            "n_ubatch": config.n_ubatch,
            "use_mmap": config.use_mmap,
            "use_mlock": config.use_mlock,
            "flash_attn": flash_attn,
            "swa_full": swa_full,
            "type_k": _ggml_type(config.type_k),
            "type_v": _ggml_type(config.type_v),
            "verbose": False,
        }
        self._llama = Llama(**kwargs)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.last_gen_tokens = 0
        self.llama_kwargs = dict(kwargs)

    llm_module.LlamaCppLLM.__init__ = benchmark_init
    return original_init


def _instrument_generation(llm: LlamaCppLLM, measurements: list[dict[str, Any]]) -> None:
    import llama_cpp

    def measured_generate(self: LlamaCppLLM, system: str, user: str) -> str:
        llama_cpp.llama_perf_context_reset(self._llama._ctx.ctx)
        start = time.perf_counter()
        first_token_at: float | None = None
        pieces: list[str] = []
        stream = self._llama.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=DETERMINISTIC_SEED,
            stream=True,
        )
        for chunk in stream:
            choices = chunk.get("choices") or []
            if not choices:
                continue
            content = (choices[0].get("delta") or {}).get("content")
            if content:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                pieces.append(content)
        finished = time.perf_counter()
        raw_answer = "".join(pieces)
        answer = strip_reasoning(raw_answer)
        perf = llama_cpp.llama_perf_context(self._llama._ctx.ctx)
        generated_tokens = int(perf.n_eval) or self.count_tokens(raw_answer)
        self.last_gen_tokens = generated_tokens
        prompt_s = float(perf.t_p_eval_ms) / 1000.0
        generation_s = float(perf.t_eval_ms) / 1000.0
        measurements.append(
            {
                "prompt_tokens": int(perf.n_p_eval),
                "generated_tokens": generated_tokens,
                "prompt_seconds": prompt_s,
                "generation_seconds": generation_s,
                "prompt_tokens_per_second": (
                    int(perf.n_p_eval) / prompt_s if prompt_s > 0 else None
                ),
                "generation_tokens_per_second": (
                    generated_tokens / generation_s if generation_s > 0 else None
                ),
                "time_to_first_token_seconds": (
                    first_token_at - start if first_token_at is not None else None
                ),
                "total_latency_seconds": finished - start,
                "perf_reused_graphs": int(perf.n_reused),
            }
        )
        if not answer:
            raise RuntimeError("Empty completion in benchmark")
        return answer

    llm.generate = MethodType(measured_generate, llm)


def _disable_student_writes() -> None:
    try:
        from app.student.updater import LearningProfileUpdater

        LearningProfileUpdater.apply_event = lambda self, event: None
    except Exception:
        pass


def _summary_stats(values: list[float | None]) -> dict[str, float | None]:
    valid = [float(value) for value in values if value is not None and math.isfinite(value)]
    if not valid:
        return {"average": None, "median": None, "minimum": None, "maximum": None}
    return {
        "average": statistics.fmean(valid),
        "median": statistics.median(valid),
        "minimum": min(valid),
        "maximum": max(valid),
    }


def _run_worker(config: ExperimentConfig, limit: int) -> dict[str, Any]:
    enable_offline_mode()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    _disable_student_writes()
    check = run_self_check()
    if not check.ok:
        raise RuntimeError("Startup self-check failed: " + "; ".join(check.format_lines()))

    items, dataset = _load_items(limit)
    stage_memory: dict[str, Any] = {"process_start": _status_memory()}
    generation_measurements: list[dict[str, Any]] = []

    original_init = _install_benchmark_init(config)
    try:
        with MemorySampler() as memory_sampler:
            prompts = get_prompt_manager()
            embed_start = time.perf_counter()
            embedder = get_embedder()
            _ = embedder.model
            embed_load_s = time.perf_counter() - embed_start
            stage_memory["embedding_loaded"] = _status_memory()

            model_start = time.perf_counter()
            llm = LlamaCppLLM()
            model_load_s = time.perf_counter() - model_start
            stage_memory["model_loaded"] = _status_memory()
            _instrument_generation(llm, generation_measurements)

            retriever_start = time.perf_counter()
            retriever = get_retriever()
            retriever.embedder = embedder
            retriever_load_s = time.perf_counter() - retriever_start
            stage_memory["retriever_loaded"] = _status_memory()
            pipeline = GenerationPipeline(
                retrieval=RetrievalService(retriever=retriever),
                llm=llm,
                prompts=prompts,
                max_context_tokens=MAX_CONTEXT_TOKENS,
            )

            rows: list[dict[str, Any]] = []
            for index, item in enumerate(items):
                before_count = len(generation_measurements)
                started = time.perf_counter()
                error: str | None = None
                try:
                    result = pipeline._ask_study(
                        item["question"],
                        top_k=TOP_K,
                        subject=item.get("subject"),
                        topic=item.get("topic"),
                    )
                    answer = str(result.get("answer") or "")
                except Exception as exc:
                    result = {"citations": [], "retrieved_chunks": [], "refused": True}
                    answer = ""
                    error = f"{type(exc).__name__}: {exc}"
                elapsed = time.perf_counter() - started
                measurement = (
                    generation_measurements[-1]
                    if len(generation_measurements) > before_count
                    else {
                        "prompt_tokens": 0,
                        "generated_tokens": 0,
                        "prompt_seconds": None,
                        "generation_seconds": None,
                        "prompt_tokens_per_second": None,
                        "generation_tokens_per_second": None,
                        "time_to_first_token_seconds": None,
                        "total_latency_seconds": elapsed,
                    }
                )
                retrieved = result.get("retrieved_chunks") or []
                relevances = _label_relevances(
                    retrieved,
                    subject=str(item.get("subject") or ""),
                    expected_keywords=item.get("expected_keywords") or [],
                )
                rows.append(
                    {
                        "index": index,
                        "id": item.get("id"),
                        "subject": item.get("subject"),
                        "topic": item.get("topic"),
                        "question": item.get("question"),
                        "answer": answer,
                        "reference_answer": item.get("answer"),
                        "exact_match": _normalise(answer)
                        == _normalise(str(item.get("answer") or "")),
                        "keyword_score": _keyword_score(
                            answer, item.get("expected_keywords") or []
                        ),
                        "retrieval_hit": any(relevances),
                        "citation_count": len(result.get("citations") or []),
                        "retrieved_chunk_count": len(retrieved),
                        "refused": bool(result.get("refused")),
                        "error": error,
                        **measurement,
                        "rss_after_mib": _status_memory().get("vmrss_mib"),
                        "hwm_after_mib": _status_memory().get("vmhwm_mib"),
                    }
                )
            stage_memory["evaluation_finished"] = _status_memory()
        memory_summary = memory_sampler.summary()
    finally:
        import app.generation.llm as llm_module

        llm_module.LlamaCppLLM.__init__ = original_init

    peak_rss_mib = float(_status_memory().get("vmhwm_mib") or 0.0)
    headroom_mib = COMPETITION_LIMIT_MIB - peak_rss_mib
    failures = sum(1 for row in rows if row["error"])
    keyword_accuracy = statistics.fmean(row["keyword_score"] for row in rows) if rows else 0.0
    exact_match = statistics.fmean(float(row["exact_match"]) for row in rows) if rows else 0.0
    result = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "evaluation_scope": "full" if limit <= 0 else "pilot",
        "config": asdict(config),
        "controls": {
            "model": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
            "model_size_bytes": MODEL_PATH.stat().st_size,
            "quantization": "Q4_K_M (GGUF general.file_type=15)",
            "n_gpu_layers": 0,
            "threads": THREADS,
            "flash_attention": FLASH_ATTN,
            "swa_full": SWA_FULL,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "top_p": 0.95,
            "top_k_sampling": 40,
            "min_p": 0.05,
            "seed": DETERMINISTIC_SEED,
            "rag_top_k": TOP_K,
            "rag_context_budget": MAX_CONTEXT_TOKENS,
            "retrieval_mode": "production default",
        },
        "hardware": _cpu_info(),
        "llama": _llama_info(),
        "dataset": dataset,
        "load_times_seconds": {
            "embedding": embed_load_s,
            "model": model_load_s,
            "retriever": retriever_load_s,
        },
        "memory": {
            "competition_limit_mib": COMPETITION_LIMIT_MIB,
            "peak_rss_mib": peak_rss_mib,
            "peak_rss_gib": peak_rss_mib / 1024.0,
            "ram_headroom_mib": headroom_mib,
            "ram_headroom_gib": headroom_mib / 1024.0,
            "status": (
                "PASS" if peak_rss_mib <= COMPETITION_LIMIT_MIB else "FAIL - ABOVE COMPETITION LIMIT"
            ),
            "stages": stage_memory,
            **memory_summary,
        },
        "quality": {
            "accuracy_metric": "mean expected-keyword recall",
            "accuracy": keyword_accuracy,
            "exact_match": exact_match,
            "retrieval_hit_rate": statistics.fmean(
                float(row["retrieval_hit"]) for row in rows
            )
            if rows
            else 0.0,
            "failures": failures,
        },
        "performance": {
            "generation_tokens_per_second": _summary_stats(
                [row["generation_tokens_per_second"] for row in rows]
            ),
            "prompt_tokens_per_second": _summary_stats(
                [row["prompt_tokens_per_second"] for row in rows]
            ),
            "time_to_first_token_seconds": _summary_stats(
                [row["time_to_first_token_seconds"] for row in rows]
            ),
            "total_latency_seconds": _summary_stats(
                [row["total_latency_seconds"] for row in rows]
            ),
            "prompt_tokens": _summary_stats([row["prompt_tokens"] for row in rows]),
            "generated_tokens": _summary_stats(
                [row["generated_tokens"] for row in rows]
            ),
        },
        "questions": rows,
    }
    return result


def _format(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _write_report(result: dict[str, Any], path: Path) -> None:
    config = result["config"]
    memory = result["memory"]
    quality = result["quality"]
    performance = result["performance"]
    lines = [
        f"# Inference benchmark: {config['name']}",
        "",
        f"- Scope: **{result['evaluation_scope']}** ({result['dataset']['questions_evaluated']} of "
        f"{result['dataset']['dataset_total_questions']} questions)",
        f"- Configuration: {config['description']}",
        f"- Accuracy (mean expected-keyword recall): {_format(quality['accuracy'])}",
        f"- Exact match: {_format(quality['exact_match'])}",
        f"- Peak RSS: {_format(memory['peak_rss_gib'])} GiB",
        f"- RAM headroom against 7 GiB: {_format(memory['ram_headroom_gib'])} GiB",
        f"- Status: **{memory['status']}**",
        f"- Average generation speed: {_format(performance['generation_tokens_per_second']['average'])} tok/s",
        f"- Average prompt speed: {_format(performance['prompt_tokens_per_second']['average'])} tok/s",
        f"- Average TTFT: {_format(performance['time_to_first_token_seconds']['average'])} s",
        f"- Average latency: {_format(performance['total_latency_seconds']['average'])} s",
        f"- Model load time: {_format(result['load_times_seconds']['model'])} s",
        "",
        "## Configuration",
        "",
        "```json",
        json.dumps(config, indent=2),
        "```",
        "",
        "## Per-question results",
        "",
        "| ID | Accuracy | Gen tok/s | Prompt tok/s | TTFT | Latency | Error |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["questions"]:
        lines.append(
            f"| {row['id']} | {_format(row['keyword_score'])} | "
            f"{_format(row['generation_tokens_per_second'])} | "
            f"{_format(row['prompt_tokens_per_second'])} | "
            f"{_format(row['time_to_first_token_seconds'])} | "
            f"{_format(row['total_latency_seconds'])} | {row['error'] or ''} |"
        )
    path.write_text("\n".join(lines) + "\n")


def _run_subprocess(name: str, limit: int, best_ctx: int | None = None, best_kv: str | None = None) -> int:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--config",
        name,
        "--limit",
        str(limit),
    ]
    if best_ctx is not None:
        command += ["--best-context", str(best_ctx)]
    if best_kv is not None:
        command += ["--best-kv", best_kv]
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


def _load_result(name: str) -> dict[str, Any] | None:
    path = BENCHMARK_DIR / f"{name}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _tradeoff_score(result: dict[str, Any]) -> float:
    if result["quality"]["failures"]:
        return -1.0
    accuracy = float(result["quality"]["accuracy"])
    speed = float(
        result["performance"]["generation_tokens_per_second"]["average"] or 0.0
    )
    peak = float(result["memory"]["peak_rss_mib"])
    efficiency = max(0.0, min(1.0, (COMPETITION_LIMIT_MIB - peak) / COMPETITION_LIMIT_MIB))
    return 50.0 * accuracy + 30.0 * speed + 20.0 * efficiency


def _write_summary(names: list[str]) -> None:
    results = [result for name in names if (result := _load_result(name))]
    if not results:
        return
    max_speed = max(
        float(result["performance"]["generation_tokens_per_second"]["average"] or 0.0)
        for result in results
    ) or 1.0
    baseline = next((result for result in results if result["config"]["name"] == "baseline"), results[0])
    table_rows: list[str] = []
    comparisons: dict[str, Any] = {}
    for result in results:
        accuracy = float(result["quality"]["accuracy"])
        peak = float(result["memory"]["peak_rss_mib"])
        speed = float(result["performance"]["generation_tokens_per_second"]["average"] or 0.0)
        efficiency = max(0.0, min(1.0, (COMPETITION_LIMIT_MIB - peak) / COMPETITION_LIMIT_MIB))
        adtc = 50 * accuracy + 30 * (speed / max_speed) + 20 * efficiency
        table_rows.append(
            f"| {result['config']['name']} | {_format(accuracy)} | "
            f"{_format(peak / 1024)} GiB | {_format(result['memory']['ram_headroom_gib'])} GiB | "
            f"{_format(speed)} | {_format(result['performance']['prompt_tokens_per_second']['average'])} | "
            f"{_format(result['performance']['time_to_first_token_seconds']['average'])} s | "
            f"{_format(result['performance']['total_latency_seconds']['average'])} s | "
            f"{_format(adtc)} | {result['memory']['status']} |"
        )
        comparisons[result["config"]["name"]] = {
            "ram_reduction_percent": (
                (baseline["memory"]["peak_rss_mib"] - peak)
                / baseline["memory"]["peak_rss_mib"]
                * 100
            ),
            "speed_change_percent": (
                (speed - (baseline["performance"]["generation_tokens_per_second"]["average"] or 0.0))
                / (baseline["performance"]["generation_tokens_per_second"]["average"] or 1.0)
                * 100
            ),
            "accuracy_change_percent_points": (
                accuracy - baseline["quality"]["accuracy"]
            )
            * 100,
            "adtc_oriented_score": adtc,
        }
    summary = {
        "schema_version": 1,
        "evaluation_scope": results[0]["evaluation_scope"],
        "configurations": [result["config"]["name"] for result in results],
        "relative_to_baseline": comparisons,
    }
    (BENCHMARK_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# ADTC inference optimization comparison",
        "",
        f"Scope: **{results[0]['evaluation_scope']}**, "
        f"{results[0]['dataset']['questions_evaluated']} questions from the unchanged evaluation file.",
        "",
        "| Configuration | Accuracy | Peak RSS | RAM Headroom | Gen tok/s | Prompt tok/s | TTFT | Avg Latency | ADTC score | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        *table_rows,
        "",
        "The ADTC-oriented score uses 50% keyword accuracy, 30% speed normalized to the fastest measured configuration, and 20% positive headroom under 7 GiB.",
    ]
    (BENCHMARK_DIR / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    configs = _configs()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="baseline", choices=[*configs, "best", "all"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--best-context", type=int, default=2048, help=argparse.SUPPRESS)
    parser.add_argument("--best-kv", choices=["Q8_0", "Q4_0"], default="Q8_0", help=argparse.SUPPRESS)
    args = parser.parse_args()
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

    if args.worker:
        if args.config == "best":
            config = ExperimentConfig(
                name="best",
                description="Measured best combined mmap, quantized KV, and controlled context",
                n_ctx=args.best_context,
                use_mmap=True,
                use_mlock=False,
                type_k=args.best_kv,
                type_v=args.best_kv,
            )
        else:
            config = configs[args.config]
        try:
            result = _run_worker(config, args.limit)
        except Exception as exc:
            failure = {
                "schema_version": 1,
                "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "evaluation_scope": "full" if args.limit <= 0 else "pilot",
                "config": asdict(config),
                "error": f"{type(exc).__name__}: {exc}",
                "memory": {**_status_memory(), "status": "FAILED EXPERIMENT"},
            }
            (BENCHMARK_DIR / f"{config.name}.json").write_text(
                json.dumps(failure, indent=2) + "\n"
            )
            print(f"{config.name}: {failure['error']}", file=sys.stderr)
            raise
        output = BENCHMARK_DIR / f"{config.name}.json"
        output.write_text(json.dumps(result, indent=2) + "\n")
        _write_report(result, BENCHMARK_DIR / f"{config.name}.md")
        generation_speed = result["performance"]["generation_tokens_per_second"][
            "average"
        ]
        print(
            f"{config.name}: accuracy={result['quality']['accuracy']:.3f} "
            f"peak={result['memory']['peak_rss_gib']:.3f} GiB "
            f"gen={_format(generation_speed)} tok/s "
            f"status={result['memory']['status']}"
        )
        return

    if args.config == "all":
        names = list(configs)
        for name in names:
            if _run_subprocess(name, args.limit) != 0:
                print(f"Experiment {name} failed; continuing.", file=sys.stderr)
        candidates = [
            result
            for name in ["mmap_kv", "mmap_kv_q4"]
            if (result := _load_result(name)) and "quality" in result
        ]
        best_kv = max(candidates, key=_tradeoff_score)["config"]["type_k"] if candidates else "Q8_0"
        contexts = [
            result
            for name in ["mmap_context_4096", "mmap_context_3072", "mmap_context_2048"]
            if (result := _load_result(name)) and "quality" in result
        ]
        best_ctx = max(contexts, key=_tradeoff_score)["config"]["n_ctx"] if contexts else 2048
        if _run_subprocess("best", args.limit, best_ctx=best_ctx, best_kv=best_kv) == 0:
            names.append("best")
        _write_summary(names)
        return

    if args.config == "best":
        contexts = [
            result
            for name in ["mmap_context_4096", "mmap_context_3072", "mmap_context_2048"]
            if (result := _load_result(name)) and "quality" in result
        ]
        kvs = [
            result
            for name in ["mmap_kv", "mmap_kv_q4"]
            if (result := _load_result(name)) and "quality" in result
        ]
        best_ctx = max(contexts, key=_tradeoff_score)["config"]["n_ctx"] if contexts else 2048
        best_kv = max(kvs, key=_tradeoff_score)["config"]["type_k"] if kvs else "Q8_0"
        raise SystemExit(_run_subprocess("best", args.limit, best_ctx=best_ctx, best_kv=best_kv))

    raise SystemExit(_run_subprocess(args.config, args.limit))


if __name__ == "__main__":
    main()
