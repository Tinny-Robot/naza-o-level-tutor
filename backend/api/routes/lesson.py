"""Lesson routes: static sample + interactive feedback grading."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.generation.pipeline import GenerationPipeline
from app.lesson.lesson_engine import LessonEngine
from app.lesson.lesson_models import LessonFeedbackRequest
from app.student.store import get_student_store
from backend.api.data.content import LESSON
from backend.api.deps import get_pipeline

router = APIRouter(tags=["lesson"])


@router.get("/lesson")
def get_lesson() -> dict[str, Any]:
    """Sample interactive lesson payload (static demo screen)."""
    return LESSON


@router.post("/lesson/feedback")
def lesson_feedback(
    body: LessonFeedbackRequest,
    pipeline: GenerationPipeline = Depends(get_pipeline),
) -> dict[str, Any]:
    """Grade a check-understanding / practice answer with teaching feedback."""
    return LessonEngine(pipeline).grade(
        question=body.question,
        expected_answer=body.expected_answer,
        student_answer=body.student_answer,
        explanation=body.explanation,
        kind=body.kind,
        title=body.title,
        language=get_student_store().preferences().language,
    )
