"""GET /revision - flashcard + strength payload."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.api.data.content import REVISION

router = APIRouter(tags=["revision"])


@router.get("/revision")
def get_revision() -> dict[str, Any]:
    return REVISION
