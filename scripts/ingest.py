"""CLI entry point: build the retrieval artifacts from raw data.

Run from the project root:

    python scripts/ingest.py                    # full pipeline (embeds locally)
    python scripts/ingest.py --skip-embedding   # chunks + metadata only

The chunks-only mode is for small CPU machines: compute embeddings
externally (e.g. a Kaggle GPU notebook), drop them into
``data/processed/embeddings.npy``, then run ``python scripts/build_index.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.pipeline import run_ingestion  # noqa: E402


def main() -> None:
    """Parse CLI flags, run the pipeline, print a summary."""
    parser = argparse.ArgumentParser(description="Ingest raw data into the index.")
    parser.add_argument(
        "--skip-embedding",
        "--chunks-only",
        action="store_true",
        dest="skip_embedding",
        help="Only write chunks.json and metadata.json; embed and build the "
        "index later with scripts/build_index.py.",
    )
    args = parser.parse_args()

    stats = run_ingestion(embed=not args.skip_embedding)
    summary = f"{stats['documents']} documents, {stats['chunks']} chunks"
    if args.skip_embedding:
        print(
            f"Chunks-only ingestion complete: {summary}. "
            "Embeddings and index are pending (see scripts/build_index.py)."
        )
    else:
        print(
            f"Ingestion complete: {summary}, "
            f"embedding dim {stats['embedding_dim']}, "
            f"index size {stats['index_size']}."
        )


if __name__ == "__main__":
    main()
