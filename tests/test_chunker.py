"""Tests for app.ingestion.chunker and app.ingestion.cleaner."""

from __future__ import annotations

import pytest

from app.ingestion.chunker import chunk_documents
from app.ingestion.cleaner import clean_documents, clean_text
from app.models.document import Document


def _doc(text: str, source: str = "data/raw/english/a.txt") -> Document:
    return Document(text=text, source=source, subject="english", topic="a")


# ---------------------------------------------------------------------------
# Cleaner
# ---------------------------------------------------------------------------


def test_clean_text_collapses_whitespace() -> None:
    assert clean_text("  hello   world \t !  ") == "hello world !"


def test_clean_text_collapses_blank_lines() -> None:
    assert clean_text("a\n\n\n  b\n") == "a\nb"


def test_clean_text_preserves_hausa_characters() -> None:
    text = "ɓarawo ɗan ƙasa da 'yan makaranta"
    assert clean_text(text) == text


def test_clean_text_nfc_normalization() -> None:
    # "e" + combining acute accent should become the composed "é".
    assert clean_text("cafe\u0301") == "caf\u00e9"


def test_clean_documents_drops_empty() -> None:
    docs = [_doc("  \n \t "), _doc("keep me")]
    cleaned = clean_documents(docs)
    assert len(cleaned) == 1
    assert cleaned[0].text == "keep me"


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


def test_short_document_single_chunk() -> None:
    chunks = chunk_documents([_doc("just a few words")], chunk_size=10, chunk_overlap=2)
    assert len(chunks) == 1
    assert chunks[0].text == "just a few words"
    assert chunks[0].metadata == {
        "source": "data/raw/english/a.txt",
        "subject": "english",
        "topic": "a",
    }


def test_chunk_sizes_and_overlap() -> None:
    words = [f"w{i}" for i in range(25)]
    chunks = chunk_documents([_doc(" ".join(words))], chunk_size=10, chunk_overlap=4)

    assert all(len(c.text.split()) <= 10 for c in chunks)
    first, second = chunks[0].text.split(), chunks[1].text.split()
    assert first[-4:] == second[:4]  # overlap of 4 words
    # Every word appears in at least one chunk.
    covered = {w for c in chunks for w in c.text.split()}
    assert covered == set(words)


def test_chunk_ids_unique_and_deterministic() -> None:
    words = " ".join(str(i) for i in range(50))
    docs = [_doc(words), _doc(words, source="data/raw/english/b.txt")]
    chunks_a = chunk_documents(docs, chunk_size=10, chunk_overlap=0)
    chunks_b = chunk_documents(docs, chunk_size=10, chunk_overlap=0)

    ids_a = [c.id for c in chunks_a]
    assert len(ids_a) == len(set(ids_a))
    assert ids_a == [c.id for c in chunks_b]


def test_invalid_chunk_params_raise() -> None:
    with pytest.raises(ValueError):
        chunk_documents([_doc("x")], chunk_size=0, chunk_overlap=0)
    with pytest.raises(ValueError):
        chunk_documents([_doc("x")], chunk_size=10, chunk_overlap=10)
