"""Tests for app.ingestion.loader."""

from __future__ import annotations

import json
from pathlib import Path

from app.ingestion.loader import load_raw_documents


def _make_raw(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    (raw / "english").mkdir(parents=True)
    (raw / "physics").mkdir(parents=True)
    return raw


def test_load_txt_and_md(tmp_path: Path) -> None:
    raw = _make_raw(tmp_path)
    (raw / "english" / "textbook_1.txt").write_text("Concord rules.", encoding="utf-8")
    (raw / "english" / "syllabus.md").write_text("# Syllabus\nTopics.", encoding="utf-8")

    docs = load_raw_documents(raw)

    assert len(docs) == 2
    by_topic = {d.topic: d for d in docs}
    assert by_topic["textbook_1"].text == "Concord rules."
    assert by_topic["textbook_1"].subject == "english"
    assert by_topic["textbook_1"].source.endswith("english/textbook_1.txt")
    assert by_topic["syllabus"].subject == "english"


def test_load_json_qa_records(tmp_path: Path) -> None:
    raw = _make_raw(tmp_path)
    records = [
        {
            "year": "2020",
            "exam_board": "WAEC",
            "paper_type": "Objective",
            "topic": "Lexis & Structure",
            "question": "Each of the candidates ___ expected.",
            "options": ["A. are", "B. is"],
            "answer": "B",
            "explanation": "'Each' is singular.",
        }
    ]
    (raw / "english" / "past_questions.json").write_text(
        json.dumps(records), encoding="utf-8"
    )

    docs = load_raw_documents(raw)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.topic == "Lexis & Structure"
    assert doc.subject == "english"
    assert "Question: Each of the candidates" in doc.text
    assert "A. are" in doc.text
    assert "Answer: B" in doc.text
    assert "Explanation: 'Each' is singular." in doc.text
    assert "2020" in doc.text and "WAEC" in doc.text


def test_load_jsonl(tmp_path: Path) -> None:
    raw = _make_raw(tmp_path)
    lines = [
        json.dumps({"topic": "Motion", "question": "Define velocity.", "answer": "A"}),
        "not valid json",
        json.dumps({"question": "Define speed.", "answer": "B"}),
    ]
    (raw / "physics" / "extra.jsonl").write_text("\n".join(lines), encoding="utf-8")

    docs = load_raw_documents(raw)

    assert len(docs) == 2  # malformed line skipped
    assert docs[0].topic == "Motion"
    assert docs[1].topic == "extra"  # falls back to file stem


def test_load_csv(tmp_path: Path) -> None:
    raw = _make_raw(tmp_path)
    (raw / "physics" / "table.csv").write_text(
        "topic,definition\nForce,A push or pull\n", encoding="utf-8"
    )

    docs = load_raw_documents(raw)

    assert len(docs) == 1
    assert docs[0].topic == "Force"
    assert "definition: A push or pull" in docs[0].text
    assert docs[0].subject == "physics"


def test_skips_unsupported_and_corrupt_files(tmp_path: Path) -> None:
    raw = _make_raw(tmp_path)
    (raw / "english" / "image.png").write_bytes(b"\x89PNG")
    (raw / "english" / "broken.json").write_text("{not json", encoding="utf-8")
    (raw / "english" / "good.txt").write_text("Fine.", encoding="utf-8")

    docs = load_raw_documents(raw)

    assert len(docs) == 1
    assert docs[0].text == "Fine."


def test_missing_raw_dir_returns_empty(tmp_path: Path) -> None:
    assert load_raw_documents(tmp_path / "nope") == []
