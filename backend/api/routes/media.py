"""Serve local textbook/extracted images for lesson diagrams (loopback only)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import DATA_DIR, PROJECT_ROOT

router = APIRouter(tags=["media"])

_ALLOWED_ROOTS = (
    DATA_DIR.resolve(),
    (PROJECT_ROOT / "data").resolve(),
)


def _safe_path(raw: str) -> Path:
    text = unquote(raw).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing path")
    path = Path(text)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    else:
        path = path.resolve()
    if not any(path.is_relative_to(root) for root in _ALLOWED_ROOTS):
        raise HTTPException(status_code=403, detail="Path not allowed")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise HTTPException(status_code=400, detail="Unsupported media type")
    return path


@router.get("/media")
def get_media(path: str) -> FileResponse:
    file_path = _safe_path(path)
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }[file_path.suffix.lower()]
    return FileResponse(file_path, media_type=media)
