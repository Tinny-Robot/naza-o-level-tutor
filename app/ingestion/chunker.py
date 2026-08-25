"""Sliding-window text chunking for documents."""

from __future__ import annotations

import hashlib
from app.models.document import Chunk, Document


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 220,
    chunk_overlap: int = 40,
) -> list[Chunk]:
    """Split documents into overlapping word-level chunks.
    
    Args:
        documents: Source documents to split.
        chunk_size: Maximum number of words per chunk.
        chunk_overlap: Number of overlapping words between consecutive chunks.
        
    Returns:
        List of Chunk objects with metadata and deterministic IDs.
        
    Raises:
        ValueError: If chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be strictly less than chunk_size ({chunk_size})"
        )

    step = chunk_size - chunk_overlap
    chunks: list[Chunk] = []

    for doc_idx, doc in enumerate(documents):
        words = doc.text.split()
        if not words:
            continue

        if len(words) <= chunk_size:
            chunk_text = " ".join(words)
            chunk_id = hashlib.sha256(
                f"{doc.source}:{doc.subject}:{doc.topic}:{doc_idx}:0:{chunk_text}".encode()
            ).hexdigest()[:16]
            meta = {
                "source": doc.source,
                "subject": doc.subject,
                "topic": doc.topic,
                **doc.extra,
            }
            chunks.append(Chunk(id=chunk_id, text=chunk_text, metadata=meta))
            continue

        start = 0
        chunk_idx = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words)
            chunk_id = hashlib.sha256(
                f"{doc.source}:{doc.subject}:{doc.topic}:{doc_idx}:{chunk_idx}:{chunk_text}".encode()
            ).hexdigest()[:16]
            meta = {
                "source": doc.source,
                "subject": doc.subject,
                "topic": doc.topic,
                **doc.extra,
            }
            chunks.append(Chunk(id=chunk_id, text=chunk_text, metadata=meta))
            chunk_idx += 1
            if end >= len(words):
                break
            start += step

    return chunks

