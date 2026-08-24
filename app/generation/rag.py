"""Retrieval interface for the generation layer (no generation logic)."""

from __future__ import annotations

from typing import Any

from app.config import TOP_K
from app.retrieval.retriever import Retriever
from app.retrieval.search import get_retriever
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RetrievalService:
    """Thin wrapper around :class:`Retriever.retrieve` for the ask pipeline."""

    def __init__(self, retriever: Retriever | None = None) -> None:
        self._retriever = retriever

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = get_retriever()
        return self._retriever

    def retrieve(
        self,
        question: str,
        *,
        top_k: int = TOP_K,
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Forward to the underlying retriever with optional metadata filters."""
        hits = self.retriever.retrieve(
            question,
            top_k=top_k,
            subject=subject,
            topic=topic,
            source=source,
        )
        logger.info("Retrieved %d hit(s) for question (%d chars)", len(hits), len(question))
        return hits


def retrieve(
    question: str,
    *,
    top_k: int = TOP_K,
    subject: str | None = None,
    topic: str | None = None,
    source: str | None = None,
    retriever: Retriever | None = None,
) -> list[dict[str, Any]]:
    """Module-level convenience for retrieval-only access."""
    return RetrievalService(retriever=retriever).retrieve(
        question, top_k=top_k, subject=subject, topic=topic, source=source
    )
