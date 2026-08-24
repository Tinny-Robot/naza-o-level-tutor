"""Hallucination / abstention guard based on retrieval quality."""

from __future__ import annotations

from typing import Any

from app.config import MIN_RETRIEVAL_SCORE, REFUSAL_MESSAGE


def should_refuse(
    results: list[dict[str, Any]],
    *,
    min_score: float = MIN_RETRIEVAL_SCORE,
) -> bool:
    """Return True when there are no docs or the top score is too low."""
    if not results:
        return True
    top = results[0].get("score")
    if not isinstance(top, (int, float)):
        return True
    return float(top) < min_score


def refusal_message(language: str | None = None) -> str:
    """Fixed abstain string (no LLM call)."""
    try:
        from app.i18n.messages import ui_string

        return ui_string("refusal", language)
    except Exception:
        return REFUSAL_MESSAGE
