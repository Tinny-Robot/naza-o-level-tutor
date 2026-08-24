"""Course / lecture objects persisted under student/courses/."""

from __future__ import annotations

from typing import Any, Literal

COURSE_STATUSES = ("draft", "in_progress", "completed", "archived")
LESSON_STATUSES = ("pending", "ready", "complete", "skipped")
LESSON_KINDS = ("concept", "examples", "assessment", "remedial")
ACTION_KINDS = ("continue", "remediate", "practice")
GOALS = ("understand", "exam", "master", "basics")
CONFIDENCE_LEVELS = ("beginner", "some", "confident")
STYLES = ("worked_examples", "examples_first", "visual", "exam")
SUBJECTS = ("english", "mathematics", "physics", "chemistry")

CourseStatus = Literal["draft", "in_progress", "completed", "archived"]
LessonStatus = Literal["pending", "ready", "complete", "skipped"]
ActionKind = Literal["continue", "remediate", "practice"]


def empty_next_action() -> dict[str, Any]:
    return {"kind": "continue", "reason": "", "lesson_id": ""}


def empty_outcome() -> dict[str, Any]:
    return {
        "check_correct": None,
        "practice_correct": None,
        "struggled": False,
        "completed_at": "",
    }


def new_lesson(
    *,
    lesson_id: str,
    title: str,
    kind: str = "concept",
    rationale: str = "",
    status: str = "pending",
) -> dict[str, Any]:
    return {
        "id": lesson_id,
        "title": title,
        "kind": kind if kind in LESSON_KINDS else "concept",
        "rationale": rationale,
        "status": status if status in LESSON_STATUSES else "pending",
        "payload": None,
        "outcome": None,
    }


def new_course(
    *,
    course_id: str,
    title: str,
    subject: str,
    topic: str,
    goal: str = "understand",
    confidence: str = "some",
    style: str = "worked_examples",
    exam: str = "WAEC",
    objective: str = "",
    status: str = "in_progress",
    lessons: list[dict[str, Any]] | None = None,
    skipped: list[dict[str, Any]] | None = None,
    created_at: str = "",
    language: str = "English",
) -> dict[str, Any]:
    items = lessons or []
    first_id = items[0]["id"] if items else ""
    lang = language if language in ("English", "Hausa") else "English"
    return {
        "id": course_id,
        "title": title,
        "subject": subject,
        "topic": topic,
        "goal": goal if goal in GOALS else "understand",
        "confidence": confidence if confidence in CONFIDENCE_LEVELS else "some",
        "style": style if style in STYLES else "worked_examples",
        "exam": exam or "WAEC",
        "objective": objective or f"Understand {topic} and practise exam-style questions.",
        "status": status if status in COURSE_STATUSES else "in_progress",
        "current_index": 0,
        "next_action": {
            "kind": "continue",
            "reason": "Start the first lesson.",
            "lesson_id": first_id,
        },
        "lessons": items,
        "skipped_because": skipped or [],
        "created_at": created_at,
        "updated_at": created_at,
        "language": lang,
    }


def lesson_progress(course: dict[str, Any]) -> dict[str, Any]:
    lessons = list(course.get("lessons") or [])
    total = len(lessons)
    done = sum(1 for item in lessons if item.get("status") == "complete")
    current = int(course.get("current_index") or 0)
    current = max(0, min(current, total - 1)) if total else 0
    current_title = lessons[current]["title"] if lessons else ""
    return {
        "total": total,
        "completed": done,
        "pct": round(100.0 * done / total, 1) if total else 0.0,
        "current_index": current,
        "current_title": current_title,
    }


def course_language(course: dict[str, Any]) -> str:
    raw = str(course.get("language") or "English")
    return raw if raw in ("English", "Hausa") else "English"


def public_course(course: dict[str, Any], *, include_payloads: bool = True) -> dict[str, Any]:
    """Copy safe for API responses."""
    out = dict(course)
    progress = lesson_progress(course)
    out["progress"] = progress
    out["language"] = course_language(course)
    if include_payloads:
        return out
    slim_lessons = []
    for item in course.get("lessons") or []:
        copy = {k: v for k, v in item.items() if k != "payload"}
        copy["has_payload"] = item.get("payload") is not None
        slim_lessons.append(copy)
    out["lessons"] = slim_lessons
    return out
