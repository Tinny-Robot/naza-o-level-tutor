"""Retriever: dense (FAISS), BM25, and hybrid (RRF) search with optional rerank.

Public API::

    retrieve(query, top_k=5, subject=None, topic=None, source=None) -> list[dict]

Each result is ``{"score": float, "text": str, "metadata": dict}``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from app.config import (
    CHUNKS_PATH,
    ENABLE_RERANKER,
    INDEX_PATH,
    RERANK_CANDIDATES,
    RERANKER_MODEL,
    RETRIEVAL_MODE,
    RRF_K,
    TOP_K,
)
from app.ingestion.embedder import Embedder
from app.retrieval.bm25_store import BM25Retriever
from app.retrieval.faiss_store import FaissStore
from app.utils.logging import get_logger

logger = get_logger(__name__)

VALID_MODES: frozenset[str] = frozenset({"dense", "bm25", "hybrid"})


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[int]],
    *,
    rrf_k: int = RRF_K,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """Fuse multiple rankings with Reciprocal Rank Fusion.

    For each document id ``d`` appearing in any list::

        score(d) = sum_i  1 / (rrf_k + rank_i(d))

    where ``rank_i`` is 1-based. Documents missing from a list contribute 0
    for that list.

    Args:
        ranked_lists: Sequences of corpus indices in descending preference.
        rrf_k: RRF smoothing constant (typically 60).
        top_k: Optional cutoff on the fused ranking.

    Returns:
        ``(doc_index, rrf_score)`` pairs sorted by descending score.
    """
    if rrf_k < 1:
        raise ValueError(f"rrf_k must be >= 1, got {rrf_k}")
    scores: dict[int, float] = {}
    for ranking in ranked_lists:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
    fused = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    if top_k is not None:
        return fused[:top_k]
    return fused


class Retriever:
    """Loads embedder, FAISS index, chunks, and (lazily) BM25 / reranker."""

    def __init__(
        self,
        index_path: Path = INDEX_PATH,
        chunks_path: Path = CHUNKS_PATH,
        embedder: Embedder | None = None,
        *,
        mode: str | None = None,
        enable_reranker: bool | None = None,
        rerank_candidates: int | None = None,
        rrf_k: int | None = None,
        reranker: Any | None = None,
        bm25: BM25Retriever | None = None,
        require_faiss: bool | None = None,
    ) -> None:
        """Load the index and chunk store.

        Args:
            index_path: Path to ``index.faiss``.
            chunks_path: Path to ``chunks.json``.
            embedder: Optional pre-built embedder (useful for tests).
            mode: ``"dense"``, ``"bm25"``, or ``"hybrid"``. Defaults to
                :data:`app.config.RETRIEVAL_MODE`.
            enable_reranker: Override :data:`app.config.ENABLE_RERANKER`.
            rerank_candidates: Override :data:`app.config.RERANK_CANDIDATES`.
            rrf_k: Override :data:`app.config.RRF_K`.
            reranker: Optional :class:`~app.retrieval.reranker.Reranker` (or
                stub) injected for tests.
            bm25: Optional pre-built :class:`BM25Retriever`.
            require_faiss: If False, allow missing FAISS when mode is bm25-only.
                Defaults to True unless ``mode == "bm25"``.

        Raises:
            FileNotFoundError: If required artifacts are missing.
            ValueError: If ``mode`` is invalid.
        """
        resolved_mode = (mode if mode is not None else RETRIEVAL_MODE).strip().lower()
        if resolved_mode not in VALID_MODES:
            raise ValueError(
                f"Invalid RETRIEVAL_MODE={resolved_mode!r}. "
                f"Choose one of: {', '.join(sorted(VALID_MODES))}."
            )
        self.mode = resolved_mode
        self.enable_reranker = (
            ENABLE_RERANKER if enable_reranker is None else enable_reranker
        )
        self.rerank_candidates = (
            RERANK_CANDIDATES if rerank_candidates is None else rerank_candidates
        )
        self.rrf_k = RRF_K if rrf_k is None else rrf_k
        self._reranker = reranker

        needs_faiss = require_faiss if require_faiss is not None else resolved_mode != "bm25"
        if not chunks_path.exists():
            raise FileNotFoundError(
                f"Missing chunks file ({chunks_path}). "
                "Run `python scripts/ingest.py` first to build the index."
            )
        if needs_faiss and not index_path.exists():
            raise FileNotFoundError(
                f"Missing index artifacts ({index_path}, {chunks_path}). "
                "Run `python scripts/ingest.py` first to build the index."
            )

        self.embedder = embedder if embedder is not None else Embedder()
        self.store: FaissStore | None = None
        if needs_faiss or index_path.exists():
            self.store = FaissStore()
            if index_path.exists():
                self.store.load(index_path)

        with chunks_path.open(encoding="utf-8") as fh:
            self.chunks: list[dict[str, Any]] = json.load(fh)

        if self.store is not None and self.store.size and len(self.chunks) != self.store.size:
            logger.warning(
                "Chunk count (%d) does not match index size (%d); "
                "consider re-running ingestion.",
                len(self.chunks),
                self.store.size,
            )

        self._bm25 = bm25
        if self._bm25 is None and resolved_mode in {"bm25", "hybrid"}:
            self._bm25 = BM25Retriever([c.get("text", "") for c in self.chunks])

        logger.info(
            "Retriever ready: %d chunks, mode=%s, reranker=%s",
            len(self.chunks),
            self.mode,
            self.enable_reranker,
        )

    @property
    def bm25(self) -> BM25Retriever:
        """Lazily build BM25 over chunk texts."""
        if self._bm25 is None:
            self._bm25 = BM25Retriever([c.get("text", "") for c in self.chunks])
        return self._bm25

    @property
    def reranker(self) -> Any:
        """Lazily construct the cross-encoder reranker."""
        if self._reranker is None:
            from app.retrieval.reranker import Reranker

            self._reranker = Reranker(model_name=RERANKER_MODEL)
        return self._reranker

    def _matches_filters(
        self,
        metadata: dict[str, Any],
        *,
        subject: str | None,
        topic: str | None,
        source: str | None,
    ) -> bool:
        """Return True if metadata satisfies all provided filters.

        * ``subject`` / ``topic`` - case-insensitive equality after strip.
        * ``source`` - case-insensitive substring match on the source field.
        """
        if subject is not None and subject.strip():
            if (metadata.get("subject") or "").strip().lower() != subject.strip().lower():
                return False
        if topic is not None and topic.strip():
            if (metadata.get("topic") or "").strip().lower() != topic.strip().lower():
                return False
        if source is not None and source.strip():
            hay = (metadata.get("source") or "").strip().lower()
            if source.strip().lower() not in hay:
                return False
        return True

    def _allowed_indices(
        self,
        subject: str | None,
        topic: str | None,
        source: str | None,
    ) -> list[int] | None:
        """Indices of chunks matching filters, or ``None`` when unfiltered."""
        if not any(
            v is not None and str(v).strip() for v in (subject, topic, source)
        ):
            return None
        allowed = [
            i
            for i, chunk in enumerate(self.chunks)
            if self._matches_filters(
                chunk.get("metadata") or {},
                subject=subject,
                topic=topic,
                source=source,
            )
        ]
        return allowed

    def _result_from_index(self, idx: int, score: float) -> dict[str, Any] | None:
        if idx < 0 or idx >= len(self.chunks):
            return None
        chunk = self.chunks[idx]
        metadata = dict(chunk.get("metadata") or {})
        if "id" not in metadata and chunk.get("id") is not None:
            metadata["id"] = chunk["id"]
        return {"score": float(score), "text": chunk["text"], "metadata": metadata}

    def _dense_search(
        self,
        query: str,
        top_k: int,
        allowed_indices: list[int] | None,
    ) -> list[tuple[int, float]]:
        """FAISS search with optional metadata pre-filter via post-masking.

        When filters are active the full index is searched (corpus is modest)
        and non-matching ids are dropped so ranking among candidates is exact.
        """
        if self.store is None or self.store.size == 0:
            raise RuntimeError(
                "Dense retrieval requires a loaded FAISS index. "
                "Run ingestion or switch RETRIEVAL_MODE to 'bm25'."
            )
        query_vec = self.embedder.embed_query(query)
        fetch_k = self.store.size if allowed_indices is not None else min(top_k, self.store.size)
        # Always fetch enough for filtering / later fusion.
        fetch_k = max(fetch_k, min(top_k, self.store.size))
        scores, indices = self.store.search(query_vec, fetch_k)

        allowed_set = set(allowed_indices) if allowed_indices is not None else None
        hits: list[tuple[int, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            idx_i = int(idx)
            if idx_i < 0:
                continue
            if allowed_set is not None and idx_i not in allowed_set:
                continue
            hits.append((idx_i, float(score)))
            if len(hits) >= top_k:
                break
        return hits

    def _bm25_search(
        self,
        query: str,
        top_k: int,
        allowed_indices: list[int] | None,
    ) -> list[tuple[int, float]]:
        return self.bm25.search(query, top_k=top_k, allowed_indices=allowed_indices)

    def _hybrid_search(
        self,
        query: str,
        top_k: int,
        allowed_indices: list[int] | None,
    ) -> list[tuple[int, float]]:
        # Fetch a wider pool from each channel before fusion.
        pool = max(top_k, self.rerank_candidates if self.enable_reranker else top_k)
        if allowed_indices is not None:
            pool = max(pool, len(allowed_indices))
        dense_hits = self._dense_search(query, pool, allowed_indices)
        bm25_hits = self._bm25_search(query, pool, allowed_indices)
        fused = reciprocal_rank_fusion(
            [[idx for idx, _ in dense_hits], [idx for idx, _ in bm25_hits]],
            rrf_k=self.rrf_k,
            top_k=top_k,
        )
        return fused

    def _search_indices(
        self,
        query: str,
        top_k: int,
        allowed_indices: list[int] | None,
    ) -> list[tuple[int, float]]:
        if self.mode == "dense":
            return self._dense_search(query, top_k, allowed_indices)
        if self.mode == "bm25":
            return self._bm25_search(query, top_k, allowed_indices)
        return self._hybrid_search(query, top_k, allowed_indices)

    def retrieve(
        self,
        query: str,
        top_k: int = TOP_K,
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the ``top_k`` most relevant chunks for ``query``.

        Args:
            query: Natural-language query.
            top_k: Number of results to return after optional reranking.
            subject: Optional metadata filter (exact, case-insensitive).
            topic: Optional metadata filter (exact, case-insensitive).
            source: Optional metadata filter (substring, case-insensitive).

        Returns:
            List of ``{"score": float, "text": str, "metadata": dict}``,
            ordered by descending score (cosine / BM25 / RRF / reranker).
        """
        if not query.strip():
            return []
        if top_k < 1:
            return []

        allowed = self._allowed_indices(subject, topic, source)
        if allowed is not None and not allowed:
            logger.info(
                "No chunks match filters subject=%r topic=%r source=%r",
                subject,
                topic,
                source,
            )
            return []

        fetch_k = top_k
        if self.enable_reranker:
            fetch_k = max(top_k, self.rerank_candidates)

        hits = self._search_indices(query, fetch_k, allowed)
        results: list[dict[str, Any]] = []
        for idx, score in hits:
            item = self._result_from_index(idx, score)
            if item is not None:
                results.append(item)

        if self.enable_reranker and results:
            results = self.reranker.rerank(query, results, top_k=top_k)
        else:
            results = results[:top_k]
        return results
