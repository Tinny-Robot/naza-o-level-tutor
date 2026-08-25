"""Hallucination / abstention guard based on retrieval quality."""

from __future__ import annotations

import re
from typing import Any

from app.config import MIN_RETRIEVAL_SCORE, REFUSAL_MESSAGE
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Minimum fraction of context keywords that should appear in the answer
# before we log a low-coverage warning. Conservative threshold to avoid
# false positives on legitimate paraphrasing.
_MIN_KEYWORD_OVERLAP = 0.15
_STOP_WORDS = frozenset(
    {
        "the", "a", "an", "is", "it", "in", "on", "at", "to", "of", "and",
        "or", "for", "with", "that", "this", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "its", "their",
        "they", "we", "you", "he", "she", "i", "my", "your", "our", "his",
        "her", "from", "by", "as", "not", "no", "but", "so", "if",
    }
)


def _keywords(text: str) -> frozenset[str]:
    """Extract meaningful lowercase words (excluding stop-words)."""
    words = re.findall(r"[a-z]{3,}", text.lower())
    return frozenset(w for w in words if w not in _STOP_WORDS)


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


def warn_if_low_coverage(
    answer: str,
    context_chunks: list[dict[str, Any]],
) -> None:
    """Log a warning when the answer shares few keywords with retrieved context.

    This is a lightweight signal — not a hard block. A low overlap may indicate
    hallucination, or may simply reflect valid paraphrasing. Log it for review.

    Does not make any model calls; uses only string operations.
    """
    if not answer or not context_chunks:
        return
    context_text = " ".join(
        str(chunk.get("text") or "") for chunk in context_chunks
    )
    if not context_text.strip():
        return

    context_kw = _keywords(context_text)
    answer_kw = _keywords(answer)
    if not context_kw or not answer_kw:
        return

    overlap = len(context_kw & answer_kw)
    coverage = overlap / len(context_kw)
    if coverage < _MIN_KEYWORD_OVERLAP:
        logger.warning(
            "Low curriculum coverage in answer: %.0f%% keyword overlap "
            "(answer_kw=%d, context_kw=%d, overlap=%d). "
            "Possible hallucination — review if answer quality is degraded.",
            coverage * 100,
            len(answer_kw),
            len(context_kw),
            overlap,
        )


def refusal_message(language: str | None = None) -> str:
    """Fixed abstain string (no LLM call)."""
    try:
        from app.i18n.messages import ui_string

        return ui_string("refusal", language)
    except Exception:
        return REFUSAL_MESSAGE
