"""Data models for student profile, preferences, mastery, and misconceptions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Preferences:
    """Student UI and tutoring preferences."""

    language: str = "English"
    explanation_style: str = "balanced"
    show_citations: bool = True
    onboarded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "explanation_style": self.explanation_style,
            "show_citations": self.show_citations,
            "onboarded": self.onboarded,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Preferences:
        # If file existed on disk without 'onboarded', it defaults to True per test specs
        has_onboarded = "onboarded" in data
        onboarded = bool(data.get("onboarded", True if not has_onboarded else False))
        return cls(
            language=str(data.get("language") or "English"),
            explanation_style=str(data.get("explanation_style") or "balanced"),
            show_citations=bool(data.get("show_citations", True)),
            onboarded=onboarded,
        )


@dataclass
class Profile:
    """Student profile attributes."""

    display_name: str = "Student"
    grade_target: str = "A"
    exam_target: str = "WAEC"
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "grade_target": self.grade_target,
            "exam_target": self.exam_target,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        return cls(
            display_name=str(data.get("display_name") or "Student"),
            grade_target=str(data.get("grade_target") or "A"),
            exam_target=str(data.get("exam_target") or "WAEC"),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class Goals:
    """Daily and weekly study goals."""

    today: str = "Complete 1 lesson and 1 practice set"
    weekly: str = "Master 3 syllabus topics"
    target_exam: str = "WAEC"
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "today": self.today,
            "weekly": self.weekly,
            "target_exam": self.target_exam,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Goals:
        return cls(
            today=str(data.get("today") or "Complete 1 lesson and 1 practice set"),
            weekly=str(data.get("weekly") or "Master 3 syllabus topics"),
            target_exam=str(data.get("target_exam") or "WAEC"),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class TopicMastery:
    """Topic-level mastery record."""

    subject: str
    topic: str
    score: float = 0.0
    attempts: int = 0
    last_attempt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "topic": self.topic,
            "score": self.score,
            "attempts": self.attempts,
            "last_attempt": self.last_attempt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopicMastery:
        return cls(
            subject=str(data.get("subject") or ""),
            topic=str(data.get("topic") or ""),
            score=float(data.get("score", 0.0)),
            attempts=int(data.get("attempts", 0)),
            last_attempt=str(data.get("last_attempt") or ""),
        )


@dataclass
class MasteryState:
    """Collection of topic masteries."""

    topics: list[TopicMastery] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"topics": [t.to_dict() for t in self.topics]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MasteryState:
        raw_topics = data.get("topics") or []
        return cls(
            topics=[TopicMastery.from_dict(t) for t in raw_topics if isinstance(t, dict)]
        )


@dataclass
class MisconceptionItem:
    """Recorded student misconception or confusion."""

    subject: str
    topic: str
    confused: str
    timestamp: str = ""
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "topic": self.topic,
            "confused": self.confused,
            "timestamp": self.timestamp,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MisconceptionItem:
        return cls(
            subject=str(data.get("subject") or ""),
            topic=str(data.get("topic") or ""),
            confused=str(data.get("confused") or ""),
            timestamp=str(data.get("timestamp") or ""),
            count=int(data.get("count", 1)),
        )


@dataclass
class MisconceptionsState:
    """Recorded misconceptions."""

    items: list[MisconceptionItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"items": [i.to_dict() for i in self.items]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MisconceptionsState:
        raw_items = data.get("items") or []
        return cls(
            items=[
                MisconceptionItem.from_dict(i) for i in raw_items if isinstance(i, dict)
            ]
        )
