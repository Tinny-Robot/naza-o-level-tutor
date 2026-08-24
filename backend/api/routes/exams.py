"""Mock exam CBT sessions (WAEC / NECO / JAMB-style)."""

from __future__ import annotations

import secrets
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.practice.bank import (
    SUBJECTS,
    EXAM_BOARDS,
    bank_stats,
    grade_choice,
    sample_questions,
)
from app.student.context import build_summary
from app.student.store import get_student_store
from app.student.updater import LearningProfileUpdater

router = APIRouter(prefix="/exams", tags=["exams"])

_SESSIONS: dict[str, dict[str, Any]] = {}


class StartBody(BaseModel):
    exam: str = "WAEC"
    subject: str = "physics"
    n: int = Field(default=10, ge=5, le=60)
    minutes: int = Field(default=15, ge=5, le=180)


class SubmitBody(BaseModel):
    session_id: str
    answers: dict[str, str] = Field(default_factory=dict)  # question id -> A/B/C/D
    flagged: list[str] = Field(default_factory=list)


def _public_item(q: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": q["id"],
        "topic": q["topic"],
        "question": q["question"],
        "passage": q.get("passage"),
        "options": q["options"],
        "year": q["year"],
        "exam_board": q["exam_board"],
        "paper_type": q.get("paper_type") or "Objective",
        "jamb_style": q.get("jamb_style", False),
        "images": q.get("images") or [],
    }


@router.get("/meta")
def exams_meta() -> dict[str, Any]:
    stats = bank_stats()
    return {
        "exams": list(EXAM_BOARDS),
        "subjects": list(SUBJECTS),
        "sizes": [10, 20, 40],
        "bank": stats,
    }


@router.post("/start")
def exams_start(body: StartBody) -> dict[str, Any]:
    subject = body.subject.lower().strip()
    exam = body.exam.upper().strip()
    if subject not in SUBJECTS:
        raise HTTPException(status_code=400, detail="Unknown subject")
    if exam not in EXAM_BOARDS:
        raise HTTPException(status_code=400, detail="Unknown exam")
    items = sample_questions(subject=subject, exam=exam, n=body.n)
    if not items:
        raise HTTPException(status_code=404, detail="No questions for this exam/subject")
    session_id = secrets.token_hex(8)
    public_items = []
    key = {}
    for q in items:
        key[q["id"]] = q
        public_items.append(_public_item(q))
    _SESSIONS[session_id] = {
        "exam": exam,
        "subject": subject,
        "items": key,
        "public": public_items,
        "started_at": time.time(),
        "duration_s": body.minutes * 60,
        "paused_s": 0.0,
        "pause_started": None,
    }
    return {
        "session_id": session_id,
        "exam": exam,
        "subject": subject,
        "duration_s": body.minutes * 60,
        "requested": body.n,
        "delivered": len(public_items),
        "items": public_items,
    }


@router.post("/submit")
def exams_submit(body: SubmitBody) -> dict[str, Any]:
    session = _SESSIONS.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Exam session not found")
    language = get_student_store().preferences().language
    items: dict[str, dict[str, Any]] = session["items"]
    results = []
    wrong_topics: list[dict[str, Any]] = []
    topic_stats: dict[str, dict[str, int]] = {}
    correct_n = 0
    for qid, q in items.items():
        topic = str(q.get("topic") or "General")
        topic_stats.setdefault(topic, {"correct": 0, "total": 0})
        topic_stats[topic]["total"] += 1
        student = body.answers.get(qid, "")
        graded = grade_choice(q, student, language=language)
        if graded["correct"]:
            correct_n += 1
            topic_stats[topic]["correct"] += 1
        else:
            wrong_topics.append(
                {
                    "subject": session["subject"],
                    "topic": topic,
                    "confused": graded.get("confused"),
                    "question": q.get("question"),
                    "expected": graded.get("expected"),
                    "student_answer": student,
                    "explanation": graded.get("explanation"),
                }
            )
        results.append(
            {
                "id": qid,
                "topic": topic,
                "correct": graded["correct"],
                "expected": graded["expected"],
                "student_answer": student,
                "explanation": graded["explanation"],
                "flagged": qid in body.flagged,
            }
        )
    total = len(items) or 1
    score_pct = round(100.0 * correct_n / total, 1)
    breakdown = [
        {
            "topic": topic,
            "correct": stats["correct"],
            "total": stats["total"],
            "accuracy": round(stats["correct"] / stats["total"], 3) if stats["total"] else 0,
        }
        for topic, stats in sorted(topic_stats.items())
    ]
    weak = [b["topic"] for b in breakdown if b["accuracy"] < 0.6]
    LearningProfileUpdater().apply_event(
        {
            "kind": "exam",
            "subject": session["subject"],
            "topic": "",
            "score_pct": score_pct,
            "wrong_topics": wrong_topics,
            "label": f"{session['exam']} {session['subject']} mock",
            "flagged": body.flagged,
        }
    )
    # Drop session after submit
    _SESSIONS.pop(body.session_id, None)
    return {
        "exam": session["exam"],
        "subject": session["subject"],
        "score_pct": score_pct,
        "correct": correct_n,
        "total": total,
        "breakdown": breakdown,
        "weak_topics": weak,
        "incorrect": wrong_topics,
        "results": results,
        "summary": build_summary(),
    }
