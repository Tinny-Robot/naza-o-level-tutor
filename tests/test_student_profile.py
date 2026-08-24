"""Learning Profile store, journal injection, plan refresh (no GGUF)."""

from __future__ import annotations

from pathlib import Path

from app.student.context import build_prompt_context, build_summary
from app.student.store import StudentStore, reset_student_store
from app.student.updater import LearningProfileUpdater


def test_store_seeds_and_journal_not_sessions(tmp_path: Path) -> None:
    reset_student_store()
    store = StudentStore(tmp_path / "student")
    updater = LearningProfileUpdater(store)
    updater.apply_event(
        {
            "kind": "practice",
            "subject": "chemistry",
            "topic": "Chemical Equilibrium",
            "correct": False,
            "confused": "Equilibrium ↔ Reaction rate",
        }
    )
    updater.apply_event(
        {
            "kind": "practice",
            "subject": "mathematics",
            "topic": "Algebra",
            "correct": True,
        }
    )
    ctx = build_prompt_context(store)
    assert "Tutor Persona" in ctx or "WAEC" in ctx
    assert "Learning journal" in ctx or "Getting stronger" in ctx or "struggles" in ctx
    assert "sessions/" not in ctx
    # Raw session files exist but are not injected
    assert list((tmp_path / "student" / "sessions").glob("*.json"))
    summary = build_summary(store)
    assert summary["learning_plan"]["items"]
    assert any(t["topic"] == "Chemical Equilibrium" for t in summary["weak_topics"]) or summary[
        "weak_topics"
    ]


def test_misconception_recorded(tmp_path: Path) -> None:
    store = StudentStore(tmp_path / "stu2")
    updater = LearningProfileUpdater(store)
    updater.record_misconception(
        subject="biology",
        topic="Transport",
        confused="Diffusion ↔ Osmosis",
    )
    items = store.misconceptions().items
    assert items and items[0].confused == "Diffusion ↔ Osmosis"
