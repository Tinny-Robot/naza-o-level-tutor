"""Build token-budgeted context blocks with stable ``[Chunk id]`` labels."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from app.config import MAX_CONTEXT_TOKENS
from app.utils.logging import get_logger

logger = get_logger(__name__)


class TokenCounter(Protocol):
    def count_tokens(self, text: str) -> int: ...


def _chunk_id(result: dict[str, Any]) -> str:
    """Stable id from metadata, else a short hash of the text."""
    metadata = result.get("metadata") or {}
    raw = metadata.get("id")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    text = (result.get("text") or "").strip()
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _score(result: dict[str, Any]) -> float:
    score = result.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    return 0.0


def format_chunk_block(
    result: dict[str, Any],
    chunk_id: str | None = None,
    *,
    text_override: str | None = None,
) -> str:
    """Render one retrieval hit as a ``[Chunk id]`` block."""
    cid = chunk_id if chunk_id is not None else _chunk_id(result)
    metadata = result.get("metadata") or {}
    subject = metadata.get("subject", "N/A")
    topic = metadata.get("topic", "N/A")
    source = metadata.get("source", "N/A")
    text = (
        text_override
        if text_override is not None
        else (result.get("text") or "").strip()
    )
    return (
        f"[Chunk {cid}]\n"
        f"Subject: {subject}\n"
        f"Topic: {topic}\n"
        f"Source: {source}\n\n"
        f"{text}"
    )


class ContextBuilder:
    """Dedupe, sort by score, and fit chunks into a token budget."""

    def __init__(
        self,
        token_counter: TokenCounter,
        *,
        max_context_tokens: int = MAX_CONTEXT_TOKENS,
        reserved_tokens: int = 0,
    ) -> None:
        self._counter = token_counter
        self.max_context_tokens = max_context_tokens
        self.reserved_tokens = reserved_tokens

    @property
    def budget(self) -> int:
        return max(0, self.max_context_tokens - self.reserved_tokens)

    def prepare(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Dedupe by chunk id (or text hash) and sort by score descending."""
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for result in results:
            cid = _chunk_id(result)
            if cid in seen:
                continue
            seen.add(cid)
            # Ensure metadata carries the resolved id for citations.
            enriched = dict(result)
            meta = dict(enriched.get("metadata") or {})
            meta["id"] = cid
            enriched["metadata"] = meta
            unique.append(enriched)
        unique.sort(key=_score, reverse=True)
        return unique

    def _fit_block(
        self,
        result: dict[str, Any],
        cid: str,
        *,
        prefix: str,
        room: int,
    ) -> tuple[str, dict[str, Any]] | None:
        """Return a block that fits in ``room`` tokens, truncating text if needed."""
        if room <= 0:
            return None
        full = format_chunk_block(result, cid)
        candidate = f"{prefix}{full}"
        cost = self._counter.count_tokens(candidate)
        if cost <= room:
            return full, result

        text = (result.get("text") or "").strip()
        if not text:
            return None

        # Binary-search a text prefix that keeps the whole candidate within room.
        lo, hi = 0, len(text)
        best: tuple[str, dict[str, Any]] | None = None
        while lo <= hi:
            mid = (lo + hi) // 2
            truncated = text[:mid].rstrip()
            if not truncated:
                lo = mid + 1
                continue
            block = format_chunk_block(result, cid, text_override=truncated + "…")
            cand = f"{prefix}{block}"
            if self._counter.count_tokens(cand) <= room:
                clipped = dict(result)
                clipped["text"] = truncated + "…"
                best = (block, clipped)
                lo = mid + 1
            else:
                hi = mid - 1

        if best is None:
            logger.warning(
                "Chunk %s header alone exceeds remaining budget %d; skipping",
                cid,
                room,
            )
        else:
            logger.info("Truncated chunk %s to fit remaining budget %d", cid, room)
        return best

    def build(
        self, results: list[dict[str, Any]]
    ) -> tuple[str, list[dict[str, Any]]]:
        """Return ``(context_text, selected_chunks)`` within the token budget.

        Token counts come from ``token_counter.count_tokens`` - never a
        character heuristic. Oversized chunks are truncated to fit.
        """
        prepared = self.prepare(results)
        if not prepared:
            return "", []

        budget = self.budget
        selected: list[dict[str, Any]] = []
        blocks: list[str] = []
        used = 0

        for result in prepared:
            cid = _chunk_id(result)
            prefix = "" if not blocks else "\n\n"
            room = budget - used
            fitted = self._fit_block(result, cid, prefix=prefix, room=room)
            if fitted is None:
                if selected:
                    logger.info(
                        "Context budget reached (%d/%d tokens); kept %d chunk(s)",
                        used,
                        budget,
                        len(selected),
                    )
                    break
                continue
            block, stored = fitted
            cost = self._counter.count_tokens(f"{prefix}{block}")
            blocks.append(block)
            selected.append(stored)
            used += cost

        context = "\n\n".join(blocks)
        return context, selected
