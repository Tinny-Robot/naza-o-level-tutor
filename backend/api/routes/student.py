"""Learning Profile summary / events / preferences (never branded as memory UI)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.i18n.language import normalize_language
from app.student.context import build_summary
from app.student.models import Preferences
from app.student.store import get_student_store
from app.student.updater import LearningProfileUpdater

router = APIRouter(prefix="/student", tags=["student"])


class EventBody(BaseModel):
    kind: str = "session"
    subject: str = ""
    topic: str = ""
    correct: bool | None = None
    confused: str | None = None
    label: str | None = None
    score_pct: float | None = None
    wrong_topics: list[dict[str, Any]] = Field(default_factory=list)


class PreferencesBody(BaseModel):
    language: str | None = None
    explanation_style: str | None = None
    show_citations: bool | None = None
    display_name: str | None = None
    goal_today: str | None = None
    onboarded: bool | None = None


@router.get("/summary")
def student_summary() -> dict[str, Any]:
    return build_summary()


@router.post("/event")
def student_event(body: EventBody) -> dict[str, Any]:
    updater = LearningProfileUpdater()
    result = updater.apply_event(body.model_dump(exclude_none=True))
    return {"ok": True, **result, "summary": build_summary()}


@router.patch("/preferences")
def patch_preferences(body: PreferencesBody) -> dict[str, Any]:
    store = get_student_store()
    prefs = store.preferences()
    if body.language is not None:
        prefs.language = normalize_language(body.language)
    if body.explanation_style is not None:
        prefs.explanation_style = body.explanation_style
    if body.show_citations is not None:
        prefs.show_citations = body.show_citations
    if body.onboarded is not None:
        prefs.onboarded = bool(body.onboarded)
    store.save_preferences(prefs)
    if body.display_name or body.goal_today:
        profile = store.profile()
        if body.display_name:
            profile.display_name = body.display_name
            store.save_profile(profile)
        if body.goal_today:
            goals = store.goals()
            goals.today = body.goal_today
            store.save_goals(goals)
    return {"ok": True, "preferences": prefs.__dict__, "summary": build_summary()}
