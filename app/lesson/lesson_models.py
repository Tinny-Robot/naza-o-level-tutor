"""Pydantic models for structured lesson JSON responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LessonSection(BaseModel):
    heading: str = ""
    body: str = ""
    diagram_placeholder: str | None = None
    diagram_svg: str | None = None


class WorkedExample(BaseModel):
    problem: str = ""
    steps: list[str] = Field(default_factory=list)
    answer: str = ""


class CheckUnderstanding(BaseModel):
    question: str = ""
    expected_answer: str = ""
    hint: str = ""


class PracticeItem(BaseModel):
    question: str = ""
    options: list[str] | None = None
    correct_answer: str = ""
    explanation: str = ""


class RevisionCard(BaseModel):
    front: str = ""
    back: str = ""


class Citation(BaseModel):
    subject: str | None = None
    topic: str | None = None
    source: str | None = None
    chunk_id: str | None = None
    score: float | None = None


class LessonPayload(BaseModel):
    """Discriminated lesson response returned by POST /chat."""

    type: Literal["lesson"] = "lesson"
    title: str = "Lesson"
    introduction: str = ""
    objectives: list[str] = Field(default_factory=list)
    sections: list[LessonSection] = Field(default_factory=list)
    worked_example: WorkedExample = Field(default_factory=WorkedExample)
    check_understanding: CheckUnderstanding = Field(default_factory=CheckUnderstanding)
    practice: PracticeItem = Field(default_factory=PracticeItem)
    summary: list[str] = Field(default_factory=list)
    revision_card: RevisionCard = Field(default_factory=RevisionCard)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    # Pipeline metadata (kept for Tutor UI / sources pane)
    mode: Literal["lesson"] = "lesson"
    confidence: float = 0.0
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    refused: bool = False
    # Short plain-text teaser for chat history / follow-ups
    answer: str = ""


class LessonFeedback(BaseModel):
    """Teaching feedback for check-understanding / practice answers."""

    type: Literal["feedback"] = "feedback"
    correct: bool = False
    feedback: str = ""
    encouragement: str = ""


class LessonFeedbackRequest(BaseModel):
    question: str = Field(..., min_length=1)
    expected_answer: str = Field(..., min_length=1)
    student_answer: str = Field(..., min_length=1)
    explanation: str | None = None
    kind: Literal["check", "practice"] = "practice"
    title: str | None = None
