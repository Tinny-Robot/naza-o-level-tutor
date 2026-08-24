"""Adaptive practice endpoints (learning mode - not CBT exams)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.i18n.messages import ui_string
from app.practice.bank import SUBJECTS, grade_choice, list_topics, sample_questions
from app.student.context import build_summary
from app.student.store import get_student_store
from app.student.updater import LearningProfileUpdater

router = APIRouter(prefix="/practice", tags=["practice"])


class NextBody(BaseModel):
    subject: str = "chemistry"
    topic: str | None = None
    exam: str = "WAEC"
    n: int = Field(default=1, ge=1, le=20)


class AnswerBody(BaseModel):
    subject: str
    topic: str = ""
    question_id: str = ""
    question: str
    options: list[str] = Field(default_factory=list)
    answer: str  # expected
    student_answer: str
    explanation: str = ""


@router.get("/subjects")
def practice_subjects() -> dict[str, Any]:
    return {"subjects": list(SUBJECTS)}


@router.get("/topics")
def practice_topics(subject: str = "chemistry") -> dict[str, Any]:
    subject = subject.lower().strip()
    if subject not in SUBJECTS:
        raise HTTPException(status_code=400, detail="Unknown subject")
    return {"subject": subject, "topics": list_topics(subject)}


@router.post("/next")
def practice_next(body: NextBody) -> dict[str, Any]:
    subject = body.subject.lower().strip()
    if subject not in SUBJECTS:
        raise HTTPException(status_code=400, detail="Unknown subject")
    store = get_student_store()
    weak = [t.topic for t in sorted(store.mastery().topics, key=lambda x: x.score) if t.subject == subject]
    prefer = [body.topic] if body.topic else weak[:3]
    items = sample_questions(
        subject=subject,
        exam=body.exam,
        topic=body.topic,
        n=body.n,
        prefer_topics=[p for p in prefer if p],
    )
    if not items:
        raise HTTPException(status_code=404, detail=ui_string("no_questions"))
    # Strip answers when n>1 for multi packs; for single next keep answer server-side only in grade
    public = []
    for q in items:
        public.append(
            {
                "id": q["id"],
                "subject": q["subject"],
                "topic": q["topic"],
                "exam_board": q["exam_board"],
                "jamb_style": q.get("jamb_style", False),
                "year": q["year"],
                "question": q["question"],
                "options": q["options"],
                # Keep for offline grade endpoint simplicity (desktop is trusted local)
                "answer": q["answer"],
                "explanation": q["explanation"],
            }
        )
    return {"items": public}


@router.post("/answer")
def practice_answer(body: AnswerBody) -> dict[str, Any]:
    question = {
        "answer": body.answer,
        "explanation": body.explanation,
        "topic": body.topic,
        "question": body.question,
        "options": body.options,
    }
    result = grade_choice(
        question,
        body.student_answer,
        language=get_student_store().preferences().language,
    )
    LearningProfileUpdater().apply_event(
        {
            "kind": "practice",
            "subject": body.subject,
            "topic": body.topic,
            "correct": result["correct"],
            "confused": result.get("confused"),
            "label": body.topic or body.question[:60],
            "question_id": body.question_id,
        }
    )
    return {
        **result,
        "encouragement": (
            ui_string("practice_ok")
            if result["correct"]
            else ui_string("practice_retry")
        ),
        "summary": build_summary(),
    }
