"""Cached prompt templates loaded once from ``app/prompts/``."""

from __future__ import annotations

import warnings
from pathlib import Path

from app.config import PROMPTS_DIR
from app.utils.logging import get_logger

logger = get_logger(__name__)

_FALLBACK_SYSTEM = (
    "You are an O-Level tutor. Ground answers in the provided context. "
    "If context is insufficient, say so clearly."
)
_FALLBACK_USER = (
    "=== Context ===\n{context}\n\n=== Question ===\n{question}\n\n"
    "Answer using the context."
)
_FALLBACK_GENERAL_SYSTEM = (
    "You are a helpful offline assistant. Answer clearly. "
    "Do not invent citations or sources."
)
_FALLBACK_GENERAL_USER = "=== Question ===\n{question}\n\nAnswer helpfully and directly."
_FALLBACK_LESSON_SYSTEM = (
    "You are an experienced Nigerian secondary-school teacher. "
    "Return ONLY valid JSON for a structured O-Level lesson. "
    "Be friendly, clear, and exam-focused (WAEC/NECO/JAMB)."
)
_FALLBACK_LESSON_USER = (
    "=== Context ===\n{context}\n\n=== Student request ===\n{question}\n\n"
    "Return a JSON lesson object with title, introduction, objectives, sections, "
    "worked_example, check_understanding, practice, summary, revision_card, citations."
)
_FALLBACK_LESSON_COURSE_FRAME = (
    "=== Context ===\n{context}\n\n=== Student request ===\n{question}\n\n"
    "Return JSON for a course lesson FRAME: title, introduction, 3-5 objectives, "
    "5-7 sections with headings only (empty body), worked_example, "
    "check_understanding, practice, summary, revision_card. "
    "diagram_placeholder must be null."
)
_FALLBACK_LESSON_COURSE_SECTION = (
    "=== Context ===\n{context}\n\n=== Lesson title ===\n{lesson_title}\n"
    "=== Section heading ===\n{heading}\n\n=== Student request ===\n{question}\n\n"
    "Return JSON {{\"heading\": \"...\", \"body\": \"long multi-paragraph explanation\"}}."
)


class PromptManager:
    """Load study + general + lesson templates once; substitute per ask."""

    def __init__(self, prompts_dir: Path | None = None) -> None:
        self._dir = Path(prompts_dir) if prompts_dir is not None else PROMPTS_DIR
        self._system: str | None = None
        self._user: str | None = None
        self._general_system: str | None = None
        self._general_user: str | None = None
        self._lesson_system: str | None = None
        self._lesson_user: str | None = None
        self._lesson_course_frame: str | None = None
        self._lesson_course_section: str | None = None
        self._load_count = 0
        self._ensure_loaded()

    def _read_file(self, name: str, fallback: str) -> str:
        path = self._dir / name
        if not path.is_file():
            msg = f"Prompt file missing: {path}; using fallback."
            warnings.warn(msg, UserWarning, stacklevel=2)
            logger.warning(msg)
            return fallback
        return path.read_text(encoding="utf-8")

    def _ensure_loaded(self) -> None:
        if (
            self._system is not None
            and self._user is not None
            and self._general_system is not None
            and self._general_user is not None
            and self._lesson_system is not None
            and self._lesson_user is not None
        ):
            return
        self._system = self._read_file("system.txt", _FALLBACK_SYSTEM).strip()
        self._user = self._read_file("user.txt", _FALLBACK_USER).strip()
        self._general_system = self._read_file(
            "general_system.txt", _FALLBACK_GENERAL_SYSTEM
        ).strip()
        self._general_user = self._read_file(
            "general_user.txt", _FALLBACK_GENERAL_USER
        ).strip()
        self._lesson_system = self._read_file(
            "lesson_system.txt", _FALLBACK_LESSON_SYSTEM
        ).strip()
        self._lesson_user = self._read_file(
            "lesson_user.txt", _FALLBACK_LESSON_USER
        ).strip()
        self._load_count += 1
        logger.info("Loaded prompts from %s (load_count=%d)", self._dir, self._load_count)

    @property
    def load_count(self) -> int:
        """How many times templates were read from disk (1 after init)."""
        return self._load_count

    @property
    def system_prompt(self) -> str:
        self._ensure_loaded()
        assert self._system is not None
        return self._system

    @property
    def general_system_prompt(self) -> str:
        self._ensure_loaded()
        assert self._general_system is not None
        return self._general_system

    @property
    def lesson_system_prompt(self) -> str:
        self._ensure_loaded()
        assert self._lesson_system is not None
        return self._lesson_system

    def render_user(self, *, context: str, question: str) -> str:
        """Fill ``{context}`` / ``{question}`` without re-reading disk."""
        self._ensure_loaded()
        assert self._user is not None
        return self._user.format(context=context, question=question.strip())

    def render_general_user(self, *, question: str) -> str:
        """Fill ``{question}`` for General Conversation mode."""
        self._ensure_loaded()
        assert self._general_user is not None
        return self._general_user.format(question=question.strip())

    def render_lesson_user(self, *, context: str, question: str) -> str:
        """Fill lesson user template with retrieved context + student request."""
        self._ensure_loaded()
        assert self._lesson_user is not None
        return self._lesson_user.format(context=context, question=question.strip())

    def render_lesson_course_frame(self, *, context: str, question: str) -> str:
        """Learn-only pass A: lesson frame with section headings."""
        if self._lesson_course_frame is None:
            self._lesson_course_frame = self._read_file(
                "lesson_course_frame.txt", _FALLBACK_LESSON_COURSE_FRAME
            ).strip()
        return self._lesson_course_frame.format(
            context=context, question=question.strip()
        )

    def render_lesson_course_section(
        self,
        *,
        context: str,
        question: str,
        heading: str,
        lesson_title: str = "",
    ) -> str:
        """Learn-only pass B: long body for one section heading."""
        if self._lesson_course_section is None:
            self._lesson_course_section = self._read_file(
                "lesson_course_section.txt", _FALLBACK_LESSON_COURSE_SECTION
            ).strip()
        return self._lesson_course_section.format(
            context=context,
            question=question.strip(),
            heading=heading.strip(),
            lesson_title=lesson_title.strip(),
        )


# Process-wide cached manager (optional convenience).
_prompt_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    """Return a shared PromptManager singleton."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


def reset_prompt_manager() -> None:
    """Clear the singleton (tests only)."""
    global _prompt_manager
    _prompt_manager = None
