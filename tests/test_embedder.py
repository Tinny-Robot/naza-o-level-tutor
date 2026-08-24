"""Tests for app.ingestion.embedder with the SentenceTransformer mocked."""

from __future__ import annotations

import numpy as np
import pytest

import app.ingestion.embedder as embedder_module
from app.ingestion.embedder import Embedder

DIM = 8


class FakeModel:
    """Deterministic stand-in for SentenceTransformer."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str], **_: object) -> np.ndarray:
        self.calls.append(list(texts))
        rng = np.random.default_rng(len(texts))
        return rng.normal(size=(len(texts), DIM)).astype(np.float64)


@pytest.fixture()
def fake_embedder(monkeypatch: pytest.MonkeyPatch) -> Embedder:
    fake = FakeModel()
    monkeypatch.setattr(embedder_module, "_get_model", lambda name: fake)
    emb = Embedder(model_name="fake-model")
    emb._fake = fake  # type: ignore[attr-defined]
    return emb


def test_embed_texts_shape_and_dtype(fake_embedder: Embedder) -> None:
    vectors = fake_embedder.embed_texts(["a", "b", "c"], batch_size=2)
    assert vectors.shape == (3, DIM)
    assert vectors.dtype == np.float32


def test_embed_texts_batches(fake_embedder: Embedder) -> None:
    fake_embedder.embed_texts([f"t{i}" for i in range(5)], batch_size=2)
    fake = fake_embedder._fake  # type: ignore[attr-defined]
    assert [len(batch) for batch in fake.calls] == [2, 2, 1]


def test_embed_texts_empty(fake_embedder: Embedder) -> None:
    vectors = fake_embedder.embed_texts([])
    assert vectors.shape[0] == 0
    assert vectors.dtype == np.float32


def test_embed_query_shape(fake_embedder: Embedder) -> None:
    vector = fake_embedder.embed_query("what is concord?")
    assert vector.shape == (1, DIM)
    assert vector.dtype == np.float32


def test_model_loaded_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        embedder_module, "_get_model", lambda name: calls.append(name) or FakeModel()
    )
    emb = Embedder(model_name="lazy-model")
    assert calls == []  # not loaded at construction
    emb.embed_query("hi")
    assert calls == ["lazy-model"]
