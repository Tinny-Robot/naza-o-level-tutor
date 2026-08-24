"""Citation records from post-budget retrieved chunks."""

from __future__ import annotations

from typing import Any


def build_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build citation dicts from the same chunks sent to the LLM.

    Each citation::

        {"subject", "topic", "source", "chunk_id", "score"}
    """
    citations: list[dict[str, Any]] = []
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        score = chunk.get("score")
        citations.append(
            {
                "subject": metadata.get("subject"),
                "topic": metadata.get("topic"),
                "source": metadata.get("source"),
                "chunk_id": metadata.get("id"),
                "score": float(score) if isinstance(score, (int, float)) else None,
            }
        )
    return citations
