"""English / Hausa language setting for prefs, UI backend copy, and LLM prompts."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.generation.pipeline import GenerationPipeline, personalized_system
from app.generation.prompt_manager import PromptManager
from app.generation.rag import RetrievalService
from app.generation.router import QueryMode
from app.i18n.language import (
    ENGLISH_INSTRUCTION,
    HAUSA_INSTRUCTION,
    language_instruction,
    normalize_language,
)
from app.learn.planner import fallback_outline
from app.lesson.lesson_engine import LessonEngine
from app.student.models import Preferences
from app.student.store import StudentStore, reset_student_store
from backend.api.main import create_app

_LESSON_JSON = json.dumps(
    {
        "type": "lesson",
        "title": "Equilibrium",
        "introduction": "Let's learn equilibrium.",
        "objectives": ["Define equilibrium"],
        "sections": [
            {
                "heading": "Meaning of equilibrium",
                "body": "A body is in equilibrium when net force and net moment are zero. "
                "WAEC and NECO ask you to state both conditions before any calculation. "
                "Opposing forces cancel, so 5 N right and 5 N left give 0 N net force.",
                "diagram_placeholder": None,
            }
        ],
        "worked_example": {
            "problem": "Two equal forces act opposite.",
            "steps": ["Draw forces", "Net force is zero"],
            "answer": "In equilibrium",
        },
        "check_understanding": {
            "question": "What is equilibrium?",
            "expected_answer": "A state of balanced forces",
            "hint": "Think balance",
        },
        "practice": {
            "question": "When is a body in equilibrium?",
            "options": ["A. Net force zero", "B. Always moving"],
            "correct_answer": "A",
            "explanation": "Net force is zero.",
        },
        "summary": ["Balance of forces"],
        "revision_card": {"front": "Equilibrium?", "back": "Net force = 0"},
        "citations": [],
        "image_refs": [],
    }
)


class _FixedRouter:
    def __init__(self, mode: QueryMode) -> None:
        self.mode = mode

    def classify(self, question: str) -> QueryMode:
        return self.mode


class _RecordingLLM:
    def __init__(self, reply: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self.reply = reply

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


class _StubRetriever:
    def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "score": 0.91,
                "text": "A body is in equilibrium when the net force and the net moment are zero.",
                "metadata": {
                    "id": "eq-1",
                    "subject": "physics",
                    "topic": "equilibrium",
                    "source": "notes",
                },
            }
        ][:top_k]


def _pipeline(llm: _RecordingLLM, mode: QueryMode) -> GenerationPipeline:
    return GenerationPipeline(
        retrieval=RetrievalService(retriever=_StubRetriever()),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        prompts=PromptManager(),
        router=_FixedRouter(mode),  # type: ignore[arg-type]
    )

HAUSA_SENTENCE = (
    "Respond entirely in Hausa. Use clear, natural Hausa suitable for an O-Level student. "
    "Do not switch to English unless an English technical term is necessary for clarity."
)
ENGLISH_SENTENCE = (
    "Respond entirely in English using clear language suitable for an O-Level student."
)


@asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pipeline = object()
    yield


def _client() -> TestClient:
    return TestClient(create_app(lifespan_fn=_noop_lifespan))


def test_normalize_language_coerces_third_and_empty() -> None:
    assert normalize_language("English") == "English"
    assert normalize_language("Hausa") == "Hausa"
    assert normalize_language("hausa") == "Hausa"
    assert normalize_language("ha") == "Hausa"
    assert normalize_language("Yoruba") == "English"
    assert normalize_language("Igbo") == "English"
    assert normalize_language("Pidgin") == "English"
    assert normalize_language("") == "English"
    assert normalize_language(None) == "English"
    assert normalize_language("French") == "English"


def test_language_instruction_contains_required_sentences() -> None:
    hausa = language_instruction("Hausa")
    english = language_instruction("English")
    assert HAUSA_SENTENCE in hausa
    assert ENGLISH_SENTENCE in english
    assert hausa == HAUSA_INSTRUCTION
    assert english == ENGLISH_INSTRUCTION
    assert language_instruction("Yoruba") == ENGLISH_INSTRUCTION


def test_personalized_system_includes_language_instruction() -> None:
    hausa = personalized_system("BASE_PROMPT", language="Hausa")
    english = personalized_system("BASE_PROMPT", language="English")
    assert HAUSA_SENTENCE in hausa
    assert "BASE_PROMPT" in hausa
    assert ENGLISH_SENTENCE in english
    assert "BASE_PROMPT" in english


def test_store_rewrites_stale_third_language(tmp_path: Path) -> None:
    root = tmp_path / "student"
    root.mkdir()
    (root / "preferences.json").write_text(
        json.dumps(
            {
                "language": "Yoruba",
                "explanation_style": "worked_examples",
                "show_citations": True,
            }
        ),
        encoding="utf-8",
    )
    store = StudentStore(root)
    prefs = store.preferences()
    assert prefs.language == "English"
    saved = json.loads((root / "preferences.json").read_text(encoding="utf-8"))
    assert saved["language"] == "English"


def test_store_save_normalizes_pidgin(tmp_path: Path) -> None:
    store = StudentStore(tmp_path / "stu")
    store.save_preferences(
        Preferences(language="Pidgin", explanation_style="concise", show_citations=True)
    )
    saved = json.loads((tmp_path / "stu" / "preferences.json").read_text(encoding="utf-8"))
    assert saved["language"] == "English"
    assert store.preferences().language == "English"


def test_patch_preferences_coerces_to_english(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr("app.config.STUDENT_DIR", tmp_path)
    monkeypatch.setattr("app.student.store.STUDENT_DIR", tmp_path)
    reset_student_store()
    try:
        with _client() as client:
            res = client.patch("/student/preferences", json={"language": "Igbo"})
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["preferences"]["language"] == "English"
            haus = client.patch("/student/preferences", json={"language": "Hausa"})
            assert haus.status_code == 200
            assert haus.json()["preferences"]["language"] == "Hausa"
            summary = client.get("/student/summary")
            assert summary.status_code == 200
            assert summary.json()["preferences"]["language"] == "Hausa"
    finally:
        reset_student_store()


def test_ask_system_prompt_includes_hausa_instruction() -> None:
    llm = _RecordingLLM("Concord means the verb agrees with the subject.")
    pipeline = _pipeline(llm, QueryMode.STUDY)
    pipeline.ask("Explain concord", top_k=2, language="Hausa")
    assert llm.calls
    system, _user = llm.calls[0]
    assert HAUSA_SENTENCE in system

    llm.calls.clear()
    pipeline.ask("Explain concord", top_k=2, language="English")
    system, _user = llm.calls[0]
    assert ENGLISH_SENTENCE in system


def test_teach_course_lesson_system_prompt_includes_hausa_instruction() -> None:
    llm = _RecordingLLM(_LESSON_JSON)
    LessonEngine(_pipeline(llm, QueryMode.LESSON)).teach_course_lesson(
        "Teach this course lesson on equilibrium.",
        subject="physics",
        topic="Equilibrium",
        query="Equilibrium Meaning of equilibrium Foundation terms",
        update_profile=False,
        language="Hausa",
    )
    systems = [system for system, _user in llm.calls]
    assert systems
    assert any(HAUSA_SENTENCE in system for system in systems)


def test_english_fallback_outline_keeps_what_is_title() -> None:
    outline = fallback_outline(
        topic="Quadratic Equations",
        subject="mathematics",
        confidence="beginner",
        language="English",
    )
    titles = [item["title"] for item in outline["lessons"]]
    assert any(title.startswith("What is") for title in titles)


def test_existing_prefs_missing_onboarded_are_treated_complete(tmp_path: Path) -> None:
    root = tmp_path / "student"
    root.mkdir()
    (root / "preferences.json").write_text(
        json.dumps(
            {
                "language": "Hausa",
                "explanation_style": "worked_examples",
                "show_citations": True,
            }
        ),
        encoding="utf-8",
    )
    store = StudentStore(root)
    prefs = store.preferences()
    assert prefs.onboarded is True
    saved = json.loads((root / "preferences.json").read_text(encoding="utf-8"))
    assert saved["onboarded"] is True
    assert saved["language"] == "Hausa"


def test_fresh_prefs_are_not_onboarded(tmp_path: Path) -> None:
    store = StudentStore(tmp_path / "fresh")
    assert store.preferences().onboarded is False


class _AskRecorder:
    def __init__(self) -> None:
        self.language: str | None = None

    def ask(self, message: str, history: Any = None, language: str | None = None, **kwargs: Any) -> dict[str, Any]:
        del message, history, kwargs
        self.language = language
        return {
            "type": "chat",
            "answer": "Concord is subject-verb agreement.",
            "text": "Concord is subject-verb agreement.",
            "mode": "study",
            "citations": [],
        }


def test_chat_route_passes_prefs_language_into_ask(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr("app.config.STUDENT_DIR", tmp_path)
    monkeypatch.setattr("app.student.store.STUDENT_DIR", tmp_path)
    reset_student_store()
    recorder = _AskRecorder()

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.pipeline = recorder
        yield

    try:
        StudentStore(tmp_path).save_preferences(
            Preferences(language="Hausa", onboarded=True)
        )
        with TestClient(create_app(lifespan_fn=_lifespan)) as client:
            res = client.post("/chat", json={"message": "Explain concord"})
            assert res.status_code == 200, res.text
        assert recorder.language == "Hausa"
        system = personalized_system("TUTOR", language=recorder.language)
        assert HAUSA_SENTENCE in system
    finally:
        reset_student_store()
