"""Text normalization and document cleaning."""

from __future__ import annotations

import re
import unicodedata

from app.models.document import Document


def clean_text(text: str) -> str:
    """Normalize unicode (NFC), collapse whitespace and excessive blank lines.
    
    Preserves Hausa characters and necessary single newlines.
    """
    if not text:
        return ""
    # NFC Unicode normalization
    normalized = unicodedata.normalize("NFC", text)
    
    # Strip leading and trailing whitespace
    stripped = normalized.strip()
    if not stripped:
        return ""
    
    # Split into lines
    lines = stripped.splitlines()
    cleaned_lines: list[str] = []
    for line in lines:
        cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned_line:
            cleaned_lines.append(cleaned_line)
            
    return "\n".join(cleaned_lines)


def clean_documents(docs: list[Document]) -> list[Document]:
    """Clean all documents and discard any that become empty."""
    cleaned_docs: list[Document] = []
    for doc in docs:
        cleaned_body = clean_text(doc.text)
        if cleaned_body:
            cleaned_docs.append(
                Document(
                    text=cleaned_body,
                    source=doc.source,
                    subject=doc.subject,
                    topic=doc.topic,
                    extra=doc.extra,
                )
            )
    return cleaned_docs

