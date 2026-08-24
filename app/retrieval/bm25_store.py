"""BM25 lexical retriever over chunk texts."""

from __future__ import annotations

import re
from typing import Any, Sequence

from rank_bm25 import BM25Okapi

from app.utils.logging import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization suitable for BM25."""
    return [tok.lower() for tok in _TOKEN_RE.findall(text or "")]


class BM25Retriever:
    """Indexes chunk texts with BM25Okapi and returns ranked corpus indices.

    Filtering is applied **before** scoring: when ``allowed_indices`` is
    provided, BM25 scores are computed only for that subset (non-allowed
    documents receive a score of ``-inf`` and never surface in top-k).
    """

    def __init__(self, texts: Sequence[str]) -> None:
        """Build a BM25 index over ``texts`` (one entry per chunk).

        Args:
            texts: Corpus strings aligned with FAISS / chunks.json order.

        Raises:
            ValueError: If ``texts`` is empty.
        """
        if not texts:
            raise ValueError("Cannot build BM25 index over an empty corpus")
        self.texts: list[str] = list(texts)
        self._tokenized: list[list[str]] = [tokenize(t) for t in self.texts]
        # BM25Okapi needs at least one non-empty token list; empty docs get [""].
        corpus = [tokens if tokens else [""] for tokens in self._tokenized]
        self._bm25 = BM25Okapi(corpus)
        logger.info("BM25 index built over %d documents", len(self.texts))

    @property
    def size(self) -> int:
        """Number of indexed documents."""
        return len(self.texts)

    def search(
        self,
        query: str,
        top_k: int = 5,
        allowed_indices: Sequence[int] | None = None,
    ) -> list[tuple[int, float]]:
        """Return ``(corpus_index, score)`` pairs sorted by descending BM25 score.

        Args:
            query: Natural-language query.
            top_k: Maximum number of hits.
            allowed_indices: Optional pre-filter; only these corpus indices
                are scored. ``None`` means the full corpus.

        Returns:
            Up to ``top_k`` ``(index, score)`` tuples. Empty query → ``[]``.
        """
        if not query.strip() or top_k < 1:
            return []

        tokens = tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)

        if allowed_indices is not None:
            allowed = set(int(i) for i in allowed_indices)
            ranked = [
                (idx, float(scores[idx]))
                for idx in allowed
                if 0 <= idx < len(scores)
            ]
        else:
            ranked = [(idx, float(scores[idx])) for idx in range(len(scores))]

        ranked.sort(key=lambda pair: pair[1], reverse=True)
        return ranked[:top_k]

    def search_as_results(
        self,
        query: str,
        chunks: Sequence[dict[str, Any]],
        top_k: int = 5,
        allowed_indices: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Search and map hits to ``{score, text, metadata}`` result dicts."""
        hits = self.search(query, top_k=top_k, allowed_indices=allowed_indices)
        results: list[dict[str, Any]] = []
        for idx, score in hits:
            if idx < 0 or idx >= len(chunks):
                continue
            chunk = chunks[idx]
            metadata = dict(chunk.get("metadata") or {})
            if "id" not in metadata and chunk.get("id") is not None:
                metadata["id"] = chunk["id"]
            results.append(
                {
                    "score": score,
                    "text": chunk["text"],
                    "metadata": metadata,
                }
            )
        return results
