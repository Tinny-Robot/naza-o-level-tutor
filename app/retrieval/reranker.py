"""Cross-encoder reranker for retrieved passages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from app.config import RERANKER_MODEL
from app.utils.logging import get_logger

logger = get_logger(__name__)

_CROSS_ENCODER_CACHE: dict[str, Any] = {}


def _load_cross_encoder(model_name: str) -> Any:
    """Load (once) a sentence-transformers CrossEncoder."""
    if model_name not in _CROSS_ENCODER_CACHE:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - dependency always present in prod
            raise RuntimeError(
                "sentence-transformers is required for reranking but is not installed."
            ) from exc
        try:
            from app.utils.offline import enable_offline_mode

            enable_offline_mode()
            path = Path(model_name)
            logger.info(
                "Loading reranker model %s (local_files_only=True)", model_name
            )
            if path.is_dir():
                _CROSS_ENCODER_CACHE[model_name] = CrossEncoder(
                    str(path), local_files_only=True
                )
            else:
                # Hub id only works if already fully cached offline; never download.
                _CROSS_ENCODER_CACHE[model_name] = CrossEncoder(
                    model_name, local_files_only=True
                )
        except Exception as exc:  # noqa: BLE001 - surface offline load failures clearly
            raise RuntimeError(
                f"Failed to load reranker model {model_name!r} offline. "
                "Place a local CrossEncoder snapshot on disk, set RERANKER_MODEL "
                "to that path, or set ENABLE_RERANKER = False in app/config.py. "
                f"Original error: {exc}"
            ) from exc
    return _CROSS_ENCODER_CACHE[model_name]


class Reranker:
    """Rerank ``(query, passage)`` pairs with a cross-encoder.

    Default model: ``cross-encoder/ms-marco-MiniLM-L-6-v2``.
    """

    def __init__(
        self,
        model_name: str = RERANKER_MODEL,
        model: Any | None = None,
    ) -> None:
        """Create a reranker.

        Args:
            model_name: Hugging Face model id (used when ``model`` is None).
            model: Optional pre-built CrossEncoder (or stub) for tests.
        """
        self.model_name = model_name
        self._model = model

    @property
    def model(self) -> Any:
        """Underlying CrossEncoder, loaded lazily on first access."""
        if self._model is None:
            self._model = _load_cross_encoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        results: Sequence[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Rerank retrieval results by cross-encoder score.

        Args:
            query: Original user query.
            results: Candidate list of ``{score, text, metadata}``.
            top_k: Optional cutoff after reranking; ``None`` keeps all.

        Returns:
            New list sorted by descending reranker score. Each item keeps
            ``text`` / ``metadata`` and replaces ``score`` with the
            cross-encoder score.
        """
        if not results:
            return []
        if not query.strip():
            return list(results)[:top_k] if top_k is not None else list(results)

        pairs = [(query, r.get("text") or "") for r in results]
        try:
            raw_scores = self.model.predict(pairs)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Reranker inference failed for model {self.model_name!r}: {exc}"
            ) from exc

        scored: list[dict[str, Any]] = []
        for result, score in zip(results, raw_scores):
            scored.append(
                {
                    "score": float(score),
                    "text": result["text"],
                    "metadata": dict(result.get("metadata") or {}),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        if top_k is not None:
            return scored[:top_k]
        return scored
