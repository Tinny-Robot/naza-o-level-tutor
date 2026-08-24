"""Learn hub: persistent mini-courses, suggestions, assessment from the bank."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.learn.models import COURSE_STATUSES, public_course
from app.learn.planner import (
    generate_lesson,
    infer_subject,
    plan_course,
    record_lesson_outcome,
    suggest_lectures,
    clear_course_payloads_for_language,
)
from app.learn.store import get_course_store, valid_status
from app.practice.bank import sample_questions
from app.student.store import get_student_store
from backend.api.deps import get_pipeline

router = APIRouter(prefix="/learn", tags=["learn"])


class PlanBody(BaseModel):
    topic: str = Field(..., min_length=1)
    subject: str | None = None
    goal: str = "understand"
    confidence: str = "some"
    style: str = "worked_examples"
    exam: str | None = None


class CompleteBody(BaseModel):
    check_correct: bool | None = None
    practice_correct: bool | None = None
    struggled: bool = False


class ProgressBody(BaseModel):
    current_index: int | None = None
    status: str | None = None
    lesson_id: str | None = None


def _course_or_404(course_id: str) -> dict[str, Any]:
    course = get_course_store().get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("/courses")
def list_courses(status: str | None = None) -> dict[str, Any]:
    if status and status not in COURSE_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status")
    items = get_course_store().list_courses(status=status)
    return {"courses": items}


@router.get("/suggestions")
def list_suggestions(limit: int = 4) -> dict[str, Any]:
    return {"suggestions": suggest_lectures(limit=max(1, min(limit, 8)))}


@router.post("/plan")
def create_plan(body: PlanBody, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    try:
        course = plan_course(
            topic=body.topic,
            goal=body.goal,
            confidence=body.confidence,
            style=body.style,
            subject=body.subject,
            exam=body.exam,
            pipeline=pipeline,
            language=get_student_store().preferences().language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return public_course(course, include_payloads=False)


@router.get("/courses/{course_id}")
def get_course(course_id: str) -> dict[str, Any]:
    return public_course(_course_or_404(course_id), include_payloads=True)


@router.post("/courses/{course_id}/lessons/{lesson_id}/generate")
def generate_course_lesson(
    course_id: str,
    lesson_id: str,
    pipeline=Depends(get_pipeline),
) -> dict[str, Any]:
    course = _course_or_404(course_id)
    try:
        course = generate_lesson(
            course,
            lesson_id,
            pipeline=pipeline,
            language=course.get("language") or get_student_store().preferences().language,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lesson not found") from exc
    return public_course(course, include_payloads=True)


@router.post("/courses/{course_id}/lessons/{lesson_id}/complete")
def complete_course_lesson(
    course_id: str,
    lesson_id: str,
    body: CompleteBody,
) -> dict[str, Any]:
    course = _course_or_404(course_id)
    try:
        course = record_lesson_outcome(
            course,
            lesson_id,
            body.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lesson not found") from exc
    return public_course(course, include_payloads=True)


@router.post("/courses/{course_id}/progress")
def update_course_progress(course_id: str, body: ProgressBody) -> dict[str, Any]:
    course = _course_or_404(course_id)
    lessons = list(course.get("lessons") or [])
    if body.lesson_id:
        for idx, item in enumerate(lessons):
            if item.get("id") == body.lesson_id:
                course["current_index"] = idx
                break
        else:
            raise HTTPException(status_code=404, detail="Lesson not found")
    elif body.current_index is not None:
        if not lessons:
            course["current_index"] = 0
        else:
            course["current_index"] = max(0, min(body.current_index, len(lessons) - 1))
    if body.status:
        status = valid_status(body.status)
        if not status:
            raise HTTPException(status_code=400, detail="Unknown status")
        course["status"] = status
    get_course_store().save(course)
    return public_course(course, include_payloads=True)


@router.post("/courses/{course_id}/regenerate")
def regenerate_course(course_id: str) -> dict[str, Any]:
    """Clear cached lesson payloads and rebuild later in the current UI language."""
    course = _course_or_404(course_id)
    language = get_student_store().preferences().language
    course = clear_course_payloads_for_language(course, language)
    return public_course(course, include_payloads=False)


@router.post("/courses/{course_id}/assess")
def assess_course(course_id: str, n: int = 6) -> dict[str, Any]:
    course = _course_or_404(course_id)
    subject = infer_subject(str(course.get("topic") or ""), str(course.get("subject") or ""))
    exam = str(course.get("exam") or get_student_store().goals().target_exam or "WAEC")
    items = sample_questions(
        subject=subject,
        exam=exam,
        topic=str(course.get("topic") or "") or None,
        n=max(3, min(n, 10)),
    )
    public_items = []
    for q in items:
        public_items.append(
            {
                "id": q.get("id"),
                "topic": q.get("topic"),
                "question": q.get("question"),
                "passage": q.get("passage"),
                "options": q.get("options") or [],
                "year": q.get("year"),
                "exam_board": q.get("exam_board"),
                "images": q.get("images") or [],
                "answer": q.get("answer"),
                "explanation": q.get("explanation") or "",
            }
        )
    return {
        "course_id": course_id,
        "subject": subject,
        "topic": course.get("topic"),
        "items": public_items,
    }
