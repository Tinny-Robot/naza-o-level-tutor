"""Fresh-process RSS/PSS/USS breakdown for the ADTC inference stack.

This diagnostic does not change production configuration or artifacts. It
measures component lifetimes, optional post-retrieval release, and isolated
batch/ubatch changes. Each experiment runs in a new subprocess.

Examples:

    .venv/bin/python scripts/benchmark_memory_breakdown.py --experiment baseline
    .venv/bin/python scripts/benchmark_memory_breakdown.py --experiment all
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MethodType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = PROJECT_ROOT / "data" / "benchmarks"
RESULT_PATH = BENCHMARK_DIR / "memory_breakdown.json"
REPORT_PATH = BENCHMARK_DIR / "memory_breakdown.md"
QUESTION_INDEX = 0
SAMPLE_INTERVAL_SECONDS = 0.10
FULL_SAMPLE_EVERY = 20
MIB = 1024 * 1024


@dataclass(frozen=True)
class DiagnosticConfig:
    name: str
    description: str
    release_embedder: bool = False
    release_faiss: bool = False
    n_batch: int = 512
    n_ubatch: int = 512
    use_repack: bool = True


def configs() -> dict[str, DiagnosticConfig]:
    return {
        "baseline": DiagnosticConfig(
            "baseline", "All production components remain resident"
        ),
        "release_embedder": DiagnosticConfig(
            "release_embedder",
            "Release KEmbed after retrieval, then collect and trim before Gemma",
            release_embedder=True,
        ),
        "release_embedder_faiss": DiagnosticConfig(
            "release_embedder_faiss",
            "Release KEmbed, FAISS, and full chunk store after retrieval",
            release_embedder=True,
            release_faiss=True,
        ),
        "batch_256": DiagnosticConfig(
            "batch_256", "Reduce n_batch and n_ubatch together to 256", n_batch=256, n_ubatch=256
        ),
        "ubatch_128": DiagnosticConfig(
            "ubatch_128", "Keep n_batch=512 and reduce only n_ubatch to 128", n_ubatch=128
        ),
        "batch_128": DiagnosticConfig(
            "batch_128", "Reduce n_batch and n_ubatch together to 128", n_batch=128, n_ubatch=128
        ),
        "no_repack": DiagnosticConfig(
            "no_repack",
            "Disable llama.cpp extra buffer types used for CPU weight repacking",
            use_repack=False,
        ),
        "release_embedder_no_repack": DiagnosticConfig(
            "release_embedder_no_repack",
            "Release KEmbed after retrieval and disable CPU weight repacking",
            release_embedder=True,
            use_repack=False,
        ),
    }


def memory_snapshot() -> dict[str, float]:
    values = status_snapshot()
    rollup: dict[str, int] = {}
    try:
        for line in Path("/proc/self/smaps_rollup").read_text().splitlines():
            if ":" not in line:
                continue
            key, rest = line.split(":", 1)
            fields = rest.split()
            if fields and fields[0].isdigit():
                rollup[key] = int(fields[0])
    except OSError:
        pass
    if rollup:
        values["pss_mib"] = rollup.get("Pss", 0) / 1024.0
        values["uss_mib"] = (
            rollup.get("Private_Clean", 0)
            + rollup.get("Private_Dirty", 0)
            + rollup.get("Private_Hugetlb", 0)
        ) / 1024.0
        values["shared_mib"] = (
            rollup.get("Shared_Clean", 0) + rollup.get("Shared_Dirty", 0)
        ) / 1024.0
        values["anonymous_mib"] = rollup.get("Anonymous", 0) / 1024.0
        values["file_mib"] = rollup.get("Pss_File", 0) / 1024.0
    return values


def status_snapshot() -> dict[str, float]:
    values: dict[str, float] = {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                key, raw = line.split()[:2]
                values[key.rstrip(":").lower() + "_mib"] = int(raw) / 1024.0
    except OSError:
        pass
    return values


class StageRecorder:
    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []

    def mark(self, name: str, **extra: Any) -> dict[str, Any]:
        snapshot = {"name": name, "at_seconds": time.perf_counter(), **memory_snapshot(), **extra}
        previous = self.stages[-1] if self.stages else None
        baseline = self.stages[0] if self.stages else snapshot
        for metric in ("vmrss_mib", "pss_mib", "uss_mib"):
            current = snapshot.get(metric)
            if current is None:
                continue
            snapshot[f"delta_previous_{metric}"] = current - float(previous.get(metric, current)) if previous else 0.0
            snapshot[f"delta_baseline_{metric}"] = current - float(baseline.get(metric, current))
        self.stages.append(snapshot)
        return snapshot


class MemorySampler:
    def __init__(self) -> None:
        self.samples: list[dict[str, float]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        sample_index = 0
        while not self._stop.is_set():
            if sample_index % FULL_SAMPLE_EVERY == 0:
                self.samples.append(memory_snapshot())
            else:
                self.samples.append(status_snapshot())
            sample_index += 1
            self._stop.wait(SAMPLE_INTERVAL_SECONDS)

    def __enter__(self) -> MemorySampler:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def summary(self) -> dict[str, Any]:
        result: dict[str, Any] = {"sample_count": len(self.samples)}
        for metric in ("vmrss_mib", "pss_mib", "uss_mib"):
            values = [sample[metric] for sample in self.samples if metric in sample]
            result[f"peak_{metric}"] = max(values) if values else None
            result[f"average_{metric}"] = statistics.fmean(values) if values else None
        return result


def malloc_trim() -> bool:
    try:
        libc = ctypes.CDLL("libc.so.6")
        return bool(libc.malloc_trim(0))
    except (OSError, AttributeError):
        return False


def normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def keyword_score(answer: str, keywords: list[str]) -> float:
    expected = [normalise(str(keyword)) for keyword in keywords]
    expected = [keyword for keyword in expected if keyword]
    if not expected:
        return 0.0
    value = normalise(answer)
    return sum(keyword in value for keyword in expected) / len(expected)


def install_llama_stage_hooks(
    recorder: StageRecorder, *, use_repack: bool
) -> tuple[Any, Any, Any]:
    from llama_cpp import _internals
    from llama_cpp import llama_cpp

    original_model = _internals.LlamaModel
    original_context = _internals.LlamaContext
    original_batch = _internals.LlamaBatch

    def model_hook(*args: Any, **kwargs: Any) -> Any:
        params = kwargs.get("params")
        if params is not None:
            params.use_extra_bufts = use_repack
        model = original_model(*args, **kwargs)
        recorder.mark(
            "06_after_gguf_model",
            llama_model_bytes=int(llama_cpp.llama_model_size(model.model)),
            llama_model_params=int(llama_cpp.llama_model_n_params(model.model)),
        )
        return model

    def context_hook(*args: Any, **kwargs: Any) -> Any:
        context = original_context(*args, **kwargs)
        recorder.mark("07_after_inference_context")
        return context

    def batch_hook(*args: Any, **kwargs: Any) -> Any:
        batch = original_batch(*args, **kwargs)
        recorder.mark("07b_after_llama_batch")
        return batch

    _internals.LlamaModel = model_hook
    _internals.LlamaContext = context_hook
    _internals.LlamaBatch = batch_hook
    return original_model, original_context, original_batch


def restore_llama_stage_hooks(originals: tuple[Any, Any, Any]) -> None:
    from llama_cpp import _internals

    _internals.LlamaModel, _internals.LlamaContext, _internals.LlamaBatch = originals


def install_llm_config(config: DiagnosticConfig) -> Any:
    import app.generation.llm as llm_module
    from app.config import (
        CONTEXT_LENGTH,
        FLASH_ATTN,
        MAX_TOKENS,
        MODEL_NAME,
        MODEL_PATH,
        SWA_FULL,
        TEMPERATURE,
        THREADS,
    )
    from llama_cpp import Llama

    original_init = llm_module.LlamaCppLLM.__init__

    def diagnostic_init(
        self: Any,
        *,
        model_path: str | Path | None = None,
        n_ctx: int = CONTEXT_LENGTH,
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
            "use_mmap": True,
            "use_mlock": False,
            "flash_attn": flash_attn,
            "swa_full": swa_full,
            "verbose": True,
        }
        self._llama = Llama(**kwargs)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.last_gen_tokens = 0
        self.llama_kwargs = kwargs

    llm_module.LlamaCppLLM.__init__ = diagnostic_init
    return original_init


def instrument_generation(llm: Any, generation: dict[str, Any]) -> None:
    import llama_cpp
    from app.generation.llm import strip_reasoning

    def measured_generate(self: Any, system: str, user: str) -> str:
        llama_cpp.llama_perf_context_reset(self._llama._ctx.ctx)
        started = time.perf_counter()
        response = self._llama.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=2026,
        )
        elapsed = time.perf_counter() - started
        content = response["choices"][0]["message"]["content"] or ""
        answer = strip_reasoning(content)
        perf = llama_cpp.llama_perf_context(self._llama._ctx.ctx)
        generated_tokens = int(perf.n_eval) or self.count_tokens(content)
        self.last_gen_tokens = generated_tokens
        generation.update(
            {
                "prompt_tokens": int(perf.n_p_eval),
                "generated_tokens": generated_tokens,
                "prompt_seconds": float(perf.t_p_eval_ms) / 1000.0,
                "generation_seconds": float(perf.t_eval_ms) / 1000.0,
                "prompt_tokens_per_second": (
                    int(perf.n_p_eval) / (float(perf.t_p_eval_ms) / 1000.0)
                    if perf.t_p_eval_ms > 0
                    else None
                ),
                "generation_tokens_per_second": (
                    generated_tokens / (float(perf.t_eval_ms) / 1000.0)
                    if perf.t_eval_ms > 0
                    else None
                ),
                "total_latency_seconds": elapsed,
            }
        )
        return answer

    llm.generate = MethodType(measured_generate, llm)


def release_embedding_model(embedder: Any, retriever: Any, recorder: StageRecorder) -> dict[str, Any]:
    import app.ingestion.embedder as embedder_module

    before = memory_snapshot()
    retriever.embedder = None
    embedder._model = None
    embedder_module._embedder_singleton = None
    embedder_module._MODEL_CACHE.clear()
    recorder.mark("04c_after_embedder_references_cleared")
    collected = gc.collect()
    recorder.mark("04d_after_embedder_gc", gc_collected=collected)
    trimmed = malloc_trim()
    after = recorder.mark("04e_after_embedder_malloc_trim", malloc_trim=trimmed)
    return {
        "before_release": before,
        "after_release": after,
        "rss_released_mib": before.get("vmrss_mib", 0.0) - after.get("vmrss_mib", 0.0),
        "pss_released_mib": before.get("pss_mib", 0.0) - after.get("pss_mib", 0.0),
        "uss_released_mib": before.get("uss_mib", 0.0) - after.get("uss_mib", 0.0),
        "gc_collected": collected,
        "malloc_trim": trimmed,
        "torch_cpu_release_api": "none; tensors released by reference deletion and allocator trim",
    }


def release_faiss_and_chunks(retriever: Any, recorder: StageRecorder) -> dict[str, Any]:
    import app.retrieval.search as search_module

    before = memory_snapshot()
    if retriever.store is not None:
        retriever.store.index = None
    retriever.store = None
    retriever.chunks = []
    search_module._retriever = None
    recorder.mark("04f_after_faiss_references_cleared")
    collected = gc.collect()
    trimmed = malloc_trim()
    after = recorder.mark(
        "04g_after_faiss_gc_trim", gc_collected=collected, malloc_trim=trimmed
    )
    return {
        "before_release": before,
        "after_release": after,
        "rss_released_mib": before.get("vmrss_mib", 0.0) - after.get("vmrss_mib", 0.0),
        "pss_released_mib": before.get("pss_mib", 0.0) - after.get("pss_mib", 0.0),
        "uss_released_mib": before.get("uss_mib", 0.0) - after.get("uss_mib", 0.0),
        "gc_collected": collected,
        "malloc_trim": trimmed,
    }


class FixedRetrieval:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results

    def retrieve(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return self.results


def run_worker(config: DiagnosticConfig) -> dict[str, Any]:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    recorder = StageRecorder()
    recorder.mark("01_process_start")

    sys.path.insert(0, str(PROJECT_ROOT))
    from app.config import MODEL_PATH, QA_PATH, THREADS, TOP_K
    from app.generation.llm import LlamaCppLLM
    from app.generation.pipeline import GenerationPipeline
    from app.generation.prompt_manager import get_prompt_manager
    from app.ingestion.embedder import get_embedder
    from app.retrieval.retriever import Retriever
    from app.student.updater import LearningProfileUpdater
    import app.student.store as student_store_module
    from app.utils.offline import enable_offline_mode, run_self_check

    temporary_student_dir = tempfile.TemporaryDirectory(prefix="adtc-memory-benchmark-")
    student_store_module.STUDENT_DIR = Path(temporary_student_dir.name)
    student_store_module._store = None
    LearningProfileUpdater.apply_event = lambda self, event: None
    enable_offline_mode()
    check = run_self_check()
    if not check.ok:
        raise RuntimeError("; ".join(check.format_lines()))
    recorder.mark("02_after_application_imports")

    items = json.loads(QA_PATH.read_text())
    item = items[QUESTION_INDEX]
    prompts = get_prompt_manager()
    embedder = get_embedder()
    embedding_model = embedder.model
    recorder.mark("03_after_embedding_model")

    retriever = Retriever(embedder=embedder)
    recorder.mark("04_after_faiss_and_chunks")
    retrieved = retriever.retrieve(
        item["question"],
        top_k=TOP_K,
        subject=item.get("subject"),
        topic=item.get("topic"),
    )
    recorder.mark("04b_after_rag_retrieval", retrieved_chunks=len(retrieved))

    releases: dict[str, Any] = {}
    if config.release_embedder:
        embedding_model = None
        releases["embedding"] = release_embedding_model(embedder, retriever, recorder)
        embedder = None
    if config.release_faiss:
        releases["faiss_and_chunks"] = release_faiss_and_chunks(retriever, recorder)
        retriever = None

    import llama_cpp

    recorder.mark(
        "05_after_llama_cpp_initialization",
        llama_cpp_python_version=getattr(llama_cpp, "__version__", "unknown"),
    )
    originals = install_llama_stage_hooks(recorder, use_repack=config.use_repack)
    original_llm_init = install_llm_config(config)
    generation: dict[str, Any] = {}
    try:
        model_started = time.perf_counter()
        llm = LlamaCppLLM()
        model_load_seconds = time.perf_counter() - model_started
        recorder.mark("07c_after_high_level_llama", model_load_seconds=model_load_seconds)
        instrument_generation(llm, generation)
        pipeline = GenerationPipeline(
            retrieval=FixedRetrieval(retrieved),
            llm=llm,
            prompts=prompts,
        )
        recorder.mark("08_before_generation")
        with MemorySampler() as sampler:
            generation_started = time.perf_counter()
            result = pipeline._ask_study(
                item["question"],
                top_k=TOP_K,
                subject=item.get("subject"),
                topic=item.get("topic"),
            )
            generation["end_to_end_seconds"] = time.perf_counter() - generation_started
        generation["memory_samples"] = sampler.summary()
        recorder.mark("09_after_generation")
        recorder.mark(
            "10_peak_during_generation",
            vmrss_mib=sampler.summary().get("peak_vmrss_mib"),
            pss_mib=sampler.summary().get("peak_pss_mib"),
            uss_mib=sampler.summary().get("peak_uss_mib"),
        )
    finally:
        import app.generation.llm as llm_module

        llm_module.LlamaCppLLM.__init__ = original_llm_init
        restore_llama_stage_hooks(originals)

    return {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": asdict(config),
        "question": {
            "index": QUESTION_INDEX,
            "id": item.get("id"),
            "prompt_length_characters": len(item["question"]),
            "retrieved_chunks": len(retrieved),
            "answer_characters": len(result.get("answer") or ""),
            "answer_sha256": hashlib.sha256(
                (result.get("answer") or "").encode("utf-8")
            ).hexdigest(),
            "keyword_score": keyword_score(
                result.get("answer") or "", item.get("expected_keywords") or []
            ),
        },
        "controls": {
            "model_path": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
            "model_file_bytes": MODEL_PATH.stat().st_size,
            "context_length": 4096,
            "threads": THREADS,
            "n_gpu_layers": 0,
            "use_mmap": True,
            "use_mlock": False,
            "flash_attention": True,
            "swa_full": False,
            "rag_top_k": TOP_K,
            "sampling_seed": 2026,
            "use_repack": config.use_repack,
        },
        "stages": recorder.stages,
        "releases": releases,
        "generation": generation,
        "final_memory": memory_snapshot(),
    }


def size_to_mib(value: str, unit: str) -> float:
    amount = float(value)
    unit = unit.lower()
    if unit == "gib":
        return amount * 1024.0
    if unit == "kib":
        return amount / 1024.0
    return amount


def parse_llama_log(path: Path) -> dict[str, Any]:
    text = path.read_text(errors="replace") if path.is_file() else ""
    parsed: dict[str, Any] = {}
    tensor = re.search(r"loaded meta data with \d+ key-value pairs and (\d+) tensors", text)
    if tensor:
        parsed["tensor_count"] = int(tensor.group(1))
    patterns = {
        "model_buffer_mib": r"model buffer size\s*=\s*([0-9.]+)\s*(KiB|MiB|GiB)",
        "mapped_model_buffer_mib": r"CPU_Mapped model buffer size\s*=\s*([0-9.]+)\s*(KiB|MiB|GiB)",
        "repack_model_buffer_mib": r"CPU_REPACK model buffer size\s*=\s*([0-9.]+)\s*(KiB|MiB|GiB)",
        "kv_buffer_mib": r"KV buffer size\s*=\s*([0-9.]+)\s*(KiB|MiB|GiB)",
        "compute_buffer_mib": r"compute buffer size\s*=\s*([0-9.]+)\s*(KiB|MiB|GiB)",
    }
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            parsed[key] = sum(size_to_mib(value, unit) for value, unit in matches)
    parsed["relevant_log_lines"] = [
        line
        for line in text.splitlines()
        if any(token in line.lower() for token in ("buffer size", "compute buffer", "kv buffer", "tensors"))
    ]
    return parsed


def run_subprocess(config: DiagnosticConfig) -> dict[str, Any]:
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    log_path = BENCHMARK_DIR / f"memory_breakdown_{config.name}.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--experiment",
        config.name,
    ]
    with log_path.open("w") as stderr:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            check=False,
        )
    result_path = BENCHMARK_DIR / f"memory_breakdown_{config.name}.json"
    if completed.returncode != 0:
        raise RuntimeError(f"{config.name} failed; see {log_path}")
    result = json.loads(result_path.read_text())
    result["llama_reported_buffers"] = parse_llama_log(log_path)
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def stage(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in result["stages"] if item["name"] == name)


def component_rows(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    pairs = [
        ("Python + application imports", "01_process_start", "02_after_application_imports"),
        ("KEmbed-naija-v3", "02_after_application_imports", "03_after_embedding_model"),
        ("FAISS index + chunks", "03_after_embedding_model", "04_after_faiss_and_chunks"),
        ("First embedding query working set", "04_after_faiss_and_chunks", "04b_after_rag_retrieval"),
        ("llama.cpp import/runtime", "04b_after_rag_retrieval", "05_after_llama_cpp_initialization"),
        ("GGUF model load", "05_after_llama_cpp_initialization", "06_after_gguf_model"),
        ("Inference context", "06_after_gguf_model", "07_after_inference_context"),
        ("Llama batch", "07_after_inference_context", "07b_after_llama_batch"),
        ("Python high-level buffers", "07b_after_llama_batch", "07c_after_high_level_llama"),
        ("Generation working set", "08_before_generation", "10_peak_during_generation"),
    ]
    rows = []
    for component, before_name, after_name in pairs:
        before = stage(baseline, before_name)
        after = stage(baseline, after_name)
        rows.append(
            {
                "component": component,
                "rss_mib": after.get("vmrss_mib", 0.0) - before.get("vmrss_mib", 0.0),
                "pss_mib": after.get("pss_mib", 0.0) - before.get("pss_mib", 0.0),
                "uss_mib": after.get("uss_mib", 0.0) - before.get("uss_mib", 0.0),
                "method": f"stage delta: {before_name} -> {after_name}",
            }
        )
    return rows


def write_outputs(results: list[dict[str, Any]]) -> None:
    by_name = {result["config"]["name"]: result for result in results}
    baseline = by_name["baseline"]
    components = component_rows(baseline)
    payload = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "experiments": results,
        "baseline_components": components,
        "key_findings": {
            "baseline_peak_rss_mib": stage(baseline, "10_peak_during_generation").get("vmrss_mib"),
            "embedding_load_rss_mib": next(item for item in components if item["component"] == "KEmbed-naija-v3")["rss_mib"],
            "embedding_query_working_rss_mib": next(item for item in components if item["component"] == "First embedding query working set")["rss_mib"],
            "mapped_model_buffer_mib": baseline.get("llama_reported_buffers", {}).get("mapped_model_buffer_mib"),
            "repack_model_buffer_mib": baseline.get("llama_reported_buffers", {}).get("repack_model_buffer_mib"),
        },
    }
    RESULT_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Memory breakdown diagnostic",
        "",
        "All measurements use Linux `/proc/self/status` and `/proc/self/smaps_rollup` in fresh processes. USS is private clean + private dirty memory; PSS proportionally attributes shared mappings.",
        "",
        "## Baseline stages",
        "",
        "| Stage | RSS MiB | Delta previous | Delta baseline | PSS MiB | USS MiB |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in baseline["stages"]:
        lines.append(
            f"| {item['name']} | {item.get('vmrss_mib', 0):.1f} | "
            f"{item.get('delta_previous_vmrss_mib', 0):+.1f} | "
            f"{item.get('delta_baseline_vmrss_mib', 0):+.1f} | "
            f"{item.get('pss_mib', 0):.1f} | {item.get('uss_mib', 0):.1f} |"
        )
    lines += [
        "",
        "## Component estimates",
        "",
        "| Component | RSS MiB | PSS MiB | USS MiB | Measurement method |",
        "|---|---:|---:|---:|---|",
    ]
    for item in components:
        lines.append(
            f"| {item['component']} | {item['rss_mib']:+.1f} | {item['pss_mib']:+.1f} | "
            f"{item['uss_mib']:+.1f} | {item['method']} |"
        )
    lines += [
        "",
        "## Experiment comparison",
        "",
        "| Experiment | Repack | Batch | Ubatch | Peak RSS | Headroom vs 7 GiB | Peak PSS | Peak USS | Gen tok/s | Keyword score |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        peak = stage(result, "10_peak_during_generation")
        headroom = 7168.0 - float(peak.get("vmrss_mib", 0.0))
        measured_keyword_score = result["question"].get("keyword_score")
        keyword_display = (
            f"{measured_keyword_score:.3f}"
            if measured_keyword_score is not None
            else "n/a"
        )
        lines.append(
            f"| {result['config']['name']} | {result['config'].get('use_repack', True)} | {result['config']['n_batch']} | {result['config']['n_ubatch']} | "
            f"{peak.get('vmrss_mib', 0):.1f} | {headroom:+.1f} | "
            f"{peak.get('pss_mib', 0):.1f} | {peak.get('uss_mib', 0):.1f} | "
            f"{result['generation'].get('generation_tokens_per_second') or 0:.3f} | "
            f"{keyword_display} |"
        )

    embed_component = next(item for item in components if item["component"] == "KEmbed-naija-v3")
    release = by_name.get("release_embedder", {}).get("releases", {}).get("embedding", {})
    faiss_release = by_name.get("release_embedder_faiss", {}).get("releases", {}).get("faiss_and_chunks", {})
    no_repack = by_name.get("no_repack")
    no_repack_release = by_name.get("release_embedder_no_repack")
    largest = max(components, key=lambda item: item["rss_mib"])
    query_component = next(item for item in components if item["component"] == "First embedding query working set")
    baseline_buffers = baseline.get("llama_reported_buffers", {})
    lines += [
        "",
        "## llama.cpp reported allocations",
        "",
        f"- Tensors: **{baseline_buffers.get('tensor_count', 'n/a')}**",
        f"- CPU mapped model buffer: **{baseline_buffers.get('mapped_model_buffer_mib', 0):.2f} MiB**",
        f"- CPU repack model buffer: **{baseline_buffers.get('repack_model_buffer_mib', 0):.2f} MiB**",
        f"- Total model buffers: **{baseline_buffers.get('model_buffer_mib', 0):.2f} MiB**",
        f"- KV buffers: **{baseline_buffers.get('kv_buffer_mib', 0):.2f} MiB**",
        f"- Reserved compute buffer: **{baseline_buffers.get('compute_buffer_mib', 0):.2f} MiB**",
        "",
        "## Findings",
        "",
        f"1. Largest measured component: **{largest['component']}**, {largest['rss_mib']:.1f} MiB RSS by stage delta.",
        f"2. KEmbed load contribution: **{embed_component['rss_mib']:.1f} MiB RSS**, {embed_component['pss_mib']:.1f} MiB PSS, {embed_component['uss_mib']:.1f} MiB USS.",
        f"3. The first embedding query adds another **{query_component['rss_mib']:.1f} MiB RSS** of framework/allocator working memory.",
        f"4. KEmbed actually returned after reference clearing, GC, and malloc trim: **{release.get('rss_released_mib', 0):.1f} MiB RSS**.",
        f"5. Additional FAISS/chunk release: **{faiss_release.get('rss_released_mib', 0):.1f} MiB RSS**.",
        f"6. Baseline CPU repacking duplicates **{baseline_buffers.get('repack_model_buffer_mib', 0):.2f} MiB** beyond the {baseline_buffers.get('mapped_model_buffer_mib', 0):.2f} MiB mapped weights.",
        f"7. No-repack peak: **{stage(no_repack, '10_peak_during_generation').get('vmrss_mib', 0):.1f} MiB** ({stage(no_repack, '10_peak_during_generation').get('vmrss_mib', 0)/1024:.3f} GiB), with **{7168-stage(no_repack, '10_peak_during_generation').get('vmrss_mib', 0):.1f} MiB headroom** under 7 GiB." if no_repack else "7. No-repack result unavailable.",
        f"8. Releasing KEmbed plus no-repack peaks at **{stage(no_repack_release, '10_peak_during_generation').get('vmrss_mib', 0):.1f} MiB** ({stage(no_repack_release, '10_peak_during_generation').get('vmrss_mib', 0)/1024:.3f} GiB)." if no_repack_release else "8. Combined release result unavailable.",
        "9. The embedder is required for every new dense query. Releasing it after one retrieval is safe only when that request's retrieved chunks are retained and no further retrieval occurs in the same process without reloading the model.",
        "10. No-repack is a diagnostic candidate, not a production recommendation. It must pass the full accuracy and speed benchmark because changing tensor buffer layout can alter numerical output.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "cd /home/ubuntu/O-Level/O-Level",
        "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \\",
        "  .venv/bin/python scripts/benchmark_memory_breakdown.py --experiment all",
        "```",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    available = configs()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=[*available, "all"], default="all")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

    if args.worker:
        result = run_worker(available[args.experiment])
        path = BENCHMARK_DIR / f"memory_breakdown_{args.experiment}.json"
        path.write_text(json.dumps(result, indent=2) + "\n")
        print(path)
        return

    names = list(available) if args.experiment == "all" else [args.experiment]
    results = [run_subprocess(available[name]) for name in names]
    if args.experiment == "all":
        write_outputs(results)
    else:
        existing = []
        for name in available:
            path = BENCHMARK_DIR / f"memory_breakdown_{name}.json"
            if path.is_file():
                existing.append(json.loads(path.read_text()))
        if "baseline" in {item["config"]["name"] for item in existing}:
            write_outputs(existing)


if __name__ == "__main__":
    main()
