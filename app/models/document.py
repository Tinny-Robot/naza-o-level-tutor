"""Data models shared across the ingestion and retrieval layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """A single logical unit of raw text loaded from ``data/raw/``.

    A document may be a whole text file or a single record from a
    JSON/JSONL/CSV file.
    """

    text: str
    source: str
    subject: str
    topic: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """A chunk of text ready for embedding and indexing."""

    id: str
    text: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk JSON representation."""
        return {"id": self.id, "text": self.text, "metadata": self.metadata}
