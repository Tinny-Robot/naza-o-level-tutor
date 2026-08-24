"""Tests for BM25, hybrid RRF, reranker, metrics, and metadata filtering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.evaluation.loader import QADatasetError, load_qa_dataset
from app.evaluation.metrics import (
    hit_rate,
    is_relevant,
    label_relevances,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)
from app.retrieval.bm25_store import BM25Retriever, tokenize
from app.retrieval.faiss_store import FaissStore
from app.retrieval.reranker import Reranker
from app.retrieval.retriever import Retriever, reciprocal_rank_fusion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class StubEmbedder:
    """Maps known queries to fixed vectors."""

    def __init__(self, mapping: dict[str, np.ndarray] | None = None) -> None:
        self.mapping = mapping or {}

    def embed_query(self, text: str) -> np.ndarray:
        if text in self.mapping:
            vec = self.mapping[text]
        else:
            # Deterministic fallback from hash so unknown queries still work.
            rng = np.random.default_rng(abs(hash(text)) % (2**32))
            vec = rng.normal(size=2).astype(np.float32)
        return vec.reshape(1, -1).astype(np.float32)


class StubCrossEncoder:
    """Assigns scores from a fixed map or by simple keyword overlap."""

    def __init__(self, scores: list[float] | None = None) -> None:
        self.scores = scores
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(list(pairs))
        if self.scores is not None:
            return list(self.scores[: len(pairs)])
        # Prefer passages containing "relevant".
        return [10.0 if "relevant" in text.lower() else 0.1 for _, text in pairs]


@pytest.fixture()
def corpus_artifacts(tmp_path: Path) -> tuple[Path, Path, list[dict[str, Any]]]:
    """Tiny 4-doc corpus with distinct subjects/topics for filter tests."""
    chunks = [
        {
            "id": "c0",
            "text": "Ohm's law states that V equals I times R in electric circuits.",
            "metadata": {
                "subject": "physics",
                "topic": "Electricity",
                "source": "data/raw/physics/notes.txt",
            },
        },
        {
            "id": "c1",
            "text": "Subject-verb concord requires agreement in number and person.",
            "metadata": {
                "subject": "english",
                "topic": "Concord",
                "source": "data/raw/english/grammar.txt",
            },
        },
        {
            "id": "c2",
            "text": "The quadratic formula solves ax^2 + bx + c = 0 for x.",
            "metadata": {
                "subject": "mathematics",
                "topic": "Algebra",
                "source": "data/raw/mathematics/algebra.txt",
            },
        },
        {
            "id": "c3",
            "text": "Zinc Zn2+ loses two electrons from the 4s orbital.",
            "metadata": {
                "subject": "chemistry",
                "topic": "Structure of the Atom",
                "source": "data/raw/chemistry/past_questions.json",
            },
        },
    ]
    # Dense vectors roughly aligned with topics for StubEmbedder tests.
    vectors = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.7, 0.7],
            [0.9, 0.1],
        ],
        dtype=np.float32,
    )
    store = FaissStore()
    store.build(vectors)
    index_path = tmp_path / "index.faiss"
    store.save(index_path)
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(json.dumps(chunks), encoding="utf-8")
    return index_path, chunks_path, chunks


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------


def test_tokenize_lowercases_and_splits() -> None:
    assert tokenize("Ohm's Law: V=IR") == ["ohm's", "law", "v", "ir"]


def test_bm25_ranks_matching_document_first() -> None:
    texts = [
        "cats sit on mats",
        "ohm law voltage current resistance electric circuits",
        "photosynthesis in green plants",
    ]
    bm25 = BM25Retriever(texts)
    hits = bm25.search("ohm law electric", top_k=2)
    assert hits[0][0] == 1
    assert hits[0][1] > hits[1][1]


def test_bm25_respects_allowed_indices() -> None:
    texts = ["alpha beta", "ohm law", "gamma delta ohm"]
    bm25 = BM25Retriever(texts)
    hits = bm25.search("ohm", top_k=5, allowed_indices=[0, 2])
    assert all(idx in {0, 2} for idx, _ in hits)
    assert hits[0][0] == 2


def test_bm25_empty_query() -> None:
    assert BM25Retriever(["a", "b"]).search("   ", top_k=3) == []


# ---------------------------------------------------------------------------
# RRF / hybrid
# ---------------------------------------------------------------------------


def test_reciprocal_rank_fusion_prefers_shared_top_docs() -> None:
    # Doc 1 ranks high in both lists → should win.
    fused = reciprocal_rank_fusion([[1, 2, 3], [1, 4, 5]], rrf_k=60, top_k=3)
    assert fused[0][0] == 1
    assert fused[0][1] > fused[1][1]


def test_hybrid_retriever_returns_results(corpus_artifacts: tuple[Path, Path, list]) -> None:
    index_path, chunks_path, _ = corpus_artifacts
    embedder = StubEmbedder({"ohm": np.array([1.0, 0.0], dtype=np.float32)})
    retriever = Retriever(
        index_path=index_path,
        chunks_path=chunks_path,
        embedder=embedder,
        mode="hybrid",
        enable_reranker=False,
    )
    results = retriever.retrieve("ohm", top_k=2)
    assert len(results) == 2
    assert set(results[0]) == {"score", "text", "metadata"}
    assert "Ohm" in results[0]["text"] or "ohm" in results[0]["text"].lower()


def test_bm25_mode_without_needing_dense_scores(
    corpus_artifacts: tuple[Path, Path, list],
) -> None:
    index_path, chunks_path, _ = corpus_artifacts
    retriever = Retriever(
        index_path=index_path,
        chunks_path=chunks_path,
        embedder=StubEmbedder({}),
        mode="bm25",
        enable_reranker=False,
    )
    results = retriever.retrieve("quadratic formula algebra", top_k=1)
    assert len(results) == 1
    assert "quadratic" in results[0]["text"].lower()


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------


def test_reranker_with_stub_cross_encoder_reorders() -> None:
    stub = StubCrossEncoder()
    reranker = Reranker(model=stub)
    results = [
        {"score": 0.9, "text": "unrelated filler", "metadata": {"id": "a"}},
        {"score": 0.5, "text": "this is relevant material", "metadata": {"id": "b"}},
    ]
    reranked = reranker.rerank("what is relevant?", results, top_k=1)
    assert len(reranked) == 1
    assert reranked[0]["metadata"]["id"] == "b"
    assert reranked[0]["score"] == pytest.approx(10.0)


def test_retriever_applies_reranker(
    corpus_artifacts: tuple[Path, Path, list],
) -> None:
    index_path, chunks_path, _ = corpus_artifacts
    stub = StubCrossEncoder(scores=[0.1, 0.2, 0.3, 9.9])
    retriever = Retriever(
        index_path=index_path,
        chunks_path=chunks_path,
        embedder=StubEmbedder({"q": np.array([1.0, 0.0], dtype=np.float32)}),
        mode="bm25",
        enable_reranker=True,
        rerank_candidates=4,
        reranker=Reranker(model=stub),
    )
    results = retriever.retrieve("ohm law zinc quadratic concord", top_k=1)
    assert len(results) == 1
    assert stub.calls  # predict was invoked


# ---------------------------------------------------------------------------
# Metadata filtering
# ---------------------------------------------------------------------------


def test_metadata_filter_subject(
    corpus_artifacts: tuple[Path, Path, list],
) -> None:
    index_path, chunks_path, _ = corpus_artifacts
    retriever = Retriever(
        index_path=index_path,
        chunks_path=chunks_path,
        embedder=StubEmbedder({}),
        mode="bm25",
        enable_reranker=False,
    )
    results = retriever.retrieve("law", top_k=5, subject="physics")
    assert results
    assert all(r["metadata"]["subject"] == "physics" for r in results)


def test_metadata_filter_topic_and_source(
    corpus_artifacts: tuple[Path, Path, list],
) -> None:
    index_path, chunks_path, _ = corpus_artifacts
    retriever = Retriever(
        index_path=index_path,
        chunks_path=chunks_path,
        embedder=StubEmbedder({}),
        mode="bm25",
        enable_reranker=False,
    )
    results = retriever.retrieve(
        "electrons zinc",
        top_k=5,
        topic="Structure of the Atom",
        source="chemistry",
    )
    assert len(results) == 1
    assert results[0]["metadata"]["id"] == "c3"


def test_metadata_filter_no_match_returns_empty(
    corpus_artifacts: tuple[Path, Path, list],
) -> None:
    index_path, chunks_path, _ = corpus_artifacts
    retriever = Retriever(
        index_path=index_path,
        chunks_path=chunks_path,
        embedder=StubEmbedder({}),
        mode="dense",
        enable_reranker=False,
    )
    assert retriever.retrieve("anything", subject="biology") == []


# ---------------------------------------------------------------------------
# Evaluation metrics + loader
# ---------------------------------------------------------------------------


def test_is_relevant_subject_and_keywords() -> None:
    doc = {
        "text": "Electronic configuration of zinc Zn2+ is 3d10",
        "metadata": {"subject": "chemistry", "topic": "Structure of the Atom"},
    }
    assert is_relevant(
        doc,
        subject="chemistry",
        expected_keywords=["zinc", "3d10"],
    )
    assert not is_relevant(
        doc,
        subject="physics",
        expected_keywords=["photosynthesis"],
    )


def test_recall_precision_mrr_hit_rate() -> None:
    relevances = [
        [False, True, False],  # first hit @2
        [True, False, False],  # first hit @1
        [False, False, False],  # miss
    ]
    assert recall_at_k(relevances, 1) == pytest.approx(1 / 3)
    assert recall_at_k(relevances, 2) == pytest.approx(2 / 3)
    assert precision_at_k(relevances, 2) == pytest.approx(
        ((0 + 1) / 2 + (1 + 0) / 2 + (0 + 0) / 2) / 3
    )
    assert mean_reciprocal_rank(relevances) == pytest.approx(
        (1 / 2 + 1 / 1 + 0) / 3
    )
    assert hit_rate(relevances) == pytest.approx(2 / 3)


def test_label_relevances_length() -> None:
    results = [
        {"text": "zinc atom", "metadata": {"subject": "chemistry", "topic": "Atom"}},
        {"text": "unrelated", "metadata": {"subject": "english", "topic": "x"}},
    ]
    labels = label_relevances(
        results, subject="chemistry", expected_keywords=["zinc"]
    )
    assert labels == [True, False]


def test_load_qa_dataset_valid(tmp_path: Path) -> None:
    path = tmp_path / "qa.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "1",
                    "question": "Q?",
                    "answer": "A",
                    "subject": "chemistry",
                    "topic": "Atom",
                    "expected_keywords": ["zinc"],
                }
            ]
        ),
        encoding="utf-8",
    )
    items = load_qa_dataset(path)
    assert len(items) == 1
    assert items[0]["id"] == "1"


def test_load_qa_dataset_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "qa.json"
    path.write_text("[]", encoding="utf-8")
    assert load_qa_dataset(path) == []


def test_load_qa_dataset_rejects_bad_schema(tmp_path: Path) -> None:
    path = tmp_path / "qa.json"
    path.write_text(json.dumps([{"id": "1", "question": "Q"}]), encoding="utf-8")
    with pytest.raises(QADatasetError, match="missing"):
        load_qa_dataset(path)


def test_load_qa_dataset_missing_file(tmp_path: Path) -> None:
    with pytest.raises(QADatasetError, match="not found"):
        load_qa_dataset(tmp_path / "missing.json")
