"""Staged RSS profiler + ablation matrix for the Gemma warm-start path.

Run from the project root (fresh process each time):

    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \\
      .venv/bin/python scripts/profile_memory.py

    .venv/bin/python scripts/profile_memory.py --ablation A
    .venv/bin/python scripts/profile_memory.py --ablation all

Never downloads models. Kill any lingering ask.py before profiling.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import (  # noqa: E402
    CONTEXT_LENGTH,
    EMBEDDING_MODEL_PATH,
    MODEL_NAME,
    MODEL_PATH,
    THREADS,
    TOP_K,
)
from app.generation.llm import (  # noqa: E402
    LlamaCppLLM,
    build_llama_kwargs,
    get_llm,
    reset_llm_singleton,
)
from app.generation.pipeline import GenerationPipeline  # noqa: E402
from app.generation.prompt_manager import get_prompt_manager, reset_prompt_manager  # noqa: E402
from app.generation.rag import RetrievalService  # noqa: E402
from app.ingestion.embedder import get_embedder, reset_embedder_singleton  # noqa: E402
from app.retrieval.search import get_retriever, reset_retriever  # noqa: E402
from app.utils.offline import enable_offline_mode, run_self_check  # noqa: E402
from app.utils.runtime import RssStageLogger, peak_rss_mb, rss_mb  # noqa: E402

GENERAL_PROMPT = "Say hello in one short sentence."
STUDY_PROMPT = "Explain Ohm's law and give the formula."


def _reset_singletons() -> None:
    reset_llm_singleton()
    reset_prompt_manager()
    reset_embedder_singleton()
    reset_retriever()


def _llama_kwargs_for_ablation(ablation: str) -> dict[str, Any]:
    """Return Llama() kwargs overrides for a single-variable ablation.

    A = legacy pre-optimization defaults (FA off, full SWA) for comparison.
    Prod = current ``build_llama_kwargs`` (FA on, SWA_FULL off).
    """
    legacy = {
        "model_path": str(MODEL_PATH),
        "n_ctx": CONTEXT_LENGTH,
        "n_threads": THREADS,
        "n_gpu_layers": 0,
        "verbose": True,  # surface FA / SWA / KV log lines for verification
        "flash_attn": False,
        "swa_full": True,
    }
    if ablation == "A":
        return {**legacy, "verbose": False}
    if ablation == "B":
        return {**legacy, "flash_attn": True}
    if ablation == "C":
        return {**legacy, "swa_full": False}
    if ablation == "D":
        return {**legacy, "n_ctx": 2048}
    if ablation == "prod":
        kwargs = build_llama_kwargs(
            model_path=MODEL_PATH,
            n_ctx=CONTEXT_LENGTH,
            n_threads=THREADS,
        )
        return kwargs
    raise ValueError(f"Unknown Llama ablation {ablation!r}")


def _install_llama_kwargs_patch(overrides: dict[str, Any]) -> Any:
    """Patch LlamaCppLLM so ablations can inject Llama() kwargs."""
    import app.generation.llm as llm_mod
    from llama_cpp import Llama

    original_init = llm_mod.LlamaCppLLM.__init__

    def patched_init(
        self: LlamaCppLLM,
        *,
        model_path: str | Path | None = None,
        n_ctx: int = CONTEXT_LENGTH,
        n_threads: int = THREADS,
        temperature: float = 0.1,
        max_tokens: int = 512,
        model_name: str = MODEL_NAME,
    ) -> None:
        path = MODEL_PATH if model_path is None else Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"GGUF model not found at {path}")
        kwargs = dict(overrides)
        kwargs["model_path"] = str(path)
        # Honour explicit n_ctx from overrides when present.
        if "n_ctx" not in kwargs:
            kwargs["n_ctx"] = n_ctx
        if "n_threads" not in kwargs:
            kwargs["n_threads"] = n_threads
        kwargs.setdefault("n_gpu_layers", 0)
        print(f"[profile] Llama() kwargs: {kwargs}")
        self._llama = Llama(**kwargs)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.last_gen_tokens = 0
        self.llama_kwargs = dict(kwargs)

    llm_mod.LlamaCppLLM.__init__ = patched_init  # type: ignore[method-assign]
    return original_init


def dump_model_metadata(llm: LlamaCppLLM) -> dict[str, Any]:
    """Dump GGUF / llama.cpp metadata available from the loaded handle."""
    path = Path(MODEL_PATH)
    meta: dict[str, Any] = {
        "MODEL_PATH": str(path),
        "basename": path.name,
        "file_size_gb": round(path.stat().st_size / (1024**3), 3) if path.is_file() else None,
        "expected_basename": "gemma-4-E4B-it-Q4_K_M.gguf",
        "basename_ok": path.name == "gemma-4-E4B-it-Q4_K_M.gguf",
        "CONTEXT_LENGTH_config": CONTEXT_LENGTH,
        "THREADS": THREADS,
    }
    llama = getattr(llm, "_llama", None)
    if llama is None:
        return meta

    cp = getattr(llama, "context_params", None)
    meta["llama_kwargs_used"] = {
        "n_ctx": getattr(cp, "n_ctx", None),
        "flash_attn_type": getattr(cp, "flash_attn_type", None),
        "swa_full": getattr(cp, "swa_full", None),
        "type_k": getattr(cp, "type_k", None),
        "type_v": getattr(cp, "type_v", None),
        "n_batch": getattr(llama, "n_batch", None),
    }
    # ggml type 1 == F16 in llama.cpp; flash_attn_type 0 == disabled.
    meta["kv_notes"] = {
        "flash_attn_enabled": bool(getattr(cp, "flash_attn_type", 0)),
        "swa_full_active": bool(getattr(cp, "swa_full", False)),
        "type_k_f16": getattr(cp, "type_k", None) == 1,
        "type_v_f16": getattr(cp, "type_v", None) == 1,
    }
    try:
        meta["n_ctx_active"] = int(llama.n_ctx())
    except Exception as exc:  # noqa: BLE001
        meta["n_ctx_active_error"] = str(exc)
    try:
        meta["n_embd"] = int(llama.n_embd())
    except Exception as exc:  # noqa: BLE001
        meta["n_embd_error"] = str(exc)
    try:
        model = getattr(llama, "_model", None)
        if model is not None:
            meta["n_vocab"] = int(model.n_vocab())
            meta["n_ctx_train"] = int(model.n_ctx_train())
            meta["n_params"] = int(model.n_params())
    except Exception as exc:  # noqa: BLE001
        meta["model_attr_error"] = str(exc)
    try:
        raw = getattr(llama, "metadata", None)
        if isinstance(raw, dict):
            interesting = {
                k: v
                for k, v in raw.items()
                if any(
                    tok in k.lower()
                    for tok in (
                        "general.architecture",
                        "general.name",
                        "general.file_type",
                        "general.quantization_version",
                        "context_length",
                        "embedding_length",
                        "block_count",
                        "attention.head",
                        "attention.key",
                        "attention.value",
                        "attention.sliding",
                        "rope",
                        "shared_kv",
                    )
                )
            }
            meta["gguf_keys"] = interesting or dict(list(raw.items())[:40])
            # GGUF file_type 15 == Q4_K_M in llama.cpp enums.
            meta["quantization"] = {
                "file_type": raw.get("general.file_type"),
                "file_type_is_q4_k_m": str(raw.get("general.file_type")) == "15",
                "architecture": raw.get("general.architecture"),
                "n_embd": raw.get("gemma4.embedding_length"),
                "n_layer": raw.get("gemma4.block_count"),
                "n_head": raw.get("gemma4.attention.head_count"),
                "n_head_kv": raw.get("gemma4.attention.head_count_kv"),
                "n_ctx_train": raw.get("gemma4.context_length"),
                "sliding_window": raw.get("gemma4.attention.sliding_window"),
            }
    except Exception as exc:  # noqa: BLE001
        meta["gguf_meta_error"] = str(exc)
    return meta

def top_smaps(limit: int = 25) -> list[dict[str, Any]]:
    """Return largest /proc/self/smaps_rollup-friendly mappings by RSS."""
    smaps = Path("/proc/self/smaps")
    if not smaps.is_file():
        return []
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    try:
        text = smaps.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        if not line:
            continue
        # Header lines look like: "7f..-7f.. r-xp 00000000 ... /path"
        if " Rss:" not in line and not line[0].isdigit() and not (
            len(line) > 8 and "-" in line[:20]
        ):
            # still may be header - check for address range
            pass
        parts = line.split()
        if parts and "-" in parts[0] and len(parts[0].split("-")) == 2:
            if current is not None:
                rows.append(current)
            pathname = " ".join(parts[5:]) if len(parts) >= 6 else "[anon]"
            current = {"pathname": pathname or "[anon]", "rss_kb": 0, "pss_kb": 0}
            continue
        if current is None:
            continue
        if line.startswith("Rss:"):
            try:
                current["rss_kb"] = int(line.split()[1])
            except (IndexError, ValueError):
                pass
        elif line.startswith("Pss:"):
            try:
                current["pss_kb"] = int(line.split()[1])
            except (IndexError, ValueError):
                pass
    if current is not None:
        rows.append(current)
    rows.sort(key=lambda r: r.get("rss_kb", 0), reverse=True)
    return rows[:limit]


def print_smaps(limit: int = 25) -> None:
    rows = top_smaps(limit=limit)
    print()
    print(f"Top {limit} /proc/self/smaps mappings by RSS")
    print(f"{'RSS_MB':>8} {'PSS_MB':>8}  pathname")
    print("-" * 72)
    for row in rows:
        print(
            f"{row['rss_kb'] / 1024:8.0f} {row['pss_kb'] / 1024:8.0f}  "
            f"{row['pathname'][:90]}"
        )


def run_component_split() -> None:
    """Ablation E: embedder-only vs LLM-only RSS in separate phases (same process)."""
    print("=" * 60)
    print("Ablation E - component split (sequential, fresh process recommended)")
    print("=" * 60)
    _reset_singletons()
    log = RssStageLogger()
    log.mark("process_start")
    emb = get_embedder()
    _ = emb.model
    log.mark("embedder_only")
    print(f"Embedder path: {EMBEDDING_MODEL_PATH}")
    # Drop embedder refs before LLM to approximate LLM-only (best-effort).
    reset_embedder_singleton()
    # Note: torch/sentence-transformers may retain native memory; report honestly.
    log.mark("after_embedder_reset")
    llm = get_llm()
    log.mark("llm_after_embedder_reset")
    print()
    print(log.summary_table())
    print()
    print("Also run with PROFILE_COMPONENT=embed|llm for true split processes.")
    _ = llm


def run_embedder_only() -> None:
    log = RssStageLogger()
    log.mark("process_start")
    emb = get_embedder()
    _ = emb.model
    log.mark("embedder_loaded")
    print(log.summary_table())
    print(f"Ready RSS (embedder-only): {rss_mb():.0f} MB")


def run_llm_only() -> None:
    log = RssStageLogger()
    log.mark("process_start")
    llm = get_llm()
    log.mark("gguf_kv_loaded")
    meta = dump_model_metadata(llm)
    print()
    print("Model metadata")
    for k, v in meta.items():
        print(f"  {k}: {v}")
    print()
    print(log.summary_table())
    print(f"Ready RSS (llm-only): {rss_mb():.0f} MB")


def run_full_profile(ablation: str, *, with_smaps: bool = False) -> dict[str, Any]:
    """Stages 1-9 matching warm_start order + first general + first study ask."""
    print("=" * 60)
    print(f"Memory profile ablation={ablation}")
    print("=" * 60)

    original_init = None
    if ablation in {"A", "B", "C", "D", "prod"}:
        overrides = _llama_kwargs_for_ablation(ablation)
        original_init = _install_llama_kwargs_patch(overrides)

    _reset_singletons()
    log = RssStageLogger()
    log.mark("1_process_start")

    prompts = get_prompt_manager()
    log.mark("2_prompt_manager")

    embedder = get_embedder()
    _ = embedder.model
    log.mark("3_embedding_model")

    llm = get_llm()
    log.mark("4_gguf_loaded")
    # KV is allocated inside Llama(); same sample documents stage 5.
    log.mark("5_kv_cache_init")

    meta = dump_model_metadata(llm)
    print()
    print("Model / KV verification")
    for k, v in meta.items():
        print(f"  {k}: {v}")
    print()

    retriever = get_retriever()
    if getattr(retriever, "embedder", None) is not None:
        retriever.embedder = embedder
    log.mark("6_faiss_index")

    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=retriever),
        llm=llm,
        prompts=prompts,
    )
    log.mark("7_generation_pipeline")
    ready_rss = rss_mb()
    print(f"Ready RSS (after stage 7): {ready_rss:.0f} MB")

    if with_smaps or ablation == "F":
        print_smaps(limit=30)

    # Stage 8 - tiny general prompt
    _ = pipeline.ask(GENERAL_PROMPT, top_k=TOP_K)
    log.mark("8_first_inference_general")

    # Stage 9 - first Study-mode query
    _ = pipeline.ask(STUDY_PROMPT, top_k=TOP_K)
    log.mark("9_first_study_query")

    peak = peak_rss_mb()
    print()
    print(log.summary_table())
    print()
    print(f"Ready RSS: {ready_rss:.0f} MB")
    print(f"Peak RSS (ru_maxrss): {peak:.0f} MB")
    print(f"Final RSS: {rss_mb():.0f} MB")

    if original_init is not None:
        import app.generation.llm as llm_mod

        llm_mod.LlamaCppLLM.__init__ = original_init  # type: ignore[method-assign]

    return {
        "ablation": ablation,
        "ready_rss_mb": ready_rss,
        "peak_rss_mb": peak,
        "final_rss_mb": rss_mb(),
        "stages": [
            {
                "name": s.name,
                "rss_mb": s.rss_mb,
                "delta_mb": s.delta_mb,
                "peak_rss_mb": s.peak_rss_mb,
            }
            for s in log.stages
        ],
        "meta": meta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemma warm-start RSS profiler")
    parser.add_argument(
        "--ablation",
        default="A",
        choices=["A", "B", "C", "D", "E", "F", "prod", "all", "embed", "llm"],
        help="Ablation run (A=legacy baseline FA-off/SWA-full; prod=current defaults). "
        "Run each ablation in a fresh process for fair RSS.",
    )
    parser.add_argument(
        "--smaps",
        action="store_true",
        help="Dump top smaps after Ready (also on for ablation F).",
    )
    args = parser.parse_args()

    enable_offline_mode()
    # Ensure offline flags visible in child tooling.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    check = run_self_check()
    print("\n".join(check.format_lines()))
    print()
    if not check.ok:
        print("Profiler aborted: startup self-check failed.", file=sys.stderr)
        sys.exit(1)

    if args.ablation == "embed":
        run_embedder_only()
        return
    if args.ablation == "llm":
        run_llm_only()
        return
    if args.ablation == "E":
        run_component_split()
        return
    if args.ablation == "all":
        print(
            "For fair RSS, run each ablation in a fresh process:\n"
            "  .venv/bin/python scripts/profile_memory.py --ablation A\n"
            "  .venv/bin/python scripts/profile_memory.py --ablation B\n"
            "  .venv/bin/python scripts/profile_memory.py --ablation C\n"
            "  .venv/bin/python scripts/profile_memory.py --ablation D\n"
            "  .venv/bin/python scripts/profile_memory.py --ablation embed\n"
            "  .venv/bin/python scripts/profile_memory.py --ablation llm\n"
            "  .venv/bin/python scripts/profile_memory.py --ablation F --smaps\n"
        )
        run_full_profile("A", with_smaps=True)
        return

    run_full_profile(args.ablation, with_smaps=args.smaps or args.ablation == "F")


if __name__ == "__main__":
    main()
