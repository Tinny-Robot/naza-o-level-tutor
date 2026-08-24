"""Canonical English / Hausa setting for UI and generation."""

from __future__ import annotations

from typing import Any

SUPPORTED_LANGUAGES: tuple[str, str] = ("English", "Hausa")

ENGLISH_INSTRUCTION = (
    "Respond entirely in English using clear language suitable for an O-Level student. "
    "JSON keys must stay in English. All human-readable teaching string values must be English. "
    "Keep necessary scientific or exam terms in their usual English form."
)

HAUSA_INSTRUCTION = (
    "Respond entirely in Hausa. Use clear, natural Hausa suitable for an O-Level student. "
    "Do not switch to English unless an English technical term is necessary for clarity. "
    "JSON keys must stay in English. All human-readable teaching string values must be Hausa. "
    "Keep necessary scientific or exam terms in English when Hausa would be unclear."
)

_ALIASES: dict[str, str] = {
    "english": "English",
    "en": "English",
    "eng": "English",
    "hausa": "Hausa",
    "ha": "Hausa",
    "hau": "Hausa",
}


def normalize_language(value: Any) -> str:
    """Return English or Hausa. Unknown / third languages become English."""
    raw = str(value or "").strip()
    if not raw:
        return "English"
    mapped = _ALIASES.get(raw.lower())
    if mapped:
        return mapped
    if raw in SUPPORTED_LANGUAGES:
        return raw
    return "English"


def language_instruction(language: Any = None) -> str:
    """Hard generation instruction for the selected language."""
    if normalize_language(language) == "Hausa":
        return HAUSA_INSTRUCTION
    return ENGLISH_INSTRUCTION


def resolve_language(explicit: Any = None, store: Any | None = None) -> str:
    """Prefer an explicit argument, else the student preference store."""
    if explicit is not None and str(explicit).strip():
        return normalize_language(explicit)
    try:
        if store is None:
            from app.student.store import get_student_store

            store = get_student_store()
        return normalize_language(store.preferences().language)
    except Exception:
        return "English"
