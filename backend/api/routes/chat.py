"""POST /chat - offline GenerationPipeline ask endpoint (chat | lesson).
POST /chat/stream - SSE streaming variant for lower perceived latency.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.generation.pipeline import GenerationPipeline
from app.generation.pipeline import personalized_system
from app.student.store import get_student_store
from backend.api.deps import get_pipeline

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


@router.post("/chat")
async def chat(
    body: ChatRequest,
    pipeline: GenerationPipeline = Depends(get_pipeline),
) -> dict[str, Any]:
    """Invoke the warm pipeline; returns ``type: chat`` or ``type: lesson``.

    The route is async so FastAPI's event loop remains free while the local
    LLM generates on its dedicated single-worker executor thread.
    """
    history = [{"role": m.role, "content": m.content} for m in body.history]
    started = time.perf_counter()
    language = get_student_store().preferences().language
    result = await asyncio.to_thread(
        pipeline.ask, body.message, history=history, language=language
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    # Ensure discriminated type for older callers / stubs that omit it.
    if "type" not in result:
        result = {**result, "type": "chat"}
    return {**result, "latency_ms": latency_ms}


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    pipeline: GenerationPipeline = Depends(get_pipeline),
) -> StreamingResponse:
    """SSE streaming variant of POST /chat for chat-mode (non-lesson) queries.

    Streams metadata and tokens as Server-Sent Events::

        data: {"type": "meta", "mode": "study", "citations": [...], ...}
        data: {"type": "token", "token": "Pho"}
        data: {"type": "token", "token": "tosyn"}
        data: [DONE]

    If generation fails halfway through, emits::

        data: {"error": "Response generation failed"}

    and terminates without emitting [DONE], allowing the client to detect partial
    failure and display a retry button.
    """
    language = get_student_store().preferences().language
    history = [{"role": m.role, "content": m.content} for m in body.history]

    async def _sse_generator() -> AsyncGenerator[str, None]:
        token_count = 0
        refused = False
        try:
            for event in pipeline.stream_ask(
                body.message,
                history=history,
                language=language,
            ):
                event_type = event.get("type")
                if event_type == "meta" and event.get("refused"):
                    refused = True
                elif event_type == "token":
                    token_count += 1
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0)

            if token_count == 0 and not refused:
                yield f"data: {json.dumps({'error': 'No response was generated.'})}\n\n"
                return
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': f'Generation failed: {exc}'})}\n\n"
            return

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering when proxied
        },
    )
