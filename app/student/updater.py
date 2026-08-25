"""Update student profile, mastery, and misconceptions based on learning events."""

from __future__ import annotations

from typing import Any

from app.student.models import MisconceptionItem, TopicMastery
from app.student.store import StudentStore, _utc_now, get_student_store
from app.utils.logging import get_logger

logger = get_logger(__name__)


class LearningProfileUpdater:
    """Processes learning events and updates the student state."""

    def __init__(self, store: StudentStore | None = None) -> None:
        self.store = store or get_student_store()

    def record_misconception(
        self, subject: str, topic: str, confused: str
    ) -> None:
        """Record a misconception or confusion for a topic."""
        misc_state = self.store.misconceptions()
        for item in misc_state.items:
            if (
                item.subject.lower() == subject.lower()
                and item.topic.lower() == topic.lower()
                and item.confused.lower() == confused.lower()
            ):
                item.count += 1
                item.timestamp = _utc_now()
                self.store.save_misconceptions(misc_state)
                return

        new_item = MisconceptionItem(
            subject=subject,
            topic=topic,
            confused=confused,
            timestamp=_utc_now(),
            count=1,
        )
        misc_state.items.append(new_item)
        self.store.save_misconceptions(misc_state)

    def apply_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Apply a learning event (practice answer, exam, quiz, lesson, chat)."""
        self.store.record_session(event)

        subject = str(event.get("subject") or "").strip()
        topic = str(event.get("topic") or "").strip()
        correct = event.get("correct")
        confused = event.get("confused")

        if confused and subject and topic:
            self.record_misconception(subject=subject, topic=topic, confused=str(confused))

        if subject and topic and correct is not None:
            mastery_state = self.store.mastery()
            target_entry: TopicMastery | None = None
            for t in mastery_state.topics:
                if t.subject.lower() == subject.lower() and t.topic.lower() == topic.lower():
                    target_entry = t
                    break

            if target_entry is None:
                initial_score = 0.85 if correct else 0.2
                target_entry = TopicMastery(
                    subject=subject,
                    topic=topic,
                    score=initial_score,
                    attempts=1,
                    last_attempt=_utc_now(),
                )
                mastery_state.topics.append(target_entry)
            else:
                target_entry.attempts += 1
                target_entry.last_attempt = _utc_now()
                current_score = target_entry.score
                if correct:
                    target_entry.score = min(1.0, current_score * 0.7 + 0.3)
                else:
                    target_entry.score = max(0.0, current_score * 0.7)

            self.store.save_mastery(mastery_state)

        return {"recorded": True}

