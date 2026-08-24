"""Sentence embedding via a local KEmbed-naija-v3 SentenceTransformer snapshot.

Loads only from ``EMBEDDING_MODEL_PATH`` (or an explicit local directory) with
``local_files_only=True``. Never contacts Hugging Face.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from tqdm import tqdm

from app.config import EMBED_BATCH_SIZE, EMBEDDING_MODEL_PATH
from app.utils.logging import get_logger
from app.utils.offline import (
    embedding_model_present,
    enable_offline_mode,
    missing_embedding_instructions,
)

logger = get_logger(__name__)

_MODEL_CACHE: dict[str, object] = {}
_embedder_singleton: Embedder | None = None


def _get_model(model_path: str):
    """Load (once) a local SentenceTransformer; never download."""
    if model_path not in _MODEL_CACHE:
        enable_offline_mode()
        path = Path(model_path)
        if not embedding_model_present(path):
            raise FileNotFoundError(missing_embedding_instructions(path))

        # Imported here so tests can mock the model without pulling in torch.
        from sentence_transformers import SentenceTransformer

        logger.info(
            "Loading embedding model from local path %s (local_files_only=True)",
            path,
        )
        try:
            _MODEL_CACHE[model_path] = SentenceTransformer(
                str(path.resolve()),
                local_files_only=True,
            )
        except FileNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface offline load failures clearly
            raise RuntimeError(
                f"Failed to load local embedding model at {path} with "
                f"local_files_only=True. {missing_embedding_instructions(path)} "
                f"Original error: {exc}"
            ) from exc
    return _MODEL_CACHE[model_path]


class Embedder:
    """Thin wrapper around a lazily loaded local SentenceTransformer model."""

    def __init__(self, model_name: str | Path | None = None) -> None:
        """Store the local model directory; the model itself loads on first use.

        Args:
            model_name: Local directory path (defaults to
                :data:`app.config.EMBEDDING_MODEL_PATH`). Kept as ``model_name``
                for backward compatibility with tests / callers.
        """
        if model_name is None:
            self.model_name = str(EMBEDDING_MODEL_PATH)
        else:
            self.model_name = str(model_name)
        self._model = None

    @property
    def model(self):
        """The underlying SentenceTransformer, loaded on first access."""
        if self._model is None:
            self._model = _get_model(self.model_name)
        return self._model

    def embed_texts(
        self, texts: list[str], batch_size: int = EMBED_BATCH_SIZE
    ) -> np.ndarray:
        """Embed a list of texts.

        Args:
            texts: Texts to embed.
            batch_size: Number of texts per model call.

        Returns:
            Float32 array of shape ``(len(texts), dim)``.
        """
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        batches: list[np.ndarray] = []
        for start in tqdm(
            range(0, len(texts), batch_size),
            desc="Embedding",
            unit="batch",
        ):
            batch = texts[start : start + batch_size]
            vectors = self.model.encode(
                batch, batch_size=batch_size, show_progress_bar=False
            )
            batches.append(np.asarray(vectors, dtype=np.float32))
        return np.vstack(batches)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query string.

        Args:
            text: The query.

        Returns:
            Float32 array of shape ``(1, dim)``.
        """
        vector = self.model.encode([text], show_progress_bar=False)
        return np.asarray(vector, dtype=np.float32).reshape(1, -1)


def get_embedder(force_reload: bool = False) -> Embedder:
    """Return the process-wide Embedder singleton (model still lazy until used)."""
    global _embedder_singleton
    if _embedder_singleton is None or force_reload:
        if force_reload:
            _MODEL_CACHE.clear()
        _embedder_singleton = Embedder()
    return _embedder_singleton


def reset_embedder_singleton() -> None:
    """Clear the embedder singleton and model cache (tests only)."""
    global _embedder_singleton
    _embedder_singleton = None
    _MODEL_CACHE.clear()
