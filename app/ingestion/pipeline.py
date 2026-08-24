"""End-to-end ingestion pipeline: load -> clean -> chunk -> [embed -> index].

The embedding/indexing stage is optional (``embed=False``) so that chunking
can run on a small CPU machine while embeddings are computed externally
(e.g. on a Kaggle GPU notebook) and indexed later via
``scripts/build_index.py``.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from app.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKS_PATH,
    EMBEDDING_MODEL,
    EMBEDDINGS_PATH,
    INDEX_PATH,
    METADATA_PATH,
    PROCESSED_DIR,
    RAW_DIR,
)
from app.ingestion.chunker import chunk_documents
from app.ingestion.cleaner import clean_documents
from app.ingestion.loader import load_raw_documents
from app.models.document import Chunk
from app.utils.logging import get_logger

logger = get_logger(__name__)


def write_metadata(
    chunks: list[Chunk],
    documents_count: int,
    embedding_dim: int | None,
    index_size: int | None,
) -> None:
    """Write ``metadata.json`` describing the current artifacts.

    Args:
        chunks: All chunks that were written to ``chunks.json``.
        documents_count: Number of documents after cleaning.
        embedding_dim: Embedding dimension, or ``None`` if embeddings are
            still pending (chunks-only run).
        index_size: FAISS index size, or ``None`` if pending.
    """
    metadata: dict[str, Any] = {
        "model": EMBEDDING_MODEL,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "documents": documents_count,
        "chunks": len(chunks),
        "embedding_dim": embedding_dim,
        "index_size": index_size,
        "status": "complete" if index_size is not None else "embeddings_pending",
        "chunk_metadata": [{"id": chunk.id, **chunk.metadata} for chunk in chunks],
    }
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
    logger.info("Wrote metadata to %s", METADATA_PATH)


def run_ingestion(embed: bool = True) -> dict[str, Any]:
    """Run the ingestion pipeline and persist artifacts.

    Always writes ``chunks.json`` and ``metadata.json`` under
    ``data/processed/``. When ``embed`` is true, also writes
    ``embeddings.npy`` and ``data/index/index.faiss``; otherwise the
    metadata notes that embeddings/index are pending and can be built
    externally (see ``scripts/build_index.py``).

    Args:
        embed: Whether to run the embedding + indexing stage.

    Returns:
        Summary statistics (documents, chunks; plus embedding dim and index
        size when ``embed`` is true).

    Raises:
        RuntimeError: If no documents or chunks were produced.
    """
    logger.info("Starting ingestion from %s (embed=%s)", RAW_DIR, embed)

    documents = load_raw_documents(RAW_DIR)
    if not documents:
        raise RuntimeError(f"No documents loaded from {RAW_DIR}; nothing to ingest.")

    documents = clean_documents(documents)
    logger.info("%d documents after cleaning", len(documents))

    chunks = chunk_documents(documents)
    if not chunks:
        raise RuntimeError("No chunks produced; check chunker configuration.")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with CHUNKS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(
            [chunk.to_dict() for chunk in chunks], fh, ensure_ascii=False, indent=2
        )
    logger.info("Wrote %d chunks to %s", len(chunks), CHUNKS_PATH)

    stats: dict[str, Any] = {"documents": len(documents), "chunks": len(chunks)}

    if not embed:
        write_metadata(chunks, len(documents), embedding_dim=None, index_size=None)
        logger.info(
            "Skipped embedding stage; compute embeddings externally and run "
            "scripts/build_index.py. Stats: %s",
            stats,
        )
        return stats

    # Imported lazily so chunks-only runs never touch torch/faiss.
    from app.ingestion.embedder import Embedder
    from app.retrieval.faiss_store import FaissStore

    embedder = Embedder()
    embeddings = embedder.embed_texts([chunk.text for chunk in chunks])
    logger.info(
        "Embedded %d chunks (dim=%d)", embeddings.shape[0], embeddings.shape[1]
    )

    store = FaissStore()
    store.build(embeddings)
    store.save(INDEX_PATH)

    np.save(EMBEDDINGS_PATH, embeddings)
    logger.info("Wrote embeddings to %s", EMBEDDINGS_PATH)

    stats["embedding_dim"] = int(embeddings.shape[1])
    stats["index_size"] = store.size
    write_metadata(
        chunks,
        len(documents),
        embedding_dim=stats["embedding_dim"],
        index_size=stats["index_size"],
    )

    logger.info("Ingestion complete: %s", stats)
    return stats
