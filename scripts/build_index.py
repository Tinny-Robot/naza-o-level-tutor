"""CLI entry point: build the FAISS index from externally computed embeddings.

Use after a chunks-only ingestion (``python scripts/ingest.py
--skip-embedding``) once ``data/processed/embeddings.npy`` has been produced
elsewhere (e.g. a Kaggle GPU notebook running the same
``matt-wisdom/KEmbed-naija-v3`` model over the texts in ``chunks.json``, in
the same order). Run from the project root:

    python scripts/build_index.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from app.config import (  # noqa: E402
    CHUNKS_PATH,
    EMBEDDINGS_PATH,
    INDEX_PATH,
    METADATA_PATH,
)
from app.ingestion.pipeline import write_metadata  # noqa: E402
from app.models.document import Chunk  # noqa: E402
from app.retrieval.faiss_store import FaissStore  # noqa: E402
from app.utils.logging import get_logger  # noqa: E402

logger = get_logger(__name__)


def main() -> None:
    """Validate chunks/embeddings, build and save the FAISS index."""
    for path, hint in (
        (CHUNKS_PATH, "run `python scripts/ingest.py --skip-embedding` first"),
        (EMBEDDINGS_PATH, "compute embeddings externally and place them there"),
    ):
        if not path.exists():
            print(f"Error: {path} not found; {hint}.", file=sys.stderr)
            sys.exit(1)

    with CHUNKS_PATH.open(encoding="utf-8") as fh:
        chunk_dicts = json.load(fh)
    embeddings = np.load(EMBEDDINGS_PATH)

    if embeddings.ndim != 2:
        print(
            f"Error: expected a 2D embeddings array, got shape {embeddings.shape}.",
            file=sys.stderr,
        )
        sys.exit(1)
    if embeddings.shape[0] != len(chunk_dicts):
        print(
            f"Error: {len(chunk_dicts)} chunks but {embeddings.shape[0]} embeddings; "
            "they must match one-to-one (same order as chunks.json).",
            file=sys.stderr,
        )
        sys.exit(1)

    store = FaissStore()
    store.build(embeddings.astype(np.float32))
    store.save(INDEX_PATH)

    chunks = [Chunk(**d) for d in chunk_dicts]
    documents_count = len({c.metadata.get("source") for c in chunks})
    if METADATA_PATH.exists():
        try:
            with METADATA_PATH.open(encoding="utf-8") as fh:
                documents_count = json.load(fh).get("documents", documents_count)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read existing metadata (%s); using fallback.", exc)
    write_metadata(
        chunks,
        documents_count=documents_count,
        embedding_dim=int(embeddings.shape[1]),
        index_size=store.size,
    )
    print(
        f"Index built: {store.size} vectors of dim {embeddings.shape[1]} "
        f"saved to {INDEX_PATH}."
    )


if __name__ == "__main__":
    main()
