"""Convenience search API with a cached module-level Retriever."""

from __future__ import annotations

from typing import Any

from app.config import TOP_K
from app.retrieval.retriever import Retriever
from app.utils.logging import get_logger

logger = get_logger(__name__)

_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    """Return the shared :class:`Retriever`, creating it on first call."""
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def reset_retriever() -> None:
    """Drop the cached retriever (useful in tests after config changes)."""
    global _retriever
    _retriever = None


def search(
    query: str,
    top_k: int = TOP_K,
    subject: str | None = None,
    topic: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Search the index for ``query`` using the cached retriever.

    Args:
        query: Natural-language query.
        top_k: Number of results.
        subject: Optional subject metadata filter.
        topic: Optional topic metadata filter.
        source: Optional source substring filter.

    Returns:
        Results as returned by :meth:`Retriever.retrieve`.
    """
    return get_retriever().retrieve(
        query,
        top_k=top_k,
        subject=subject,
        topic=topic,
        source=source,
    )


def format_results(results: list[dict[str, Any]], max_chars: int = 400) -> str:
    """Format search results for terminal display.

    Args:
        results: Output of :func:`search`.
        max_chars: Truncate each chunk's text to this many characters.

    Returns:
        A human-readable, dash-separated block of results.
    """
    if not results:
        return "No results found."
    separator = "-" * 70
    lines: list[str] = [f"Top {len(results)} Results", separator]
    for i, result in enumerate(results, start=1):
        metadata = result.get("metadata", {}) or {}
        text = result["text"]
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        chunk_id = metadata.get("id", metadata.get("chunk_id", "N/A"))
        lines.append(f"[{i}] Rank: {i}")
        lines.append(f"Score: {result['score']:.4f}")
        lines.append(f"Subject: {metadata.get('subject', 'N/A')}")
        lines.append(f"Topic: {metadata.get('topic', 'N/A')}")
        lines.append(f"Source: {metadata.get('source', 'N/A')}")
        lines.append(f"Chunk ID: {chunk_id}")
        lines.append(f"Text: {text}")
        lines.append(separator)
    return "\n".join(lines)
