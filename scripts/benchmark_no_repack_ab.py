"""Controlled production vs no-repack A/B benchmark.

The only model-runtime difference between production and no-repack is the
llama.cpp model parameter ``use_extra_bufts``. A third diagnostic configuration
keeps no-repack but releases KEmbed after each retrieval.

Examples:

    .venv/bin/python scripts/benchmark_no_repack_ab.py --limit 1 --label validation
    .venv/bin/python scripts/benchmark_no_repack_ab.py --limit 8 --label representative
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MethodType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = PROJECT_ROOT / "data" / "benchmarks"
WORK_DIR = BENCHMARK_DIR / "no_repack_ab"
OUTPUT_JSON = BENCHMARK_DIR / "no_repack_ab.json"
OUTPUT_MD = BENCHMARK_DIR / "no_repack_ab.md"
QA_PATH = PROJECT_ROOT / "data" / "eval" / "qa.json"
COMPETITION_LIMIT_MIB = 7 * 1024
SEED = 2026


@dataclass(frozen=True)
class RuntimeConfig:
    name: str
    description: str
    use_repack: bool
    release_embedder: bool = False


CONFIGS = {
    "production": RuntimeConfig(
        "production", "Current production CPU repacking enabled/default", True
    ),
    "no_repack": RuntimeConfig(
        "no_repack", "Only use_extra_bufts=False differs from production", False
    ),
    "no_repack_release": RuntimeConfig(
        "no_repack_release",
        "No-repack plus KEmbed release after each retrieval",
        False,
        True,
    ),
}


def status_memory() -> dict[str, float]:
    result: dict[str, float] = {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                key, value = line.split()[:2]
                result[key.rstrip(":").lower() + "_mib"] = int(value) / 1024.0
    except OSError:
        pass
    return result


class RssSampler:
    def __init__(self, interval: float = 0.1) -> None:
        self.interval = interval
        self.values: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            value = status_memory().get("vmrss_mib")
            if value is not None:
                self.values.append(value)
            self._stop.wait(self.interval)

    def __enter__(self) -> RssSampler:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def summary(self) -> dict[str, float | None]:
        if not self.values:
            return {"average_rss_mib": None, "sampled_peak_rss_mib": None}
        return {
            "average_rss_mib": statistics.fmean(self.values),
            "sampled_peak_rss_mib": max(self.values),
        }


def normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def keyword_score(answer: str, keywords: list[str]) -> float:
    expected = [normalise(str(keyword)) for keyword in keywords]
    expected = [keyword for keyword in expected if keyword]
    if not expected:
        return 0.0
    value = normalise(answer)
    return sum(keyword in value for keyword in expected) / len(expected)


def retrieval_labels(
    results: list[dict[str, Any]], subject: str, keywords: list[str]
) -> list[bool]:
    expected_subject = (subject or "").strip().lower()
    expected_keywords = [str(keyword).strip().lower() for keyword in keywords]
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
        keyword_hit = any(keyword and keyword in haystack for keyword in expected_keywords)
        subject_hit = bool(expected_subject) and document_subject == expected_subject
        labels.append((subject_hit and (not expected_keywords or keyword_hit)) or keyword_hit)
    return labels


def canonical_retrieval(results: list[dict[str, Any]]) -> str:
    compact = []
    for result in results:
        metadata = result.get("metadata") or {}
        compact.append(
            {
                "score": round(float(result.get("score") or 0.0), 7),
                "text": result.get("text") or "",
                "metadata": metadata,
            }
        )
    return hashlib.sha256(
        json.dumps(compact, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def select_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return items
    eligible = [
        item
        for item in items
        if not item.get("needs_review") and 12 <= len(item.get("question") or "") <= 1200
    ]
    subjects = ["chemistry", "english", "mathematics", "physics"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in eligible:
        groups[str(item.get("subject") or "").lower()].append(item)
    for group in groups.values():
        group.sort(key=lambda item: str(item.get("id") or ""))
    selected: list[dict[str, Any]] = []
    allocation = {subject: limit // len(subjects) for subject in subjects}
    for subject in subjects[: limit % len(subjects)]:
        allocation[subject] += 1
    for subject in subjects:
        count = allocation[subject]
        group = groups[subject]
        if count == 1:
            indexes = [len(group) // 2]
        elif count > 1:
            indexes = [round(index * (len(group) - 1) / (count - 1)) for index in range(count)]
        else:
            indexes = []
        selected.extend(group[index] for index in indexes)
    selected.sort(key=lambda item: (subjects.index(str(item.get("subject")).lower()), str(item.get("id"))))
    return selected


def prepare_cases(limit: int, label: str) -> Path:
    sys.path.insert(0, str(PROJECT_ROOT))
    from app.config import QA_PATH, TOP_K
    from app.ingestion.embedder import get_embedder
    from app.retrieval.retriever import Retriever
    from app.utils.offline import enable_offline_mode

    enable_offline_mode()
    items = select_items(json.loads(QA_PATH.read_text()), limit)
    embedder = get_embedder()
    retriever = Retriever(embedder=embedder)
    cases = []
    for item in items:
        results = retriever.retrieve(item["question"], top_k=TOP_K)
        cases.append(
            {
                "item": item,
                "retrieved": results,
                "retrieval_hash": canonical_retrieval(results),
                "retrieved_ids": [
                    (result.get("metadata") or {}).get("id") for result in results
                ],
            }
        )
    path = WORK_DIR / f"cases_{label}_{len(cases)}.json"
    path.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n")
    return path


def malloc_trim() -> bool:
    try:
        return bool(ctypes.CDLL("libc.so.6").malloc_trim(0))
    except (OSError, AttributeError):
        return False


def release_embedder(embedder: Any, retriever: Any) -> dict[str, Any]:
    import app.ingestion.embedder as embedder_module

    before = status_memory()
    retriever.embedder = None
    embedder._model = None
    embedder_module._embedder_singleton = None
    embedder_module._MODEL_CACHE.clear()
    collected = gc.collect()
    trimmed = malloc_trim()
    after = status_memory()
    return {
        "before_rss_mib": before.get("vmrss_mib"),
        "after_rss_mib": after.get("vmrss_mib"),
        "released_rss_mib": (before.get("vmrss_mib") or 0.0)
        - (after.get("vmrss_mib") or 0.0),
        "gc_collected": collected,
        "malloc_trim": trimmed,
    }


def install_repack_hook(use_repack: bool) -> Any:
    from llama_cpp import _internals

    original = _internals.LlamaModel

    def hooked(*args: Any, **kwargs: Any) -> Any:
        params = kwargs.get("params")
        if params is not None:
            params.use_extra_bufts = use_repack
        return original(*args, **kwargs)

    _internals.LlamaModel = hooked
    return original


def install_llm_init(config: RuntimeConfig) -> Any:
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

    original = llm_module.LlamaCppLLM.__init__

    def benchmark_init(
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
            "n_batch": 512,
            "n_ubatch": 512,
            "use_mmap": True,
            "use_mlock": False,
            "flash_attn": flash_attn,
            "swa_full": swa_full,
            "verbose": False,
        }
        self._llama = Llama(**kwargs)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.last_gen_tokens = 0
        self.llama_kwargs = kwargs

    llm_module.LlamaCppLLM.__init__ = benchmark_init
    return original


def instrument_generation(llm: Any, measurements: list[dict[str, Any]]) -> None:
    import llama_cpp
    from app.generation.llm import strip_reasoning

    def measured_generate(self: Any, system: str, user: str) -> str:
        llama_cpp.llama_perf_context_reset(self._llama._ctx.ctx)
        started = time.perf_counter()
        first_token_at: float | None = None
        finish_reason: str | None = None
        pieces: list[str] = []
        stream = self._llama.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            top_p=0.95,
            top_k=40,
            min_p=0.05,
            max_tokens=self.max_tokens,
            seed=SEED,
            stream=True,
        )
        for chunk in stream:
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            content = (choice.get("delta") or {}).get("content")
            if content:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                pieces.append(content)
            if choice.get("finish_reason"):
                finish_reason = str(choice["finish_reason"])
        finished = time.perf_counter()
        raw = "".join(pieces)
        answer = strip_reasoning(raw)
        perf = llama_cpp.llama_perf_context(self._llama._ctx.ctx)
        generation_seconds = float(perf.t_eval_ms) / 1000.0
        prompt_seconds = float(perf.t_p_eval_ms) / 1000.0
        generated_tokens = int(perf.n_eval) or self.count_tokens(raw)
        self.last_gen_tokens = generated_tokens
        measurements.append(
            {
                "prompt_hash": hashlib.sha256(
                    (system + "\0" + user).encode("utf-8")
                ).hexdigest(),
                "prompt_tokens": int(perf.n_p_eval),
                "generated_tokens": generated_tokens,
                "prompt_seconds": prompt_seconds,
                "generation_seconds": generation_seconds,
                "prompt_tokens_per_second": (
                    int(perf.n_p_eval) / prompt_seconds if prompt_seconds > 0 else None
                ),
                "generation_tokens_per_second": (
                    generated_tokens / generation_seconds
                    if generation_seconds > 0
                    else None
                ),
                "time_to_first_token_seconds": (
                    first_token_at - started if first_token_at is not None else None
                ),
                "total_latency_seconds": finished - started,
                "finish_reason": finish_reason or "unknown",
                "stop_class": (
                    "max_tokens" if finish_reason == "length" else "eos_or_stop"
                    if finish_reason == "stop"
                    else "unknown"
                ),
            }
        )
        if not answer:
            raise RuntimeError("Empty completion")
        return answer

    llm.generate = MethodType(measured_generate, llm)


class FrozenRetrieval:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results

    def retrieve(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return self.results


def run_worker(config: RuntimeConfig, cases_path: Path, label: str) -> dict[str, Any]:
    sys.path.insert(0, str(PROJECT_ROOT))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from llama_cpp import _internals
    from app.config import MAX_CONTEXT_TOKENS, MODEL_PATH, THREADS, TOP_K
    from app.generation.llm import LlamaCppLLM
    from app.generation.pipeline import GenerationPipeline
    from app.generation.prompt_manager import get_prompt_manager
    from app.ingestion.embedder import get_embedder
    from app.retrieval.retriever import Retriever
    from app.student.updater import LearningProfileUpdater
    import app.student.store as student_store_module
    from app.utils.offline import enable_offline_mode, run_self_check

    temporary_student_dir = tempfile.TemporaryDirectory(prefix="adtc-no-repack-ab-")
    student_store_module.STUDENT_DIR = Path(temporary_student_dir.name)
    student_store_module._store = None
    LearningProfileUpdater.apply_event = lambda self, event: None
    enable_offline_mode()
    check = run_self_check()
    if not check.ok:
        raise RuntimeError("; ".join(check.format_lines()))

    cases = json.loads(cases_path.read_text())
    prompts = get_prompt_manager()
    original_model = install_repack_hook(config.use_repack)
    original_init = install_llm_init(config)
    embedder = None
    retriever = None
    try:
        if not config.release_embedder:
            embedder = get_embedder()
            _embedding_model = embedder.model
            retriever = Retriever(embedder=embedder)
        else:
            retriever = Retriever()

        load_started = time.perf_counter()
        llm = LlamaCppLLM()
        model_load_seconds = time.perf_counter() - load_started
        measurements: list[dict[str, Any]] = []
        instrument_generation(llm, measurements)

        rows: list[dict[str, Any]] = []
        with RssSampler() as run_sampler:
            for case in cases:
                item = case["item"]
                release_metrics = None
                if config.release_embedder:
                    embedder = get_embedder(force_reload=True)
                    _embedding_model = embedder.model
                    retriever.embedder = embedder
                retrieval_started = time.perf_counter()
                actual_results = retriever.retrieve(item["question"], top_k=TOP_K)
                retrieval_seconds = time.perf_counter() - retrieval_started
                actual_hash = canonical_retrieval(actual_results)
                retrieval_match = actual_hash == case["retrieval_hash"]
                if config.release_embedder:
                    _embedding_model = None
                    release_metrics = release_embedder(embedder, retriever)
                    embedder = None

                pipeline = GenerationPipeline(
                    retrieval=FrozenRetrieval(case["retrieved"]),
                    llm=llm,
                    prompts=prompts,
                    max_context_tokens=MAX_CONTEXT_TOKENS,
                )
                before_measurements = len(measurements)
                error = None
                with RssSampler() as question_sampler:
                    started = time.perf_counter()
                    try:
                        result = pipeline._ask_study(
                            item["question"],
                            top_k=TOP_K,
                            subject=item.get("subject"),
                            topic=item.get("topic"),
                        )
                        answer = str(result.get("answer") or "")
                    except Exception as exc:
                        answer = ""
                        result = {"citations": [], "retrieved_chunks": [], "refused": True}
                        error = f"{type(exc).__name__}: {exc}"
                    end_to_end = time.perf_counter() - started
                measurement = (
                    measurements[-1]
                    if len(measurements) > before_measurements
                    else {
                        "prompt_hash": None,
                        "prompt_tokens": 0,
                        "generated_tokens": 0,
                        "prompt_tokens_per_second": None,
                        "generation_tokens_per_second": None,
                        "time_to_first_token_seconds": None,
                        "total_latency_seconds": end_to_end,
                        "finish_reason": "failed",
                        "stop_class": "failed",
                    }
                )
                labels = retrieval_labels(
                    case["retrieved"],
                    str(item.get("subject") or ""),
                    item.get("expected_keywords") or [],
                )
                rows.append(
                    {
                        "id": item.get("id"),
                        "subject": item.get("subject"),
                        "topic": item.get("topic"),
                        "question": item.get("question"),
                        "reference_answer": item.get("answer"),
                        "expected_keywords": item.get("expected_keywords") or [],
                        "answer": answer,
                        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                        "exact_match_reference": normalise(answer)
                        == normalise(str(item.get("answer") or "")),
                        "keyword_score": keyword_score(
                            answer, item.get("expected_keywords") or []
                        ),
                        "retrieval_hit": any(labels),
                        "retrieval_hash": actual_hash,
                        "expected_retrieval_hash": case["retrieval_hash"],
                        "retrieval_match": retrieval_match,
                        "retrieval_seconds": retrieval_seconds,
                        "release": release_metrics,
                        "error": error,
                        "end_to_end_seconds": end_to_end,
                        "question_memory": question_sampler.summary(),
                        **measurement,
                    }
                )
        run_memory = run_sampler.summary()
    finally:
        import app.generation.llm as llm_module

        llm_module.LlamaCppLLM.__init__ = original_init
        _internals.LlamaModel = original_model

    peak_rss = status_memory().get("vmhwm_mib", 0.0)
    successful = [row for row in rows if not row["error"]]
    result = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label": label,
        "config": asdict(config),
        "controls": {
            "model_path": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
            "model_size_bytes": MODEL_PATH.stat().st_size,
            "llama_cpp_python": __import__("llama_cpp").__version__,
            "context_length": 4096,
            "n_batch": 512,
            "n_ubatch": 512,
            "threads": THREADS,
            "n_gpu_layers": 0,
            "use_mmap": True,
            "use_mlock": False,
            "flash_attention": True,
            "swa_full": False,
            "temperature": 0.1,
            "top_p": 0.95,
            "top_k_sampling": 40,
            "min_p": 0.05,
            "seed": SEED,
            "max_tokens": 512,
            "rag_top_k": TOP_K,
            "cases_path": str(cases_path.relative_to(PROJECT_ROOT)),
        },
        "model_load_seconds": model_load_seconds,
        "memory": {
            "peak_rss_mib": peak_rss,
            "peak_rss_gib": peak_rss / 1024.0,
            "headroom_mib": COMPETITION_LIMIT_MIB - peak_rss,
            "status": "PASS" if peak_rss <= COMPETITION_LIMIT_MIB else "FAIL - ABOVE 7 GiB",
            **run_memory,
        },
        "questions": rows,
        "summary": aggregate_rows(rows, model_load_seconds, peak_rss, run_memory),
    }
    return result


def stats(values: list[float | int | None]) -> dict[str, float | None]:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not valid:
        return {"average": None, "median": None, "minimum": None, "maximum": None}
    return {
        "average": statistics.fmean(valid),
        "median": statistics.median(valid),
        "minimum": min(valid),
        "maximum": max(valid),
    }


def aggregate_rows(
    rows: list[dict[str, Any]], model_load_seconds: float, peak_rss: float, run_memory: dict[str, Any]
) -> dict[str, Any]:
    successful = [row for row in rows if not row["error"]]
    releases = [row["release"] for row in rows if row.get("release")]
    return {
        "questions": len(rows),
        "successful_generations": len(successful),
        "failures": len(rows) - len(successful),
        "accuracy_metric": "mean expected-keyword recall",
        "accuracy": statistics.fmean(row["keyword_score"] for row in rows) if rows else 0.0,
        "exact_match_reference": statistics.fmean(float(row["exact_match_reference"]) for row in rows) if rows else 0.0,
        "retrieval_hit_rate": statistics.fmean(float(row["retrieval_hit"]) for row in rows) if rows else 0.0,
        "retrieval_match_rate": statistics.fmean(float(row["retrieval_match"]) for row in rows) if rows else 0.0,
        "generated_tokens": stats([row["generated_tokens"] for row in successful]),
        "generation_tokens_per_second": stats(
            [row["generation_tokens_per_second"] for row in successful]
        ),
        "prompt_tokens_per_second": stats(
            [row["prompt_tokens_per_second"] for row in successful]
        ),
        "time_to_first_token_seconds": stats(
            [row["time_to_first_token_seconds"] for row in successful]
        ),
        "total_latency_seconds": stats(
            [row["total_latency_seconds"] for row in successful]
        ),
        "end_to_end_seconds": stats([row["end_to_end_seconds"] for row in rows]),
        "finish_reasons": dict(Counter(row["finish_reason"] for row in rows)),
        "stop_classes": dict(Counter(row["stop_class"] for row in rows)),
        "model_load_seconds": model_load_seconds,
        "peak_rss_mib": peak_rss,
        "average_rss_mib": run_memory.get("average_rss_mib"),
        "generation_sampled_peak_rss_mib": stats(
            [row["question_memory"].get("sampled_peak_rss_mib") for row in rows]
        ),
        "embedder_release_rss_mib": stats(
            [release.get("released_rss_mib") for release in releases]
        ),
    }


def run_worker_subprocess(config: RuntimeConfig, cases_path: Path, label: str) -> dict[str, Any]:
    path = WORK_DIR / f"{label}_{config.name}.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--config",
        config.name,
        "--cases",
        str(cases_path),
        "--label",
        label,
    ]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Worker {config.name} failed")
    return json.loads(path.read_text())


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def semantic_comparisons(results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    from sentence_transformers import SentenceTransformer
    from app.config import EMBEDDING_MODEL_PATH

    model = SentenceTransformer(str(EMBEDDING_MODEL_PATH), local_files_only=True)
    production_rows = {row["id"]: row for row in results["production"]["questions"]}
    comparisons = []
    for config_name in ("no_repack", "no_repack_release"):
        for candidate in results[config_name]["questions"]:
            baseline = production_rows[candidate["id"]]
            texts = [
                baseline["answer"] or " ",
                candidate["answer"] or " ",
                candidate["reference_answer"] or " ",
            ]
            vectors = model.encode(texts, normalize_embeddings=True).tolist()
            answer_similarity = cosine(vectors[0], vectors[1])
            baseline_reference_similarity = cosine(vectors[0], vectors[2])
            candidate_reference_similarity = cosine(vectors[1], vectors[2])
            if candidate["error"] or not candidate["answer"]:
                category = "empty_or_failed"
            elif candidate["finish_reason"] == "length":
                category = "truncated"
            elif normalise(baseline["answer"]) == normalise(candidate["answer"]):
                category = "exact_same"
            elif (
                answer_similarity >= 0.88
                and abs(candidate["keyword_score"] - baseline["keyword_score"]) <= 0.125
            ):
                category = "semantically_equivalent"
            elif (
                candidate["keyword_score"] < 0.25
                and candidate_reference_similarity + 0.10 < baseline_reference_similarity
            ):
                category = "incorrect_candidate"
            else:
                category = "materially_different"
            comparisons.append(
                {
                    "id": candidate["id"],
                    "comparison": f"production_vs_{config_name}",
                    "category": category,
                    "answer_similarity": answer_similarity,
                    "baseline_reference_similarity": baseline_reference_similarity,
                    "candidate_reference_similarity": candidate_reference_similarity,
                    "keyword_difference": candidate["keyword_score"]
                    - baseline["keyword_score"],
                    "generated_token_difference": candidate["generated_tokens"]
                    - baseline["generated_tokens"],
                    "finish_reason_production": baseline["finish_reason"],
                    "finish_reason_candidate": candidate["finish_reason"],
                }
            )
    return comparisons


def percent_change(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline in (None, 0):
        return None
    return (candidate - baseline) / baseline * 100.0


def build_report(label: str, cases_path: Path, result_list: list[dict[str, Any]]) -> dict[str, Any]:
    results = {result["config"]["name"]: result for result in result_list}
    comparisons = semantic_comparisons(results)
    production = results["production"]
    baseline_summary = production["summary"]
    differences: dict[str, Any] = {}
    for name in ("no_repack", "no_repack_release"):
        summary = results[name]["summary"]
        pair = [row for row in comparisons if row["comparison"] == f"production_vs_{name}"]
        differences[name] = {
            "accuracy_difference": summary["accuracy"] - baseline_summary["accuracy"],
            "ram_reduction_percent": (
                production["memory"]["peak_rss_mib"] - results[name]["memory"]["peak_rss_mib"]
            )
            / production["memory"]["peak_rss_mib"]
            * 100.0,
            "generation_speed_difference_percent": percent_change(
                summary["generation_tokens_per_second"]["average"],
                baseline_summary["generation_tokens_per_second"]["average"],
            ),
            "prompt_speed_difference_percent": percent_change(
                summary["prompt_tokens_per_second"]["average"],
                baseline_summary["prompt_tokens_per_second"]["average"],
            ),
            "latency_difference_percent": percent_change(
                summary["total_latency_seconds"]["average"],
                baseline_summary["total_latency_seconds"]["average"],
            ),
            "answers_differ_percent": statistics.fmean(
                row["category"] != "exact_same" for row in pair
            )
            * 100.0,
            "semantic_equivalent_or_same_percent": statistics.fmean(
                row["category"] in {"exact_same", "semantically_equivalent"}
                for row in pair
            )
            * 100.0,
            "categories": dict(Counter(row["category"] for row in pair)),
        }

    no_repack = results["no_repack"]
    no_repack_diff = differences["no_repack"]
    if no_repack["memory"]["peak_rss_mib"] > COMPETITION_LIMIT_MIB:
        recommendation = "DO NOT ADOPT"
        reason = "No-repack exceeds the 7 GiB hard limit."
    elif (
        no_repack_diff["accuracy_difference"] < -0.03
        or no_repack_diff["semantic_equivalent_or_same_percent"] < 85.0
        or no_repack["summary"]["failures"] > 0
    ):
        recommendation = "DO NOT ADOPT"
        reason = "Measured quality or reliability degradation is too large."
    else:
        recommendation = "PROMISING - requires benchmark on actual ADTC laptop"
        reason = "It passes memory here, but this host is not the target laptop."

    eval_questions = len(json.loads(QA_PATH.read_text()))
    selected_questions = len(production["questions"])
    production_by_id = {row["id"]: row for row in production["questions"]}
    fairness = {
        "retrieval_hashes_match": all(
            row["retrieval_match"]
            for result in results.values()
            for row in result["questions"]
        ),
        "production_no_repack_prompt_hashes_match": all(
            row["prompt_hash"] == production_by_id[row["id"]]["prompt_hash"]
            for row in no_repack["questions"]
        ),
        "production_no_repack_question_ids_match": {
            row["id"] for row in production["questions"]
        }
        == {row["id"] for row in no_repack["questions"]},
    }
    two_arm_seconds_per_question = (
        production["summary"]["end_to_end_seconds"]["average"]
        + no_repack["summary"]["end_to_end_seconds"]["average"]
    )
    three_arm_seconds_per_question = two_arm_seconds_per_question + results[
        "no_repack_release"
    ]["summary"]["end_to_end_seconds"]["average"]

    payload = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label": label,
        "cases_path": str(cases_path.relative_to(PROJECT_ROOT)),
        "scope": {
            "evaluation_questions_available": eval_questions,
            "questions_run": selected_questions,
            "subjects": dict(Counter(row["subject"] for row in production["questions"])),
            "estimated_full_two_arm_hours": two_arm_seconds_per_question
            * eval_questions
            / 3600.0,
            "estimated_full_three_arm_hours": three_arm_seconds_per_question
            * eval_questions
            / 3600.0,
        },
        "fairness": fairness,
        "configurations": results,
        "comparisons": comparisons,
        "differences": differences,
        "recommendation": recommendation,
        "recommendation_reason": reason,
    }
    return payload


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def write_report(payload: dict[str, Any]) -> None:
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    results = payload["configurations"]
    production = results["production"]
    no_repack = results["no_repack"]
    metrics = [
        ("Questions", "questions"),
        ("Accuracy", "accuracy"),
        ("Successful generations", "successful_generations"),
        ("Failures", "failures"),
        ("Average generated tokens", ("generated_tokens", "average")),
        ("Median generated tokens", ("generated_tokens", "median")),
        ("Average generation tok/s", ("generation_tokens_per_second", "average")),
        ("Median generation tok/s", ("generation_tokens_per_second", "median")),
        ("Average prompt tok/s", ("prompt_tokens_per_second", "average")),
        ("Average TTFT seconds", ("time_to_first_token_seconds", "average")),
        ("Average latency seconds", ("total_latency_seconds", "average")),
        ("Peak RSS MiB", "peak_rss_mib"),
        ("Average RSS MiB", "average_rss_mib"),
        ("Model load seconds", "model_load_seconds"),
    ]

    def value(result: dict[str, Any], key: Any) -> Any:
        summary = result["summary"]
        if isinstance(key, tuple):
            return summary[key[0]][key[1]]
        return summary.get(key)

    lines = [
        "# Production vs no-repack controlled A/B benchmark",
        "",
        f"Label: **{payload['label']}**",
        "",
        "The same GGUF, frozen retrieved chunks, prompts, context, sampling controls, seed, batch/ubatch, CPU threads, and llama.cpp version were used. The only production/no-repack model-runtime difference is `use_extra_bufts`.",
        "",
        "## Scope and fairness",
        "",
        f"- Questions run: {payload['scope']['questions_run']} of {payload['scope']['evaluation_questions_available']}",
        f"- Subject allocation: `{json.dumps(payload['scope']['subjects'], sort_keys=True)}`",
        f"- Frozen retrieval hashes matched: {payload['fairness']['retrieval_hashes_match']}",
        f"- Production/no-repack prompt hashes matched: {payload['fairness']['production_no_repack_prompt_hashes_match']}",
        f"- Estimated full two-arm runtime on this VM: {payload['scope']['estimated_full_two_arm_hours']:.1f} hours",
        f"- Estimated full three-arm runtime on this VM: {payload['scope']['estimated_full_three_arm_hours']:.1f} hours",
        "",
        "## Primary comparison",
        "",
        "| Metric | Production | No-repack | Difference |",
        "|---|---:|---:|---:|",
    ]
    for label, key in metrics:
        left = value(production, key)
        right = value(no_repack, key)
        difference = right - left if isinstance(left, (int, float)) and isinstance(right, (int, float)) else None
        lines.append(f"| {label} | {fmt(left)} | {fmt(right)} | {fmt(difference)} |")

    lines += [
        "",
        "## Configuration table",
        "",
        "| Configuration | Peak RSS | RAM Headroom | Accuracy | Prompt tok/s | Generation tok/s | Avg tokens | Avg latency | ADTC status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name in ("production", "no_repack", "no_repack_release"):
        result = results[name]
        summary = result["summary"]
        lines.append(
            f"| {name} | {result['memory']['peak_rss_gib']:.3f} GiB | "
            f"{result['memory']['headroom_mib'] / 1024:.3f} GiB | {summary['accuracy']:.3f} | "
            f"{fmt(summary['prompt_tokens_per_second']['average'])} | "
            f"{fmt(summary['generation_tokens_per_second']['average'])} | "
            f"{fmt(summary['generated_tokens']['average'])} | "
            f"{fmt(summary['total_latency_seconds']['average'])} s | {result['memory']['status']} |"
        )

    release_summary = results["no_repack_release"]["summary"]
    lines += [
        "",
        "## Embedder release experiment",
        "",
        f"- Average RSS released after retrieval: {fmt(release_summary['embedder_release_rss_mib']['average'])} MiB",
        f"- Median RSS released after retrieval: {fmt(release_summary['embedder_release_rss_mib']['median'])} MiB",
        f"- Average sampled generation peak after release: {fmt(release_summary['generation_sampled_peak_rss_mib']['average'])} MiB",
        f"- Process peak includes the transient period when Gemma and the reloaded embedder coexist: {results['no_repack_release']['memory']['peak_rss_mib']:.3f} MiB",
        "- Releasing KEmbed per question requires reloading it for the next dense retrieval, so it lowers steady generation RSS but adds reload overhead and does not lower the observed process peak in this long-lived worker.",
    ]

    lines += [
        "",
        "## Per-question comparison",
        "",
        "| ID | Pair | Category | Similarity | Keyword Δ | Token Δ | Finish reasons |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in payload["comparisons"]:
        lines.append(
            f"| {row['id']} | {row['comparison']} | {row['category']} | "
            f"{row['answer_similarity']:.3f} | {row['keyword_difference']:+.3f} | "
            f"{row['generated_token_difference']:+d} | "
            f"{row['finish_reason_production']} / {row['finish_reason_candidate']} |"
        )

    lines += [
        "",
        "## Statistical differences",
        "",
    ]
    for name, difference in payload["differences"].items():
        lines += [
            f"### {name}",
            "",
            f"- Accuracy difference: {difference['accuracy_difference']:+.3f}",
            f"- RAM reduction: {difference['ram_reduction_percent']:.2f}%",
            f"- Generation speed difference: {fmt(difference['generation_speed_difference_percent'])}%",
            f"- Prompt speed difference: {fmt(difference['prompt_speed_difference_percent'])}%",
            f"- Latency difference: {fmt(difference['latency_difference_percent'])}%",
            f"- Answers different: {difference['answers_differ_percent']:.1f}%",
            f"- Same or semantically equivalent: {difference['semantic_equivalent_or_same_percent']:.1f}%",
            f"- Categories: `{json.dumps(difference['categories'], sort_keys=True)}`",
            "",
        ]

    lines += [
        "## Reproduction",
        "",
        "```bash",
        "cd /home/ubuntu/O-Level/O-Level",
        "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/benchmark_no_repack_ab.py --limit 8 --label representative",
        "```",
        "",
        "## Recommendation",
        "",
        f"**{payload['recommendation']}**",
        "",
        payload["recommendation_reason"],
        "",
        "No production configuration was changed.",
    ]
    OUTPUT_MD.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--label", default="representative")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--config", choices=CONFIGS, help=argparse.SUPPRESS)
    parser.add_argument("--cases", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

    if args.worker:
        result = run_worker(CONFIGS[args.config], args.cases, args.label)
        path = WORK_DIR / f"{args.label}_{args.config}.json"
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        return

    cases_path = prepare_cases(args.limit, args.label)
    results = [
        run_worker_subprocess(CONFIGS[name], cases_path, args.label)
        for name in ("production", "no_repack", "no_repack_release")
    ]
    payload = build_report(args.label, cases_path, results)
    write_report(payload)
    print(
        f"{payload['recommendation']}: {len(results[0]['questions'])} questions; "
        f"production={results[0]['memory']['peak_rss_gib']:.3f} GiB; "
        f"no_repack={results[1]['memory']['peak_rss_gib']:.3f} GiB"
    )


if __name__ == "__main__":
    main()
