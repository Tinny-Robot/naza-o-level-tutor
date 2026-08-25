"""CLI entry point: interactive offline RAG Q&A over the O-Level corpus.

Run from the project root:

    python scripts/ask.py

Requires a Gemma 4 E4B-it IQ3_M GGUF at MODEL_PATH (default
``model/gemma-4-E4B-it-IQ3_M.gguf``), a local embedding snapshot at
``EMBEDDING_MODEL_PATH``, and a built index (see scripts/ingest.py /
scripts/build_index.py). The app never downloads model weights.

Questions are routed offline to Study mode (RAG) or General Conversation
(same local Gemma, no retrieval).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import MODEL_NAME, TOP_K  # noqa: E402
from app.generation.llm import get_llm  # noqa: E402
from app.generation.pipeline import GenerationPipeline  # noqa: E402
from app.generation.prompt_manager import get_prompt_manager  # noqa: E402
from app.generation.rag import RetrievalService  # noqa: E402
from app.ingestion.embedder import get_embedder  # noqa: E402
from app.retrieval.search import get_retriever  # noqa: E402
from app.utils.logging import get_logger  # noqa: E402
from app.utils.offline import enable_offline_mode, run_self_check  # noqa: E402
from app.utils.runtime import RssStageLogger, rss_mb  # noqa: E402

logger = get_logger(__name__)


def format_citations(citations: list[dict[str, Any]]) -> str:
    """Format citation records for terminal display."""
    if not citations:
        return "Citations: (none)"
    lines = ["Citations:"]
    for i, cite in enumerate(citations, start=1):
        score = cite.get("score")
        score_str = f"{score:.4f}" if isinstance(score, (int, float)) else "N/A"
        lines.append(
            f"  [{i}] chunk_id={cite.get('chunk_id')}  "
            f"subject={cite.get('subject')}  topic={cite.get('topic')}  "
            f"source={cite.get('source')}  score={score_str}"
        )
    return "\n".join(lines)


def _mode_label(mode: str) -> str:
    if mode == "study":
        return "Study"
    if mode == "general":
        return "General Conversation"
    return mode


def print_banner() -> None:
    """Print the offline tutor banner."""
    print("==============================")
    print("O-Level AI Tutor")
    print("Offline Ready ✓")
    print(f"Model: {MODEL_NAME}")
    print("Mode: Auto (Study / General)")
    print("==============================")


def warm_start() -> GenerationPipeline:
    """Eagerly load embedder, prompts, LLM, and retriever once."""
    print("Warm-starting models (one-time load)...")
    stages = RssStageLogger()
    stages.mark("1_process_start")

    prompts = get_prompt_manager()
    stages.mark("2_prompt_manager")

    embedder = get_embedder()
    _ = embedder.model
    stages.mark("3_embedding_model")

    llm = get_llm()
    stages.mark("4_gguf_loaded")
    # llama.cpp allocates the KV cache inside Llama(); same RSS sample.
    stages.mark("5_kv_cache_init")

    retriever = get_retriever()
    # Share the warmed embedder with the retriever when possible.
    if getattr(retriever, "embedder", None) is not None:
        retriever.embedder = embedder
    stages.mark("6_faiss_index")

    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=retriever),
        llm=llm,
        prompts=prompts,
    )
    stages.mark("7_generation_pipeline")
    print()
    print(stages.summary_table())
    print()
    print(f"Ready. RSS ≈ {rss_mb():.0f} MB")
    print()
    return pipeline


def _tokens_generated(llm: Any, answer: str) -> int:
    last = getattr(llm, "last_gen_tokens", None)
    if isinstance(last, int) and last > 0:
        return last
    count_tokens = getattr(llm, "count_tokens", None)
    if callable(count_tokens):
        try:
            return int(count_tokens(answer))
        except Exception:  # noqa: BLE001
            return 0
    return 0


def print_answer_meta(
    *,
    mode: str,
    result: dict[str, Any],
    latency_s: float,
    tokens: int,
    memory_mb: float,
) -> None:
    """Print per-answer metrics under the answer body."""
    tps = (tokens / latency_s) if latency_s > 0 and tokens > 0 else 0.0
    print(f"Mode: {_mode_label(mode)}")
    print(f"Confidence: {result['confidence']:.4f}")
    print(f"Latency: {latency_s:.2f}s")
    print(f"Tokens Generated: {tokens}")
    print(f"Tokens/sec: {tps:.1f}")
    print(f"Memory Usage: {memory_mb:.0f} MB")
    if mode == "study":
        if result.get("refused"):
            print(f"refused={result['refused']}")
        print(format_citations(result.get("citations") or []))


def main() -> None:
    """Interactive ask loop: self-check, warm-start, route, print metrics."""
    enable_offline_mode()
    check = run_self_check()
    print("\n".join(check.format_lines()))
    print()
    if not check.ok:
        print(
            "Startup self-check failed. Fix the items marked ✗ before asking.",
            file=sys.stderr,
        )
        sys.exit(1)

    print_banner()
    print()
    try:
        pipeline = warm_start()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Enter a question (empty input or Ctrl+C exits).")
    print()

    while True:
        try:
            question = input("Enter question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            break
        try:
            t0 = time.perf_counter()
            result = pipeline.ask(question, top_k=TOP_K)
            latency_s = time.perf_counter() - t0
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:  # noqa: BLE001 - surface local LLM errors cleanly
            logger.exception("Ask failed")
            print(f"Error generating answer: {exc}", file=sys.stderr)
            continue

        mode = result.get("mode", "study")
        answer = result.get("answer") or ""
        tokens = _tokens_generated(pipeline.llm, answer)
        memory_mb = rss_mb()

        print()
        print(answer)
        print()
        print_answer_meta(
            mode=mode,
            result=result,
            latency_s=latency_s,
            tokens=tokens,
            memory_mb=memory_mb,
        )
        print()

    print("Goodbye.")


if __name__ == "__main__":
    main()
