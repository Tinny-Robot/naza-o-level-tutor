"""Unit tests for structured lesson models, formatter, and engine (no GGUF)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.generation.pipeline import GenerationPipeline, blend_confidence
from app.generation.prompt_manager import PromptManager
from app.generation.rag import RetrievalService
from app.generation.router import QueryMode
from app.lesson.lesson_engine import LessonEngine, extract_topic
from app.lesson.lesson_formatter import (
    answers_match,
    extract_json_object,
    fallback_lesson,
    format_feedback,
    format_lesson,
)


class _FixedRouter:
    def __init__(self, mode: QueryMode) -> None:
        self.mode = mode

    def classify(self, question: str) -> QueryMode:
        return self.mode


class _StubLLM:
    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []
        self.fail = False

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise RuntimeError("llm down")
        return self.response


class _StubRetriever:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self._results = results if results is not None else [
            {
                "score": 0.9,
                "text": "Equilibrium is a state of balance of forces.",
                "metadata": {
                    "id": "eq-1",
                    "subject": "physics",
                    "topic": "equilibrium",
                    "source": "notes",
                },
            }
        ]

    def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[dict[str, Any]]:
        return self._results[:top_k]


def _valid_lesson_json(**overrides: Any) -> str:
    payload = {
        "type": "lesson",
        "title": "Equilibrium",
        "introduction": "Let's learn equilibrium together.",
        "objectives": ["Define equilibrium", "Solve a force problem"],
        "sections": [
            {
                "heading": "What it means",
                "body": "Forces balance [Chunk eq-1].",
                "diagram_placeholder": "Force diagram",
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
            "options": ["A. Net force zero", "B. Always moving", "C. Hot", "D. Soft"],
            "correct_answer": "A",
            "explanation": "Net force (and often net moment) is zero.",
        },
        "summary": ["Balance of forces", "Draw free-body diagrams"],
        "revision_card": {"front": "Equilibrium?", "back": "Net force = 0"},
        "citations": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


def test_extract_json_from_fenced_block() -> None:
    raw = "Here you go:\n```json\n{\"title\": \"X\", \"objectives\": []}\n```\n"
    data = extract_json_object(raw)
    assert data is not None
    assert data["title"] == "X"


def test_sanitize_section_body_unwraps_fenced_json() -> None:
    from app.lesson.lesson_formatter import sanitize_section_body

    raw = (
        '```json\n{"heading": "Menene Set?", "body": "Set shine tattara. '
        '[Chunk abc123]\\n\\nRoster: V = {a,e,i}."}\n```'
    )
    body = sanitize_section_body(raw, heading="Yadda za ka tuna da shi")
    assert "```" not in body
    assert "heading" not in body
    assert "Set shine tattara" in body
    assert "[Chunk" not in body
    assert "Roster" in body


def test_sanitize_section_body_recovers_truncated_json() -> None:
    from app.lesson.lesson_formatter import sanitize_section_body

    raw = (
        '```json\n{\n  "heading": "Menene Set?",\n  "body": '
        '"A matsayin dalibi, set shine tattara [Chunk deadbeef].\\n\\n'
        'Wannan sanin menene set yana da muhimmanci.'
        # truncated - no closing quote/brace/fence
    )
    body = sanitize_section_body(raw)
    assert "```" not in body
    assert "A matsayin dalibi" in body
    assert "[Chunk" not in body


def test_format_lesson_rejects_json_blob_section_body() -> None:
    raw = json.dumps(
        {
            "title": "Sets",
            "introduction": "Welcome.",
            "sections": [
                {
                    "heading": "How to remember it",
                    "body": '```json\n{"heading": "What is a set?", "body": "A set is a collection."}\n```',
                }
            ],
            "practice": {"question": "Q?", "correct_answer": "A", "options": ["A", "B", "C", "D"]},
        }
    )
    lesson = format_lesson(raw, topic="Sets")
    assert lesson.sections
    assert "```" not in lesson.sections[0].body
    assert "A set is a collection" in lesson.sections[0].body


def test_format_lesson_malformed_uses_safe_fallback() -> None:
    lesson = format_lesson("not json at all {{{", topic="Refraction", confidence=0.4)
    assert lesson.type == "lesson"
    assert lesson.title == "Refraction"
    assert lesson.introduction
    assert lesson.objectives
    assert lesson.sections
    assert lesson.practice.question
    assert lesson.revision_card.front
    assert lesson.confidence == 0.4


def test_format_lesson_partial_fills_gaps() -> None:
    raw = json.dumps(
        {
            "title": "Ohm's law",
            "introduction": "Welcome.",
            "sections": [{"heading": "Idea", "body": "V = IR"}],
        }
    )
    lesson = format_lesson(raw, topic="Ohm's law")
    assert lesson.title == "Ohm's law"
    assert lesson.introduction == "Welcome."
    assert lesson.sections[0].body == "V = IR"
    assert lesson.practice.question  # filled from fallback
    assert lesson.check_understanding.question


def test_format_lesson_valid_json() -> None:
    lesson = format_lesson(
        _valid_lesson_json(),
        topic="Equilibrium",
        citations=[{"chunk_id": "eq-1", "score": 0.9}],
        confidence=0.88,
    )
    assert lesson.title == "Equilibrium"
    assert len(lesson.sections) == 1
    assert lesson.worked_example.answer == "In equilibrium"
    assert lesson.practice.correct_answer == "A"
    assert lesson.citations[0]["chunk_id"] == "eq-1"


def test_fallback_lesson_shape() -> None:
    lesson = fallback_lesson(topic="Concord")
    dumped = lesson.model_dump()
    assert dumped["type"] == "lesson"
    assert dumped["mode"] == "lesson"
    for key in (
        "title",
        "introduction",
        "objectives",
        "sections",
        "worked_example",
        "check_understanding",
        "practice",
        "summary",
        "revision_card",
        "citations",
    ):
        assert key in dumped


def test_answers_match_option_letter() -> None:
    assert answers_match("A", "A")
    assert answers_match("A", "A. Net force zero")
    assert answers_match("balanced forces", "A state of balanced forces")


def test_format_feedback_never_only_correct() -> None:
    fb = format_feedback(
        "Correct.",
        correct=True,
        explanation="Net force is zero at equilibrium.",
        expected_answer="A",
    )
    assert fb.correct is True
    assert "correct." != fb.feedback.strip().lower()
    assert "Net force" in fb.feedback or "equilibrium" in fb.feedback.lower() or "A" in fb.feedback


def test_format_feedback_plain_prose() -> None:
    fb = format_feedback(
        "Good try - remember net force must be zero.",
        correct=False,
        expected_answer="A",
    )
    assert "net force" in fb.feedback.lower()


# ---------------------------------------------------------------------------
# Engine + pipeline
# ---------------------------------------------------------------------------


def test_extract_topic() -> None:
    assert extract_topic("Teach me equilibrium.") == "equilibrium"
    assert "refraction" in extract_topic("lesson on refraction").lower()


def test_lesson_engine_teach_parses_llm_json() -> None:
    llm = _StubLLM(_valid_lesson_json())
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=_StubRetriever()),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        prompts=PromptManager(),
        router=_FixedRouter(QueryMode.LESSON),  # type: ignore[arg-type]
    )
    engine = LessonEngine(pipeline)
    result = engine.teach("Teach me equilibrium.")
    assert result["type"] == "lesson"
    assert result["title"] == "Equilibrium"
    assert result["mode"] == "lesson"
    assert result["citations"]
    assert llm.calls
    system, user = llm.calls[0]
    assert system
    assert "Teach me equilibrium" in user
    assert "[Chunk" in user or "Context" in user
    assert any(
        (section.get("diagram_svg") or "").lstrip().startswith("<svg")
        for section in result["sections"]
    )


def test_lesson_engine_llm_failure_fallback() -> None:
    llm = _StubLLM()
    llm.fail = True
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=_StubRetriever()),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        prompts=PromptManager(),
        router=_FixedRouter(QueryMode.LESSON),  # type: ignore[arg-type]
    )
    result = LessonEngine(pipeline).teach("Teach me waves.")
    assert result["type"] == "lesson"
    assert result["title"]
    assert result["practice"]["question"]


def test_pipeline_ask_routes_lesson_mode() -> None:
    llm = _StubLLM(_valid_lesson_json())
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=_StubRetriever()),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        prompts=PromptManager(),
        router=_FixedRouter(QueryMode.LESSON),  # type: ignore[arg-type]
    )
    result = pipeline.ask("Teach me equilibrium.")
    assert result["type"] == "lesson"
    assert result["mode"] == "lesson"


def test_pipeline_study_still_returns_chat_type() -> None:
    llm = _StubLLM("Concord is agreement.")
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=_StubRetriever()),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        prompts=PromptManager(),
        router=_FixedRouter(QueryMode.STUDY),  # type: ignore[arg-type]
    )
    result = pipeline.ask("Explain concord")
    assert result["type"] == "chat"
    assert result["mode"] == "study"
    assert result["answer"] == "Concord is agreement."
    assert result["confidence"] == pytest.approx(blend_confidence([0.9]))


def test_lesson_engine_grade_uses_explanation_fallback() -> None:
    llm = _StubLLM()
    llm.fail = True
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=_StubRetriever()),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        prompts=PromptManager(),
        router=_FixedRouter(QueryMode.LESSON),  # type: ignore[arg-type]
    )
    out = LessonEngine(pipeline).grade(
        question="When is equilibrium?",
        expected_answer="A",
        student_answer="A",
        explanation="Net force is zero.",
        kind="practice",
    )
    assert out["type"] == "feedback"
    assert out["correct"] is True
    assert "Net force" in out["feedback"]
    assert out["feedback"].strip().lower() not in {"correct.", "correct"}
