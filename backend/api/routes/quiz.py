"""GET /quiz - current quiz question JSON."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.api.data.content import QUIZ

router = APIRouter(tags=["quiz"])


@router.get("/quiz")
def get_quiz() -> dict[str, Any]:
    return QUIZ
