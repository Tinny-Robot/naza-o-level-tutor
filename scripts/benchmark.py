"""Offline warm/cold benchmark for the O-Level tutor stack.

Run from the project root:

    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/benchmark.py

Uses fixed Study + General sample questions. Never downloads models.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import FLASH_ATTN, MODEL_NAME, SWA_FULL, TOP_K  # noqa: E402
from app.generation.llm import get_llm, reset_llm_singleton  # noqa: E402
from app.generation.pipeline import GenerationPipeline  # noqa: E402
from app.generation.prompt_manager import get_prompt_manager, reset_prompt_manager  # noqa: E402
from app.generation.rag import RetrievalService  # noqa: E402
from app.ingestion.embedder import get_embedder, reset_embedder_singleton  # noqa: E402
from app.retrieval.search import get_retriever, reset_retriever  # noqa: E402
from app.utils.offline import enable_offline_mode, run_self_check  # noqa: E402
from app.utils.runtime import peak_rss_mb, rss_mb  # noqa: E402

SAMPLE_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("study", "Explain Ohm's law and give the formula."),
    ("study", "What is subject-verb concord?"),
    ("general", "Hello, how are you?"),
    ("general", "Give me three tips for staying focused while studying."),
)


def _tokens_generated(llm: Any, answer: str) -> int:
    last = getattr(llm, "last_gen_tokens", None)
    if isinstance(last, int) and last > 0:
        return last
    count_tokens = getattr(llm, "count_tokens", None)
    if callable(count_tokens):
        try:
            return int(count_tokens(answer or ""))
        except Exception:  # noqa: BLE001
            return 0
    return 0


def _reset_singletons() -> None:
    reset_llm_singleton()
    reset_prompt_manager()
    reset_embedder_singleton()
    reset_retriever()


def _warm_pipeline() -> tuple[GenerationPipeline, float, float, float, float]:
    """Load embedder + LLM + prompts + retriever; return pipeline, timings, Ready RSS."""
    t_all = time.perf_counter()

    t0 = time.perf_counter()
    prompts = get_prompt_manager()
    prompt_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    embedder = get_embedder()
    _ = embedder.model
    embed_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    llm = get_llm()
    llm_s = time.perf_counter() - t0

    retriever = get_retriever()
    retriever.embedder = embedder
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=retriever),
        llm=llm,
        prompts=prompts,
    )
    total_s = time.perf_counter() - t_all
    ready_rss = rss_mb()
    return (
        pipeline,
        embed_s,
        llm_s,
        total_s if total_s else (embed_s + llm_s + prompt_s),
        ready_rss,
    )


def _run_questions(pipeline: GenerationPipeline) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for expected_mode, question in SAMPLE_QUESTIONS:
        t0 = time.perf_counter()
        result = pipeline.ask(question, top_k=TOP_K)
        latency = time.perf_counter() - t0
        answer = result.get("answer") or ""
        tokens = _tokens_generated(pipeline.llm, answer)
        tps = (tokens / latency) if latency > 0 and tokens > 0 else 0.0
        rows.append(
            {
                "expected_mode": expected_mode,
                "mode": result.get("mode"),
                "question": question,
                "latency_s": latency,
                "tokens": tokens,
                "tokens_per_s": tps,
                "confidence": float(result.get("confidence") or 0.0),
                "memory_mb": rss_mb(),
                "answer_preview": (answer or "").replace("\n", " ")[:120],
            }
        )
    return rows


def _mode_stats(rows: list[dict[str, Any]], mode: str) -> dict[str, float]:
    subset = [r for r in rows if r.get("mode") == mode or r.get("expected_mode") == mode]
    if not subset:
        return {"count": 0, "avg_latency_s": 0.0, "avg_tps": 0.0}
    latencies = [r["latency_s"] for r in subset]
    tps = [r["tokens_per_s"] for r in subset if r["tokens_per_s"] > 0]
    return {
        "count": float(len(subset)),
        "avg_latency_s": statistics.mean(latencies),
        "avg_tps": statistics.mean(tps) if tps else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="O-Level offline tutor benchmark")
    parser.add_argument(
        "--single-pass",
        action="store_true",
        help="Warm-start once, then run sample questions once (skip cold+warm double ask).",
    )
    args = parser.parse_args()

    enable_offline_mode()
    check = run_self_check()
    print("\n".join(check.format_lines()))
    print()
    if not check.ok:
        print("Benchmark aborted: startup self-check failed.", file=sys.stderr)
        sys.exit(1)

    print(f"O-Level offline benchmark ({MODEL_NAME})")
    print(f"llama.cpp knobs: FLASH_ATTN={FLASH_ATTN} SWA_FULL={SWA_FULL}")
    print("=" * 40)

    # --- Cold start: clear singletons, then first load ---
    _reset_singletons()
    mem_before = rss_mb()
    t_cold = time.perf_counter()
    pipeline, embed_load_s, llm_load_s, model_load_s, ready_rss = _warm_pipeline()

    if args.single_pass:
        cold_rows: list[dict[str, Any]] = []
        cold_total_s = time.perf_counter() - t_cold
        cold_first = 0.0
        t_warm = time.perf_counter()
        warm_rows = _run_questions(pipeline)
        warm_total_s = time.perf_counter() - t_warm
    else:
        cold_rows = _run_questions(pipeline)
        cold_total_s = time.perf_counter() - t_cold
        cold_first = cold_rows[0]["latency_s"] if cold_rows else 0.0
        # --- Warm start: already loaded; re-run the same questions ---
        t_warm = time.perf_counter()
        warm_rows = _run_questions(pipeline)
        warm_total_s = time.perf_counter() - t_warm

    warm_latencies = [r["latency_s"] for r in warm_rows]
    warm_tps = [r["tokens_per_s"] for r in warm_rows if r["tokens_per_s"] > 0]
    mem_after = rss_mb()
    peak = peak_rss_mb()

    avg_latency = statistics.mean(warm_latencies) if warm_latencies else 0.0
    avg_tps = statistics.mean(warm_tps) if warm_tps else 0.0
    study = _mode_stats(warm_rows, "study")
    general = _mode_stats(warm_rows, "general")

    print()
    print("Model load")
    print(f"  Embedding load: {embed_load_s:.2f}s")
    print(f"  Gemma GGUF load: {llm_load_s:.2f}s")
    print(f"  Total warm-start load: {model_load_s:.2f}s")
    print()
    if not args.single_pass:
        print("Cold start")
        print(f"  End-to-end (load + sample asks): {cold_total_s:.2f}s")
        print(f"  First ask latency: {cold_first:.2f}s")
        print()
    print("Ask pass" if args.single_pass else "Warm start")
    print(f"  Sample asks wall time: {warm_total_s:.2f}s")
    print(f"  Avg latency: {avg_latency:.2f}s")
    print(f"  Avg tokens/sec: {avg_tps:.1f}")
    print(f"  Study avg latency: {study['avg_latency_s']:.2f}s  "
          f"({int(study['count'])} q)  avg t/s={study['avg_tps']:.1f}")
    print(f"  General avg latency: {general['avg_latency_s']:.2f}s  "
          f"({int(general['count'])} q)  avg t/s={general['avg_tps']:.1f}")
    print()
    print("Memory")
    print(f"  RSS before load: {mem_before:.0f} MB")
    print(f"  Ready RSS (after warm-start, before asks): {ready_rss:.0f} MB")
    print(f"  Peak RSS (ru_maxrss): {peak:.0f} MB")
    print(f"  RSS after warm asks: {mem_after:.0f} MB")
    print()
    print("Per-question")
    for row in warm_rows:
        print(
            f"  [{row['mode']}] {row['latency_s']:.2f}s  "
            f"{row['tokens']} tok  {row['tokens_per_s']:.1f} t/s  "
            f"q={row['question'][:48]!r}"
        )
        print(f"    preview: {row['answer_preview']}")
    print("=" * 40)


if __name__ == "__main__":
    main()
