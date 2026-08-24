"""Practice bank sampling and exam submit (no GGUF)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.practice.bank import grade_choice, sample_questions
from backend.api.main import create_app


def test_sample_chemistry_waec() -> None:
    items = sample_questions(subject="chemistry", exam="WAEC", n=5, seed=1)
    assert items
    assert all(i.get("options") for i in items)
    assert all(i.get("answer") for i in items)


def test_grade_choice() -> None:
    q = {"answer": "C", "explanation": "Because.", "topic": "Atom"}
    assert grade_choice(q, "C")["correct"] is True
    wrong = grade_choice(q, "A")
    assert wrong["correct"] is False
    assert wrong["confused"]


def test_grade_choice_hausa_chrome_keeps_english_explanation() -> None:
    q = {"answer": "C", "explanation": "Because the nucleus is positive.", "topic": "Atom"}
    ok = grade_choice(q, "C", language="Hausa")
    assert ok["correct"] is True
    assert ok["feedback"].startswith("Daidai")
    assert "Because the nucleus is positive." in ok["feedback"]
    wrong = grade_choice(q, "A", language="Hausa")
    assert wrong["correct"] is False
    assert "Bai daidai ba" in wrong["feedback"]
    assert "Because the nucleus is positive." in wrong["feedback"]
    english = grade_choice(q, "C")
    assert english["feedback"].startswith("Correct.")


@asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pipeline = object()
    yield


def _client() -> TestClient:
    return TestClient(create_app(lifespan_fn=_noop_lifespan))


def test_student_summary_api() -> None:
    with _client() as client:
        res = client.get("/student/summary")
        assert res.status_code == 200
        data = res.json()
        assert "learning_plan" in data
        assert "streak_days" in data


def test_exam_start_submit() -> None:
    with _client() as client:
        start = client.post(
            "/exams/start",
            json={"exam": "WAEC", "subject": "chemistry", "n": 5, "minutes": 10},
        )
        assert start.status_code == 200, start.text
        body = start.json()
        assert body["delivered"] == len(body["items"])
        assert body["requested"] == 5
        for item in body["items"]:
            assert "images" in item
            assert "passage" in item
        sid = body["session_id"]
        answers: dict[str, str] = {}
        for item in body["items"]:
            answers[item["id"]] = "A"
        done = client.post(
            "/exams/submit",
            json={"session_id": sid, "answers": answers, "flagged": []},
        )
        assert done.status_code == 200
        assert "score_pct" in done.json()
        assert "breakdown" in done.json()


def test_no_duplicate_stems_in_large_exam() -> None:
    for subject in ("english", "mathematics", "physics", "chemistry"):
        items = sample_questions(subject=subject, exam="WAEC", n=40, seed=7)
        stems = [i["question"] for i in items]
        assert len(stems) == len(set(stems)), subject
        assert len(items) <= 40


def test_english_includes_comprehension() -> None:
    items = sample_questions(subject="english", exam="WAEC", n=40, seed=3)
    assert any(i.get("passage") for i in items)
    assert any(i.get("paper_type") == "Comprehension" for i in items)


def test_curated_qa_images_are_used() -> None:
    from pathlib import Path

    from app.practice.bank import _from_qa_json, _unified_bank, reset_bank_cache

    reset_bank_cache()
    physics_qa = _from_qa_json("physics")
    assert any(i.get("images") for i in physics_qa)

    for subject, lo, hi in (
        ("chemistry", 1, 20),
        ("mathematics", 1, 20),
        ("physics", 20, 200),
        ("english", 0, 5),
    ):
        items = list(_unified_bank(subject))
        imaged = [i for i in items if i.get("images")]
        assert lo <= len(imaged) <= hi, (subject, len(imaged))
        for item in imaged:
            for img in item["images"]:
                assert Path(img["path"]).is_file(), img["path"]


def test_qa_images_and_needs_review_skipped() -> None:
    from app.practice.bank import _from_qa_json, reset_bank_cache

    reset_bank_cache()
    items = _from_qa_json("physics")
    assert items
    assert any(i.get("images") for i in items)
    # needs_review rows must not enter the CBT bank
    assert all("ncert" not in (i.get("topic") or "").lower() for i in items)


def test_load_full_qa_dataset() -> None:
    from app.evaluation.loader import load_qa_dataset

    items = load_qa_dataset()
    assert len(items) >= 1000
    assert any(i.get("images") for i in items)
    assert any(i.get("needs_review") for i in items)


def test_exam_meta_includes_bank() -> None:
    with _client() as client:
        res = client.get("/exams/meta")
        assert res.status_code == 200
        data = res.json()
        assert "bank" in data
        assert data["bank"]["english"]["total"] >= 40
