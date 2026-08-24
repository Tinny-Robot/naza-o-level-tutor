"""English / Hausa language helpers for UI copy and LLM instructions."""

from app.i18n.language import (
    HAUSA_INSTRUCTION,
    ENGLISH_INSTRUCTION,
    SUPPORTED_LANGUAGES,
    language_instruction,
    normalize_language,
    resolve_language,
)
from app.i18n.messages import ui_string

__all__ = [
    "ENGLISH_INSTRUCTION",
    "HAUSA_INSTRUCTION",
    "SUPPORTED_LANGUAGES",
    "language_instruction",
    "normalize_language",
    "resolve_language",
    "ui_string",
]
