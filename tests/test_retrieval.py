"""Tests for app.retrieval: FaissStore and Retriever (stubbed embedder)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.retrieval.faiss_store import FaissStore
from app.retrieval.retriever import Retriever


def _unit(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32)
    return arr / np.linalg.norm(arr)


# ---------------------------------------------------------------------------
# FaissStore
# ---------------------------------------------------------------------------


def test_search_returns_cosine_scores() -> None:
    # Non-normalized inputs; the store must normalize them itself.
    base = np.array([[2.0, 0.0], [0.0, 5.0], [3.0, 3.0]], dtype=np.float32)
    store = FaissStore()
    store.build(base)

    scores, indices = store.search(np.array([[10.0, 0.0]], dtype=np.float32), k=3)

    assert indices[0].tolist() == [0, 2, 1]
    expected = [1.0, float(np.dot(_unit([10, 0]), _unit([3, 3]))), 0.0]
    assert np.allclose(scores[0], expected, atol=1e-5)


def test_top_k_ordering_descending() -> None:
    rng = np.random.default_rng(42)
    store = FaissStore()
    store.build(rng.normal(size=(50, 16)).astype(np.float32))

    scores, _ = store.search(rng.normal(size=(1, 16)).astype(np.float32), k=10)
    assert all(scores[0][i] >= scores[0][i + 1] for i in range(9))


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    vectors = np.eye(4, dtype=np.float32)
    store = FaissStore()
    store.build(vectors)
    path = tmp_path / "idx" / "index.faiss"
    store.save(path)

    loaded = FaissStore()
    loaded.load(path)
    assert loaded.size == 4
    scores, indices = loaded.search(np.array([[0.0, 1.0, 0.0, 0.0]]), k=1)
    assert indices[0][0] == 1
    assert scores[0][0] == pytest.approx(1.0)


def test_build_rejects_empty() -> None:
    with pytest.raises(ValueError):
        FaissStore().build(np.empty((0, 4), dtype=np.float32))


def test_search_without_index_raises() -> None:
    with pytest.raises(RuntimeError):
        FaissStore().search(np.zeros((1, 4), dtype=np.float32), k=1)


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------


class StubEmbedder:
    """Maps known queries to fixed vectors."""

    def __init__(self, mapping: dict[str, np.ndarray]) -> None:
        self.mapping = mapping

    def embed_query(self, text: str) -> np.ndarray:
        return self.mapping[text].reshape(1, -1).astype(np.float32)


@pytest.fixture()
def index_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    vectors = np.array(
        [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]], dtype=np.float32
    )
    store = FaissStore()
    store.build(vectors)
    index_path = tmp_path / "index.faiss"
    store.save(index_path)

    chunks = [
        {"id": f"c{i}", "text": f"chunk {i}", "metadata": {"subject": "english", "topic": f"t{i}", "source": "s"}}
        for i in range(3)
    ]
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(json.dumps(chunks), encoding="utf-8")
    return index_path, chunks_path


def test_retriever_returns_expected_shape(index_artifacts: tuple[Path, Path]) -> None:
    index_path, chunks_path = index_artifacts
    embedder = StubEmbedder({"q": np.array([1.0, 0.0])})
    retriever = Retriever(index_path=index_path, chunks_path=chunks_path, embedder=embedder)

    results = retriever.retrieve("q", top_k=2)

    assert len(results) == 2
    assert results[0]["text"] == "chunk 0"
    assert results[0]["score"] == pytest.approx(1.0)
    assert results[0]["metadata"]["topic"] == "t0"
    assert results[0]["score"] >= results[1]["score"]
    assert set(results[0]) == {"score", "text", "metadata"}


def test_retriever_empty_query(index_artifacts: tuple[Path, Path]) -> None:
    index_path, chunks_path = index_artifacts
    retriever = Retriever(
        index_path=index_path, chunks_path=chunks_path, embedder=StubEmbedder({})
    )
    assert retriever.retrieve("   ") == []


def test_retriever_missing_index_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="ingest"):
        Retriever(
            index_path=tmp_path / "missing.faiss",
            chunks_path=tmp_path / "missing.json",
            embedder=StubEmbedder({}),
        )
