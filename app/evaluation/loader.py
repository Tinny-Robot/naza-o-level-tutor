"""Load and validate the hand-curated retrieval evaluation dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import QA_PATH
from app.utils.logging import get_logger

logger = get_logger(__name__)

REQUIRED_FIELDS: frozenset[str] = frozenset(
    {"id", "question", "answer", "subject", "topic", "expected_keywords"}
)
OPTIONAL_IMAGE_FIELD = "images"
# Optional metadata from repaired / curated qa.json revisions
_OPTIONAL_BOOL_FIELDS = ("needs_review", "repaired")
_OPTIONAL_STR_FIELDS = ("review_reason",)


class QADatasetError(ValueError):
    """Raised when ``qa.json`` is missing, malformed, or schema-invalid."""


def _validate_item(item: Any, index: int) -> dict[str, Any]:
    """Validate a single Q&A record and return a normalized copy.

    Args:
        item: Raw JSON value (must be an object).
        index: Zero-based position in the array (for error messages).

    Returns:
        Normalized record with stripped strings and a keyword list.

    Raises:
        QADatasetError: If required fields are missing or mistyped.
    """
    prefix = f"qa.json[{index}]"
    if not isinstance(item, dict):
        raise QADatasetError(f"{prefix} must be an object, got {type(item).__name__}")

    missing = sorted(REQUIRED_FIELDS - set(item.keys()))
    if missing:
        raise QADatasetError(f"{prefix} missing required field(s): {', '.join(missing)}")

    record_id = item.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        raise QADatasetError(f"{prefix}.id must be a non-empty string")

    question = item.get("question")
    if not isinstance(question, str) or not question.strip():
        raise QADatasetError(f"{prefix}.question must be a non-empty string")

    answer = item.get("answer")
    if not isinstance(answer, str):
        raise QADatasetError(f"{prefix}.answer must be a string")

    subject = item.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise QADatasetError(f"{prefix}.subject must be a non-empty string")

    topic = item.get("topic")
    if not isinstance(topic, str):
        raise QADatasetError(f"{prefix}.topic must be a string")

    keywords_raw = item.get("expected_keywords")
    if not isinstance(keywords_raw, list) or not all(
        isinstance(k, str) for k in keywords_raw
    ):
        raise QADatasetError(f"{prefix}.expected_keywords must be a list of strings")

    record: dict[str, Any] = {
        "id": record_id.strip(),
        "question": question.strip(),
        "answer": answer.strip(),
        "subject": subject.strip().lower(),
        "topic": topic.strip(),
        "expected_keywords": [k.strip() for k in keywords_raw if k and str(k).strip()],
    }

    if OPTIONAL_IMAGE_FIELD in item:
        images = item.get(OPTIONAL_IMAGE_FIELD)
        if not isinstance(images, list) or not all(isinstance(i, str) for i in images):
            raise QADatasetError(f"{prefix}.images must be a list of strings when present")
        cleaned_images = [i.strip() for i in images if i and str(i).strip()]
        if cleaned_images:
            record["images"] = cleaned_images

    for field in _OPTIONAL_BOOL_FIELDS:
        if field in item:
            record[field] = bool(item.get(field))

    for field in _OPTIONAL_STR_FIELDS:
        if field in item and item.get(field) is not None:
            val = item.get(field)
            if not isinstance(val, str):
                raise QADatasetError(f"{prefix}.{field} must be a string when present")
            record[field] = val.strip()

    return record


def load_qa_dataset(path: Path | None = None) -> list[dict[str, Any]]:
    """Load and validate the evaluation Q&A JSON file.

    Expected schema (JSON array)::

        [
          {
            "id": "...",
            "question": "...",
            "answer": "...",
            "subject": "...",
            "topic": "...",
            "expected_keywords": ["..."],
            "images": ["optional/path.png"],
            "needs_review": false,
            "review_reason": "optional",
            "repaired": true
          }
        ]

    An empty list ``[]`` is valid (no items to evaluate).

    Args:
        path: Path to ``qa.json``. Defaults to :data:`app.config.QA_PATH`.

    Returns:
        List of validated Q&A dicts.

    Raises:
        QADatasetError: On missing file, invalid JSON, or schema violations.
    """
    qa_path = path if path is not None else QA_PATH
    if not qa_path.is_file():
        raise QADatasetError(
            f"Evaluation dataset not found at {qa_path}. "
            "Create data/eval/qa.json (see data/eval/qa.example.json)."
        )
    try:
        raw = json.loads(qa_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QADatasetError(f"Invalid JSON in {qa_path}: {exc}") from exc

    if not isinstance(raw, list):
        raise QADatasetError(f"{qa_path} must contain a JSON array")

    items = [_validate_item(item, i) for i, item in enumerate(raw)]
    logger.info("Loaded %d eval Q&A item(s) from %s", len(items), qa_path)
    return items
