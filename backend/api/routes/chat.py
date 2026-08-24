"""POST /chat - offline GenerationPipeline ask endpoint (chat | lesson)."""

from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.generation.pipeline import GenerationPipeline
from app.student.store import get_student_store
from backend.api.deps import get_pipeline

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


@router.post("/chat")
def chat(
    body: ChatRequest,
    pipeline: GenerationPipeline = Depends(get_pipeline),
) -> dict[str, Any]:
    """Invoke the warm pipeline; returns ``type: chat`` or ``type: lesson``."""
    history = [{"role": m.role, "content": m.content} for m in body.history]
    started = time.perf_counter()
    language = get_student_store().preferences().language
    result = pipeline.ask(body.message, history=history, language=language)
    latency_ms = int((time.perf_counter() - started) * 1000)
    # Ensure discriminated type for older callers / stubs that omit it.
    if "type" not in result:
        result = {**result, "type": "chat"}
    return {**result, "latency_ms": latency_ms}
