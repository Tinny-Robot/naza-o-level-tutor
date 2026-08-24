"""FAISS inner-product index with L2 normalization (cosine similarity)."""

from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np

from app.utils.logging import get_logger

logger = get_logger(__name__)


class FaissStore:
    """Wrapper around ``faiss.IndexFlatIP`` storing L2-normalized vectors.

    Because all stored vectors and queries are normalized, inner-product
    scores equal cosine similarity.
    """

    def __init__(self) -> None:
        """Create an empty store; call :meth:`build` or :meth:`load`."""
        self.index: faiss.IndexFlatIP | None = None

    @property
    def size(self) -> int:
        """Number of vectors in the index (0 if not built)."""
        return int(self.index.ntotal) if self.index is not None else 0

    def build(self, embeddings: np.ndarray) -> None:
        """Build the index from an ``(n, dim)`` float32 embedding matrix.

        The input is copied and L2-normalized before being added.

        Raises:
            ValueError: If ``embeddings`` is not a non-empty 2D array.
        """
        if embeddings.ndim != 2 or embeddings.shape[0] == 0:
            raise ValueError(
                f"Expected a non-empty 2D embeddings array, got shape {embeddings.shape}"
            )
        vectors = np.ascontiguousarray(embeddings, dtype=np.float32).copy()
        faiss.normalize_L2(vectors)
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(vectors)
        logger.info(
            "Built IndexFlatIP with %d vectors of dim %d",
            self.index.ntotal,
            vectors.shape[1],
        )

    def save(self, path: Path) -> None:
        """Write the index to ``path``, creating parent directories.

        Raises:
            RuntimeError: If the index has not been built.
        """
        if self.index is None:
            raise RuntimeError("Cannot save: index has not been built or loaded.")
        path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(path))
        logger.info("Saved FAISS index (%d vectors) to %s", self.index.ntotal, path)

    def load(self, path: Path) -> None:
        """Load an index previously written by :meth:`save`.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"FAISS index not found at {path}")
        self.index = faiss.read_index(str(path))
        logger.info("Loaded FAISS index (%d vectors) from %s", self.index.ntotal, path)

    def search(self, query_vecs: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        """Search for the ``k`` nearest neighbours of each query vector.

        Args:
            query_vecs: ``(m, dim)`` float32 array; normalized in-place copy.
            k: Number of results per query.

        Returns:
            Tuple ``(scores, indices)``, each of shape ``(m, k)``.

        Raises:
            RuntimeError: If the index has not been built or loaded.
        """
        if self.index is None:
            raise RuntimeError("Cannot search: index has not been built or loaded.")
        vectors = np.ascontiguousarray(query_vecs, dtype=np.float32).copy()
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        faiss.normalize_L2(vectors)
        k = min(k, self.index.ntotal)
        scores, indices = self.index.search(vectors, k)
        return scores, indices
