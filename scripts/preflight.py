"""Pre-flight checks that must pass before the API server starts.

Run this before uvicorn to fail fast with a clear message instead of
crashing 60+ seconds into startup when the LLM tries to load.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly: python scripts/preflight.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def check_model() -> None:
    """Verify the GGUF model file exists; exit 1 with a clear message if not."""
    from app.config import MODEL_NAME, MODEL_PATH

    if MODEL_PATH.is_file():
        print(f"\u2713  Model found: {MODEL_PATH}", flush=True)
        return

    print(
        f"\n"
        f"\u274c  Naza local model not found.\n"
        f"\n"
        f"   Expected:  {MODEL_PATH}\n"
        f"\n"
        f"   Naza is offline-first and requires a local GGUF model ({MODEL_NAME}).\n"
        f"   To download the model, run from the repository root:\n"
        f"\n"
        f"       bash download_model.sh\n"
        f"\n"
        f"   After the download completes, start Naza again.\n"
        f"\n"
        f"   The app does NOT download model weights automatically.\n",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(1)


def check_embedding_model() -> None:
    """Warn (not fail) if the embedding model directory is missing."""
    from app.config import EMBEDDING_MODEL_PATH

    if EMBEDDING_MODEL_PATH.exists():
        print(f"\u2713  Embedding model found: {EMBEDDING_MODEL_PATH}", flush=True)
        return

    print(
        f"\u26a0\ufe0f   Embedding model not found at {EMBEDDING_MODEL_PATH}.\n"
        f"    Retrieval (RAG) will be unavailable until the model is downloaded.\n"
        f"    Run: bash download_model.sh",
        file=sys.stderr,
        flush=True,
    )
    # Not fatal - the app can start in degraded mode without embeddings.


def run_all() -> None:
    """Run all pre-flight checks. Call before starting uvicorn."""
    print("Naza pre-flight checks...", flush=True)
    check_model()
    check_embedding_model()
    print("Pre-flight checks passed.\n", flush=True)


if __name__ == "__main__":
    run_all()
