"""Load raw documents from disk across supported file formats."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.models.document import Document
from app.utils.logging import get_logger

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".jsonl", ".csv"}


def _format_qa_record(record: dict[str, Any], file_stem: str) -> tuple[str, str, dict[str, Any]]:
    """Format a Q&A record into a readable document string and extract topic/extra."""
    parts: list[str] = []
    
    header_parts: list[str] = []
    if record.get("year"):
        header_parts.append(str(record["year"]))
    if record.get("exam_board"):
        header_parts.append(str(record["exam_board"]))
    if record.get("paper_type"):
        header_parts.append(str(record["paper_type"]))
    if header_parts:
        parts.append(" | ".join(header_parts))

    if record.get("passage"):
        parts.append(f"Passage: {record['passage']}")

    if record.get("question"):
        parts.append(f"Question: {record['question']}")

    options = record.get("options")
    if isinstance(options, list) and options:
        parts.append("\n".join(str(opt) for opt in options))
    elif isinstance(options, dict) and options:
        parts.append("\n".join(f"{k}. {v}" for k, v in options.items()))

    if record.get("answer"):
        parts.append(f"Answer: {record['answer']}")

    if record.get("explanation"):
        parts.append(f"Explanation: {record['explanation']}")

    if not parts:
        # Fallback to key-value pairs
        parts = [f"{k}: {v}" for k, v in record.items() if v]

    text = "\n".join(parts)
    topic = str(record.get("topic") or file_stem).strip()
    extra: dict[str, Any] = {}
    for key in ("year", "exam_board", "paper_type", "images", "caption", "needs_review"):
        if key in record:
            extra[key] = record[key]

    return text, topic, extra


def load_raw_documents(raw_dir: Path | str) -> list[Document]:
    """Load text and structured files under raw_dir into Document objects.
    
    Subject is derived from the parent directory name (e.g. data/raw/physics -> physics).
    Topic is derived from the file stem or structured record metadata.
    """
    base_dir = Path(raw_dir)
    if not base_dir.is_dir():
        logger.warning("Raw directory %s does not exist", base_dir)
        return []

    documents: list[Document] = []

    for path in sorted(base_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        subject = path.parent.name
        rel_source = str(path)
        stem = path.stem

        try:
            suffix = path.suffix.lower()
            if suffix in (".txt", ".md"):
                text = path.read_text(encoding="utf-8")
                if text.strip():
                    documents.append(
                        Document(
                            text=text,
                            source=rel_source,
                            subject=subject,
                            topic=stem,
                        )
                    )

            elif suffix == ".json":
                try:
                    content = path.read_text(encoding="utf-8")
                    data = json.loads(content)
                except Exception as exc:
                    logger.warning("Failed to parse JSON file %s: %s", path, exc)
                    continue

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            rec_text, rec_topic, rec_extra = _format_qa_record(item, stem)
                            rec_subj = str(item.get("subject") or subject)
                            if rec_text.strip():
                                documents.append(
                                    Document(
                                        text=rec_text,
                                        source=rel_source,
                                        subject=rec_subj,
                                        topic=rec_topic,
                                        extra=rec_extra,
                                    )
                                )
                elif isinstance(data, dict):
                    rec_text, rec_topic, rec_extra = _format_qa_record(data, stem)
                    rec_subj = str(data.get("subject") or subject)
                    if rec_text.strip():
                        documents.append(
                            Document(
                                text=rec_text,
                                source=rel_source,
                                subject=rec_subj,
                                topic=rec_topic,
                                extra=rec_extra,
                            )
                        )

            elif suffix == ".jsonl":
                with path.open("r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            item = json.loads(line_str)
                        except json.JSONDecodeError:
                            logger.warning(
                                "Malformed JSON line %d in %s", line_num, path
                            )
                            continue
                        if isinstance(item, dict):
                            rec_text, rec_topic, rec_extra = _format_qa_record(item, stem)
                            rec_subj = str(item.get("subject") or subject)
                            if rec_text.strip():
                                documents.append(
                                    Document(
                                        text=rec_text,
                                        source=rel_source,
                                        subject=rec_subj,
                                        topic=rec_topic,
                                        extra=rec_extra,
                                    )
                                )

            elif suffix == ".csv":
                with path.open("r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        topic = row.get("topic") or stem
                        rec_subj = row.get("subject") or subject
                        lines = [f"{k}: {v}" for k, v in row.items() if v]
                        text = "\n".join(lines)
                        if text.strip():
                            documents.append(
                                Document(
                                    text=text,
                                    source=rel_source,
                                    subject=rec_subj,
                                    topic=topic,
                                )
                            )

        except Exception as exc:
            logger.warning("Error reading file %s: %s", path, exc)
            continue

    return documents

