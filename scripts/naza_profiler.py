"""Naza Profiler - performance (Sperf) and efficiency (Seff) benchmark.

Exercises the production GenerationPipeline without modifying app code, models,
prompts, or RAG data. Writes raw JSON + markdown and prints the submission block.

    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/naza_profiler.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import statistics
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from types import MethodType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import (  # noqa: E402
    MAX_CONTEXT_TOKENS,
    MODEL_NAME,
    MODEL_PATH,
    TOP_K,
)
from app.generation.llm import LlamaCppLLM, get_llm, strip_reasoning  # noqa: E402
from app.generation.pipeline import GenerationPipeline  # noqa: E402
from app.generation.prompt_manager import get_prompt_manager  # noqa: E402
from app.generation.rag import RetrievalService  # noqa: E402
from app.ingestion.embedder import get_embedder  # noqa: E402
from app.retrieval.search import get_retriever  # noqa: E402
from app.utils.offline import enable_offline_mode, run_self_check  # noqa: E402

PROMPTS_PATH = PROJECT_ROOT / "data/benchmarks/naza_profiler_prompts.json"
BENCHMARK_DIR = PROJECT_ROOT / "data/benchmarks"
DETERMINISTIC_SEED = 2026
DEFAULT_SAMPLE_INTERVAL_S = 0.05
COMPETITION_RAM_MIB = 7168  # 7 GiB ADTC reference

EFFICIENCY_PROBES: tuple[dict[str, Any], ...] = (
    {
        "id": "eff-study-01",
        "prompt": "Explain Ohm's law and give the formula.",
        "language": "English",
        "subject": "physics",
        "topic": "Electricity & Magnetism",
    },
    {
        "id": "eff-study-02",
        "prompt": "What is subject-verb concord?",
        "language": "English",
        "subject": "english",
        "topic": "Lexis & Structure",
    },
    {
        "id": "eff-general-01",
        "prompt": "Hello, how are you?",
        "language": "English",
    },
    {
        "id": "eff-general-02",
        "prompt": "Give me three tips for staying focused while studying.",
        "language": "English",
    },
    {
        "id": "eff-hausa-01",
        "prompt": "Bayani game da dokar Ohm a Physics na WAEC.",
        "language": "Hausa",
        "subject": "physics",
        "topic": "Electricity & Magnetism",
    },
    {
        "id": "eff-tutor-01",
        "prompt": "Walk me through solving 2x + 5 = 17 step by step.",
        "language": "English",
        "subject": "mathematics",
        "topic": "Algebra",
    },
)

WARMUP_PROMPTS: tuple[tuple[str, str | None], ...] = (
    ("Hello", None),
    ("Explain Ohm's law briefly.", "English"),
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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
    expected_subject = (subject or "").strip().lower()
    keywords = [
        str(keyword).strip().lower()
        for keyword in expected_keywords
        if str(keyword).strip()
    ]
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


class CpuSampler:
    """Sample process CPU % via /proc/stat deltas during a window."""

    def __init__(self, interval_s: float = DEFAULT_SAMPLE_INTERVAL_S) -> None:
        self.interval_s = interval_s
        self.samples_pct: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._available = Path("/proc/stat").is_file()

    @staticmethod
    def _read_jiffies() -> tuple[int, int] | None:
        try:
            stat_line = Path("/proc/self/stat").read_text().split("\n", 1)[0]
            parts = stat_line.split()
            utime = int(parts[13])
            stime = int(parts[14])
            with Path("/proc/stat").open() as handle:
                cpu = handle.readline().split()
            total = sum(int(x) for x in cpu[1:])
            return utime + stime, total
        except (OSError, ValueError, IndexError):
            return None

    def _run(self) -> None:
        prev = self._read_jiffies()
        while not self._stop.is_set():
            self._stop.wait(self.interval_s)
            cur = self._read_jiffies()
            if prev and cur:
                proc_delta = cur[0] - prev[0]
                total_delta = cur[1] - prev[1]
                if total_delta > 0:
                    ncpu = os.cpu_count() or 1
                    pct = 100.0 * proc_delta / total_delta / ncpu
                    self.samples_pct.append(min(100.0, max(0.0, pct)))
            prev = cur

    def __enter__(self) -> CpuSampler:
        if self._available:
            self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        if self._available:
            self._thread.join(timeout=2)

    def average(self) -> float | None:
        if not self.samples_pct:
            return None
        return statistics.fmean(self.samples_pct)


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
        "ram_total_gib": mem_total_kib / (1024**2),
        "platform": platform.platform(),
    }


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


def _disable_student_writes() -> None:
    try:
        from app.student.updater import LearningProfileUpdater

        LearningProfileUpdater.apply_event = lambda self, event: None
    except Exception:
        pass


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
            }
        )
        return answer

    llm.generate = MethodType(measured_generate, llm)


def _extract_answer_text(result: dict[str, Any]) -> str:
    if result.get("type") == "lesson":
        parts: list[str] = [str(result.get("answer") or "")]
        parts.append(str(result.get("introduction") or ""))
        for section in result.get("sections") or []:
            if isinstance(section, dict):
                parts.append(str(section.get("heading") or ""))
                parts.append(str(section.get("body") or ""))
            else:
                parts.append(str(getattr(section, "heading", "") or ""))
                parts.append(str(getattr(section, "body", "") or ""))
        worked = result.get("worked_example") or {}
        if isinstance(worked, dict):
            parts.extend(str(x) for x in worked.get("steps") or [])
        return "\n".join(p for p in parts if p).strip()
    return str(result.get("answer") or "")


def _has_step_pattern(text: str) -> bool:
    if re.search(r"\bstep\s+\d+\b", text, re.IGNORECASE):
        return True
    if re.search(r"\bfirst\b.*\bsecond\b", text, re.IGNORECASE):
        return True
    if re.search(r"^\s*\d+[\).\]]\s+", text, re.MULTILINE):
        return True
    return False


def _sentence_repeats(text: str) -> bool:
    sentences = [s.strip().lower() for s in re.split(r"[.!?]+", text) if s.strip()]
    return len(sentences) != len(set(sentences))


def _latin_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for ch in letters if ord(ch) < 128)
    return latin / len(letters)


def _score_accuracy(item: dict[str, Any], result: dict[str, Any], answer: str) -> float:
    rubric = item["rubric_type"]
    if rubric == "qa_keywords":
        kw = _keyword_score(answer, item.get("expected_keywords") or [])
        ref = item.get("reference_answer") or ""
        exact = 1.0 if ref and _normalise(answer) == _normalise(ref) else 0.0
        return 0.7 * kw + 0.3 * exact
    if rubric == "refusal":
        return 1.0 if result.get("refused") else 0.0
    if rubric == "lesson_structure":
        sections = result.get("sections") or []
        nonempty = sum(
            1
            for s in sections
            if (s.get("body") if isinstance(s, dict) else getattr(s, "body", ""))
        )
        if result.get("type") == "lesson" and nonempty >= 3:
            return 1.0
        return _clamp(nonempty / 3.0, 0.0, 1.0)
    if rubric == "general_quality":
        return _clamp(len(answer) / 80.0, 0.0, 1.0)
    if rubric == "tutor_steps":
        keywords = item.get("expected_keywords") or []
        if keywords:
            kw = _keyword_score(answer, keywords)
            return 0.7 * kw + 0.3 * (1.0 if _has_step_pattern(answer) else 0.0)
        return _clamp(len(answer) / 80.0, 0.0, 1.0)
    if rubric == "language_hausa":
        return _clamp(len(answer) / 40.0, 0.0, 1.0)
    return _clamp(len(answer) / 80.0, 0.0, 1.0)


def _score_tutor(item: dict[str, Any], result: dict[str, Any], answer: str) -> float:
    score = 1.0
    if not answer.strip():
        score -= 0.25
    if "[Chunk" in answer:
        score -= 0.25
    if item.get("expects_steps") and not _has_step_pattern(answer):
        score -= 0.25
    mode = result.get("mode")
    if mode == "study" and not result.get("refused") and len(answer) < 120:
        score -= 0.25
    return max(0.0, score)


def _score_language(item: dict[str, Any], answer: str) -> float:
    rubric = item["rubric_type"]
    lang = item.get("language", "English")
    if rubric == "language_hausa" or lang == "Hausa":
        markers = item.get("hausa_markers") or []
        hits = sum(1 for m in markers if re.search(rf"\b{re.escape(m)}\b", answer, re.IGNORECASE))
        if hits >= 2:
            return 1.0
        if hits == 1:
            return 0.6
        if _latin_ratio(answer) >= 0.95 and len(answer) > 80:
            return 0.2
        return 0.4
    ratio = _latin_ratio(answer)
    return _clamp(ratio / 0.9, 0.0, 1.0)


def _score_hallucination(
    item: dict[str, Any], result: dict[str, Any], answer: str
) -> float:
    if item.get("expects_refusal"):
        return 1.0 if result.get("refused") else 0.0
    category = item.get("category", "")
    if category in {"syllabus", "reasoning", "language_hausa"}:
        retrieved = result.get("retrieved_chunks") or []
        relevances = _label_relevances(
            retrieved,
            subject=str(item.get("subject") or ""),
            expected_keywords=item.get("expected_keywords") or [],
        )
        hit = any(relevances)
        if result.get("refused"):
            return 0.5 if hit else 0.0
        return 1.0 if hit else 0.5
    if result.get("refused"):
        return 0.5
    return 1.0 if answer.strip() else 0.0


def _score_clarity(answer: str) -> float:
    words = len(answer.split())
    base = min(1.0, words / 80.0)
    penalty = 0.2 if _sentence_repeats(answer) else 0.0
    return max(0.0, base * (1.0 - penalty))


def _score_prompt(item: dict[str, Any], result: dict[str, Any], answer: str) -> dict[str, float]:
    a = _score_accuracy(item, result, answer)
    t = _score_tutor(item, result, answer)
    l = _score_language(item, answer)
    h = _score_hallucination(item, result, answer)
    c = _score_clarity(answer)
    total = 100.0 * (0.40 * a + 0.25 * t + 0.15 * l + 0.10 * h + 0.10 * c)
    return {
        "accuracy": a,
        "tutor_quality": t,
        "language": l,
        "anti_hallucination": h,
        "clarity": c,
        "prompt_score": total,
    }


def _aggregate_generation_measurements(
    generation_measurements: list[dict[str, Any]], before: int
) -> dict[str, Any]:
    slice_ = generation_measurements[before:]
    if not slice_:
        return {
            "prompt_tokens": 0,
            "generated_tokens": 0,
            "prompt_tokens_per_second": None,
            "generation_tokens_per_second": None,
            "time_to_first_token_seconds": None,
            "total_latency_seconds": None,
            "llm_calls": 0,
        }
    prompt_tokens = sum(int(m.get("prompt_tokens") or 0) for m in slice_)
    generated_tokens = sum(int(m.get("generated_tokens") or 0) for m in slice_)
    ttfts = [m["time_to_first_token_seconds"] for m in slice_ if m.get("time_to_first_token_seconds")]
    gen_tps = [
        m["generation_tokens_per_second"]
        for m in slice_
        if m.get("generation_tokens_per_second")
    ]
    total_lat = sum(float(m.get("total_latency_seconds") or 0.0) for m in slice_)
    return {
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "prompt_tokens_per_second": statistics.fmean(gen_tps) if gen_tps else None,
        "generation_tokens_per_second": statistics.fmean(gen_tps) if gen_tps else None,
        "time_to_first_token_seconds": statistics.fmean(ttfts) if ttfts else None,
        "total_latency_seconds": total_lat,
        "llm_calls": len(slice_),
    }


def _ask_pipeline(
    pipeline: GenerationPipeline,
    generation_measurements: list[dict[str, Any]],
    *,
    prompt: str,
    language: str | None = None,
    subject: str | None = None,
    topic: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    before = len(generation_measurements)
    started = time.perf_counter()
    error: str | None = None
    try:
        kwargs: dict[str, Any] = {"language": language}
        if subject:
            kwargs["subject"] = subject
        if topic:
            kwargs["topic"] = topic
        result = pipeline.ask(prompt, top_k=TOP_K, **kwargs)
    except Exception as exc:
        result = {"type": "chat", "mode": "general", "answer": "", "refused": True}
        error = f"{type(exc).__name__}: {exc}"
    wall = time.perf_counter() - started
    metrics = _aggregate_generation_measurements(generation_measurements, before)
    metrics["wall_latency_seconds"] = wall
    metrics["error"] = error
    answer = _extract_answer_text(result)
    return result, metrics, wall


def _compute_seff(
    *,
    avg_ttft: float | None,
    avg_tps: float | None,
    avg_latency: float | None,
    peak_rss_mib: float,
    model_load_s: float,
) -> dict[str, Any]:
    ttft_score = (
        100.0 * _clamp(1.0 - (avg_ttft - 5.0) / (90.0 - 5.0), 0.0, 1.0)
        if avg_ttft is not None
        else 0.0
    )
    tps_score = (
        100.0 * _clamp((avg_tps - 1.0) / (8.0 - 1.0), 0.0, 1.0)
        if avg_tps is not None
        else 0.0
    )
    latency_score = (
        100.0 * _clamp(1.0 - (avg_latency - 45.0) / (240.0 - 45.0), 0.0, 1.0)
        if avg_latency is not None
        else 0.0
    )
    ram_score = 100.0 * _clamp((COMPETITION_RAM_MIB - peak_rss_mib) / COMPETITION_RAM_MIB, 0.0, 1.0)
    load_score = 100.0 * _clamp(1.0 - (model_load_s - 15.0) / (90.0 - 15.0), 0.0, 1.0)
    seff = 0.25 * ttft_score + 0.25 * tps_score + 0.20 * latency_score + 0.20 * ram_score + 0.10 * load_score
    return {
        "seff": seff,
        "subscores": {
            "ttft": ttft_score,
            "generation_tps": tps_score,
            "total_latency": latency_score,
            "ram_headroom": ram_score,
            "model_load": load_score,
        },
        "anchors": {
            "ttft": "100 at <=5s, 0 at >=90s",
            "generation_tps": "100 at >=8 tok/s, 0 at <=1 tok/s",
            "total_latency": "100 at <=45s, 0 at >=240s",
            "ram_headroom": f"100 * clamp((7168 - peak_mib) / 7168, 0, 1)",
            "model_load": "100 at <=15s, 0 at >=90s",
        },
        "weights": {"ttft": 0.25, "generation_tps": 0.25, "total_latency": 0.20, "ram_headroom": 0.20, "model_load": 0.10},
    }


def _load_prompt_suite(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    prompts = data.get("prompts") or data
    if not isinstance(prompts, list):
        raise ValueError("Invalid prompt suite format")
    return prompts


def _validate_qa_refs(prompts: list[dict[str, Any]]) -> None:
    from app.config import QA_PATH

    qa = {item["id"]: item for item in json.loads(QA_PATH.read_text())}
    for item in prompts:
        ref = item.get("qa_ref")
        if not ref:
            continue
        if ref not in qa:
            raise ValueError(f"Missing qa_ref {ref} for prompt {item['id']}")
        source = qa[ref]
        if not item.get("expected_keywords"):
            item["expected_keywords"] = source.get("expected_keywords") or []
        if not item.get("reference_answer"):
            item["reference_answer"] = source.get("answer") or ""


def run_profiler(*, efficiency_reps: int, output_dir: Path) -> dict[str, Any]:
    enable_offline_mode()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    _disable_student_writes()
    check = run_self_check()
    print("\n".join(check.format_lines()))
    if not check.ok:
        raise RuntimeError("Startup self-check failed")

    prompts = _load_prompt_suite(PROMPTS_PATH)
    _validate_qa_refs(prompts)
    if len(prompts) < 30:
        raise RuntimeError(f"Prompt suite has {len(prompts)} items; need at least 30")

    generation_measurements: list[dict[str, Any]] = []
    performance_rows: list[dict[str, Any]] = []
    efficiency_rows: list[dict[str, Any]] = []
    warmup_count = 0

    with MemorySampler() as memory_sampler, CpuSampler() as cpu_sampler:
        t0 = time.perf_counter()
        pm = get_prompt_manager()
        prompt_load_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        embedder = get_embedder()
        _ = embedder.model
        embed_load_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        llm = get_llm()
        model_load_s = time.perf_counter() - t0
        _instrument_generation(llm, generation_measurements)

        t0 = time.perf_counter()
        retriever = get_retriever()
        retriever.embedder = embedder
        retriever_load_s = time.perf_counter() - t0

        pipeline = GenerationPipeline(
            retrieval=RetrievalService(retriever=retriever),
            llm=llm,
            prompts=pm,
            max_context_tokens=MAX_CONTEXT_TOKENS,
        )

        print("\nWarmup (discarded)...")
        for text, lang in WARMUP_PROMPTS:
            before = len(generation_measurements)
            pipeline.ask(text, language=lang, top_k=TOP_K)
            warmup_count += 1
            generation_measurements[:] = generation_measurements[:before]

        print(f"\nPerformance pass ({len(prompts)} prompts)...")
        for index, item in enumerate(prompts, 1):
            print(f"  [{index}/{len(prompts)}] {item['id']} ...", flush=True)
            result, metrics, wall = _ask_pipeline(
                pipeline,
                generation_measurements,
                prompt=item["prompt"],
                language=item.get("language"),
                subject=item.get("subject"),
                topic=item.get("topic"),
            )
            answer = _extract_answer_text(result)
            scores = _score_prompt(item, result, answer)
            performance_rows.append(
                {
                    "id": item["id"],
                    "category": item.get("category"),
                    "rubric_type": item.get("rubric_type"),
                    "language": item.get("language"),
                    "prompt": item["prompt"],
                    "answer_preview": answer[:400],
                    "mode": result.get("mode") or result.get("type"),
                    "refused": bool(result.get("refused")),
                    "scores": scores,
                    "metrics": metrics,
                    "wall_latency_seconds": wall,
                }
            )

        print(f"\nEfficiency pass ({len(EFFICIENCY_PROBES)} probes x {efficiency_reps} reps)...")
        for probe in EFFICIENCY_PROBES:
            for rep in range(1, efficiency_reps + 1):
                print(f"  {probe['id']} rep {rep}/{efficiency_reps} ...", flush=True)
                result, metrics, wall = _ask_pipeline(
                    pipeline,
                    generation_measurements,
                    prompt=probe["prompt"],
                    language=probe.get("language"),
                    subject=probe.get("subject"),
                    topic=probe.get("topic"),
                )
                efficiency_rows.append(
                    {
                        "probe_id": probe["id"],
                        "rep": rep,
                        "metrics": metrics,
                        "wall_latency_seconds": wall,
                        "mode": result.get("mode") or result.get("type"),
                    }
                )

        memory_summary = memory_sampler.summary()
        cpu_avg = cpu_sampler.average()

    peak_rss_mib = float(_status_memory().get("vmhwm_mib") or 0.0)
    prompt_scores = [row["scores"]["prompt_score"] for row in performance_rows]
    sperf = statistics.fmean(prompt_scores) if prompt_scores else 0.0

    accuracy_pct = 100.0 * statistics.fmean(row["scores"]["accuracy"] for row in performance_rows)
    tutor_pct = 100.0 * statistics.fmean(row["scores"]["tutor_quality"] for row in performance_rows)
    lang_rows = [
        row
        for row in performance_rows
        if row["language"] == "Hausa"
        or row["category"] == "language_hausa"
        or row["rubric_type"] == "language_english"
        or row["language"] == "English"
    ]
    lang_pct = 100.0 * statistics.fmean(row["scores"]["language"] for row in lang_rows)
    perf_latency_avg = statistics.fmean(row["wall_latency_seconds"] for row in performance_rows)

    eff_ttft = [row["metrics"]["time_to_first_token_seconds"] for row in efficiency_rows]
    eff_tps = [row["metrics"]["generation_tokens_per_second"] for row in efficiency_rows]
    eff_wall = [row["wall_latency_seconds"] for row in efficiency_rows]
    avg_ttft = statistics.fmean([x for x in eff_ttft if x is not None]) if any(eff_ttft) else None
    avg_tps = statistics.fmean([x for x in eff_tps if x is not None]) if any(eff_tps) else None
    avg_eff_latency = statistics.fmean(eff_wall) if eff_wall else None

    seff_info = _compute_seff(
        avg_ttft=avg_ttft,
        avg_tps=avg_tps,
        avg_latency=avg_eff_latency,
        peak_rss_mib=peak_rss_mib,
        model_load_s=model_load_s,
    )

    total_runs = warmup_count + len(performance_rows) + len(efficiency_rows)
    hardware = _cpu_info()
    hardware_str = (
        f"{hardware['cpu_model']}, {hardware['logical_cpus']} CPUs, "
        f"{hardware['ram_total_gib']:.1f} GiB RAM, {hardware['platform']}"
    )

    result = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": {
            "name": MODEL_NAME,
            "path": str(MODEL_PATH),
            "quantization": "GGUF Q4_K_M",
        },
        "hardware": hardware,
        "load_times_seconds": {
            "prompt_manager": prompt_load_s,
            "embedding": embed_load_s,
            "model": model_load_s,
            "retriever": retriever_load_s,
        },
        "memory": {
            "peak_rss_mib": peak_rss_mib,
            "peak_rss_gib": peak_rss_mib / 1024.0,
            "competition_limit_mib": COMPETITION_RAM_MIB,
            **memory_summary,
        },
        "cpu_utilization_percent": cpu_avg,
        "gpu_utilization": "N/A (n_gpu_layers=0)",
        "sperf": {
            "score": sperf,
            "formula": "mean(prompt_score) where prompt_score = 100*(0.40*A + 0.25*T + 0.15*L + 0.10*H + 0.10*C)",
            "breakdown_percent": {
                "accuracy_correctness": accuracy_pct,
                "tutor_quality": tutor_pct,
                "hausa_english_performance": lang_pct,
            },
            "average_latency_seconds": perf_latency_avg,
        },
        "seff": seff_info,
        "efficiency_measured": {
            "average_ttft_seconds": avg_ttft,
            "average_generation_speed_tok_s": avg_tps,
            "average_total_latency_seconds": avg_eff_latency,
            "peak_ram_gib": peak_rss_mib / 1024.0,
            "cpu_utilization_percent": cpu_avg,
        },
        "benchmark": {
            "performance_prompts": len(prompts),
            "efficiency_probes": len(EFFICIENCY_PROBES),
            "efficiency_reps": efficiency_reps,
            "warmup_runs": warmup_count,
            "total_runs": total_runs,
        },
        "performance_rows": performance_rows,
        "efficiency_rows": efficiency_rows,
    }
    return result


def _format_report(result: dict[str, Any]) -> str:
    sperf = result["sperf"]["score"]
    seff = result["seff"]["seff"]
    bd = result["sperf"]["breakdown_percent"]
    eff = result["efficiency_measured"]
    bench = result["benchmark"]
    hw = result["hardware"]
    cpu = eff["cpu_utilization_percent"]
    cpu_str = f"{cpu:.1f}%" if cpu is not None else "unavailable"

    lines = [
        "## Naza Profiler Results",
        "",
        f"Sperf: {sperf:.1f}/100",
        f"Seff: {seff:.1f}/100",
        "",
        "Performance:",
        f"* Accuracy/correctness: {bd['accuracy_correctness']:.1f}%",
        f"* Tutor quality: {bd['tutor_quality']:.1f}%",
        f"* Hausa/English performance: {bd['hausa_english_performance']:.1f}%",
        f"* Average latency: {result['sperf']['average_latency_seconds']:.1f} s",
        "",
        "Efficiency:",
        f"* Average TTFT: {eff['average_ttft_seconds']:.1f} s"
        if eff["average_ttft_seconds"] is not None
        else "* Average TTFT: unavailable",
        f"* Average generation speed: {eff['average_generation_speed_tok_s']:.2f} tok/s"
        if eff["average_generation_speed_tok_s"] is not None
        else "* Average generation speed: unavailable",
        f"* Average total latency: {eff['average_total_latency_seconds']:.1f} s"
        if eff["average_total_latency_seconds"] is not None
        else "* Average total latency: unavailable",
        f"* Peak RAM: {eff['peak_ram_gib']:.2f} GB",
        f"* CPU utilization: {cpu_str}",
        "",
        "Benchmark:",
        f"* Number of prompts: {bench['performance_prompts']}",
        f"* Number of runs: {bench['total_runs']}",
        f"* Model: {result['model']['name']}",
        f"* Hardware: {hw['cpu_model']}, {hw['logical_cpus']} CPUs, {hw['ram_total_gib']:.1f} GiB RAM",
        "",
        "### Score methodology",
        "",
        "**Sperf** = arithmetic mean of 36 per-prompt scores (0–100). Each prompt:",
        "`100 × (0.40×Accuracy + 0.25×TutorQuality + 0.15×Language + 0.10×AntiHallucination + 0.10×Clarity)`.",
        "Accuracy uses keyword recall + exact match (qa items), refusal (traps), lesson section count, or answer length.",
        "",
        "**Seff** = weighted sum of anchor-normalized subscores:",
        "25% TTFT (5s→100, 90s→0), 25% gen tok/s (8→100, 1→0), 20% wall latency (45s→100, 240s→0),",
        "20% RAM headroom vs 7 GiB, 10% model load (15s→100, 90s→0).",
        "Efficiency metrics averaged over 6 probe prompts × 3 repetitions.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Naza Profiler benchmark")
    parser.add_argument("--efficiency-reps", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=BENCHMARK_DIR)
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    args.output_dir.mkdir(parents=True, exist_ok=True)

    result = run_profiler(efficiency_reps=args.efficiency_reps, output_dir=args.output_dir)

    json_path = args.output_dir / f"naza_profiler_{stamp}.json"
    md_path = args.output_dir / f"naza_profiler_{stamp}.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n")

    report = _format_report(result)
    md_path.write_text(report + "\n")
    print("\n" + report)
    print(f"\nArtifacts: {json_path}\n           {md_path}")


if __name__ == "__main__":
    main()
