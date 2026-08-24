"""GET /progress - streak / XP / heatmap / mastery payload."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.api.data.content import PROGRESS

router = APIRouter(tags=["progress"])


@router.get("/progress")
def get_progress() -> dict[str, Any]:
    return PROGRESS
