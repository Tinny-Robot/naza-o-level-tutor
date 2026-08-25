"""Persistent local JSON store for student profile, preferences, and mastery."""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import STUDENT_DIR
from app.student.models import (
    Goals,
    MasteryState,
    MisconceptionsState,
    Preferences,
    Profile,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_GLOBAL_STORE: StudentStore | None = None


def _utc_now() -> str:
    """ISO 8601 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


class StudentStore:
    """Store student state in JSON files under student/."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else STUDENT_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = self.root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Corrupt JSON file at %s", path)
            return None

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        with _lock:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(path)

    # -----------------------------------------------------------------------
    # Preferences
    # -----------------------------------------------------------------------

    def preferences(self) -> Preferences:
        path = self.root / "preferences.json"
        data = self._read_json(path)
        if data is None:
            return Preferences(language="English", onboarded=False)

        from app.i18n.language import normalize_language

        norm_lang = normalize_language(data.get("language"))
        has_onboarded = "onboarded" in data
        onboarded = bool(data.get("onboarded", True))

        prefs = Preferences(
            language=norm_lang,
            explanation_style=str(data.get("explanation_style") or "balanced"),
            show_citations=bool(data.get("show_citations", True)),
            onboarded=onboarded,
        )

        # If data was rewritten (e.g. stale third language or missing onboarded flag), persist it
        if data.get("language") != norm_lang or not has_onboarded:
            self.save_preferences(prefs)

        return prefs

    def save_preferences(self, prefs: Preferences) -> Preferences:
        from app.i18n.language import normalize_language

        prefs.language = normalize_language(prefs.language)
        path = self.root / "preferences.json"
        self._write_json(path, prefs.to_dict())
        return prefs

    # -----------------------------------------------------------------------
    # Profile & Goals
    # -----------------------------------------------------------------------

    def profile(self) -> Profile:
        path = self.root / "profile.json"
        data = self._read_json(path)
        if data is None:
            return Profile(updated_at=_utc_now())
        return Profile.from_dict(data)

    def save_profile(self, profile: Profile) -> Profile:
        profile.updated_at = _utc_now()
        path = self.root / "profile.json"
        self._write_json(path, profile.to_dict())
        return profile

    def goals(self) -> Goals:
        path = self.root / "goals.json"
        data = self._read_json(path)
        if data is None:
            return Goals(updated_at=_utc_now())
        return Goals.from_dict(data)

    def save_goals(self, goals: Goals) -> Goals:
        goals.updated_at = _utc_now()
        path = self.root / "goals.json"
        self._write_json(path, goals.to_dict())
        return goals

    # -----------------------------------------------------------------------
    # Mastery & Misconceptions
    # -----------------------------------------------------------------------

    def mastery(self) -> MasteryState:
        path = self.root / "mastery.json"
        data = self._read_json(path)
        if data is None:
            return MasteryState()
        return MasteryState.from_dict(data)

    def save_mastery(self, mastery: MasteryState) -> MasteryState:
        path = self.root / "mastery.json"
        self._write_json(path, mastery.to_dict())
        return mastery

    def misconceptions(self) -> MisconceptionsState:
        path = self.root / "misconceptions.json"
        data = self._read_json(path)
        if data is None:
            return MisconceptionsState()
        return MisconceptionsState.from_dict(data)

    def save_misconceptions(self, misc: MisconceptionsState) -> MisconceptionsState:
        path = self.root / "misconceptions.json"
        self._write_json(path, misc.to_dict())
        return misc

    # -----------------------------------------------------------------------
    # Sessions
    # -----------------------------------------------------------------------

    def record_session(self, event: dict[str, Any]) -> None:
        now_str = _utc_now().replace(":", "-")
        rand = secrets.token_hex(4)
        path = self.sessions_dir / f"{now_str}_{rand}.json"
        payload = {"recorded_at": _utc_now(), **event}
        self._write_json(path, payload)

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for path in sorted(self.sessions_dir.glob("*.json"), reverse=True)[:limit]:
            data = self._read_json(path)
            if isinstance(data, dict):
                sessions.append(data)
        return sessions


def get_student_store(root: Path | str | None = None) -> StudentStore:
    global _GLOBAL_STORE
    if root is not None:
        return StudentStore(root)
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = StudentStore()
    return _GLOBAL_STORE


def reset_student_store() -> None:
    global _GLOBAL_STORE
    _GLOBAL_STORE = None

