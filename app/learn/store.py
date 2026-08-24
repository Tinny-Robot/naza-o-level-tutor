"""Persist mini-courses under student/courses/."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.config import STUDENT_DIR
from app.learn.models import COURSE_STATUSES, public_course
from app.student.store import _utc_now
from app.utils.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()


class CourseStore:
    """One JSON file per course; gitignored with the rest of student/."""

    def __init__(self, root: Path | None = None) -> None:
        base = Path(root) if root is not None else STUDENT_DIR
        self.root = base / "courses"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, course_id: str) -> Path:
        safe = "".join(ch for ch in course_id if ch.isalnum() or ch in "-_")
        if not safe:
            raise ValueError("Invalid course id")
        return self.root / f"{safe}.json"

    def save(self, course: dict[str, Any]) -> dict[str, Any]:
        course_id = str(course.get("id") or "").strip()
        if not course_id:
            raise ValueError("Course missing id")
        course["updated_at"] = _utc_now()
        if not course.get("created_at"):
            course["created_at"] = course["updated_at"]
        path = self._path(course_id)
        with _lock:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(course, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(path)
        return course

    def get(self, course_id: str) -> dict[str, Any] | None:
        path = self._path(course_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Corrupt course file %s", path)
            return None
        if not isinstance(data, dict):
            return None
        from app.learn.models import course_language

        if "language" not in data:
            data["language"] = course_language(data)
            self.save(data)
        return data

    def list_courses(self, status: str | None = None) -> list[dict[str, Any]]:
        """List courses. Default hides archived. Pass status to filter exactly."""
        items: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            current = str(data.get("status") or "in_progress")
            if status:
                if current != status:
                    continue
            elif current == "archived":
                continue
            items.append(public_course(data, include_payloads=False))
        items.sort(key=lambda c: str(c.get("updated_at") or ""), reverse=True)
        return items

    def in_progress_topics(self) -> set[tuple[str, str]]:
        out: set[tuple[str, str]] = set()
        for course in self.list_courses(status="in_progress"):
            subject = str(course.get("subject") or "").lower()
            topic = str(course.get("topic") or "").strip().lower()
            if subject and topic:
                out.add((subject, topic))
        return out


def get_course_store(root: Path | None = None) -> CourseStore:
    return CourseStore(root)


def valid_status(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().lower()
    return text if text in COURSE_STATUSES else None
