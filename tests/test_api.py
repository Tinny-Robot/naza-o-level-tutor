"""API tests with a stubbed GenerationPipeline (no GGUF / embedder load)."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import MODEL_NAME
from backend.api.main import create_app


class StubPipeline:
    """Minimal stand-in for GenerationPipeline.ask / stream_ask / lesson grading."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.llm = _StubGradeLLM()

    def ask(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        self.calls.append({"question": question, "history": history or []})
        lowered = question.lower()
        if any(
            p in lowered
            for p in ("teach me", "lesson on", "help me understand", "learn about")
        ):
            return {
                "type": "lesson",
                "mode": "lesson",
                "title": "Equilibrium",
                "introduction": "Let's learn equilibrium.",
                "objectives": ["Define equilibrium"],
                "sections": [
                    {
                        "heading": "Idea",
                        "body": "Forces balance.",
                        "diagram_placeholder": None,
                    }
                ],
                "worked_example": {
                    "problem": "Two forces",
                    "steps": ["Draw"],
                    "answer": "Balanced",
                },
                "check_understanding": {
                    "question": "What is equilibrium?",
                    "expected_answer": "Balanced forces",
                    "hint": "Balance",
                },
                "practice": {
                    "question": "Net force in equilibrium?",
                    "options": ["A. Zero", "B. Large"],
                    "correct_answer": "A",
                    "explanation": "Net force is zero.",
                },
                "summary": ["Balance of forces"],
                "revision_card": {"front": "Equilibrium?", "back": "Net force = 0"},
                "citations": [
                    {
                        "subject": "physics",
                        "topic": "equilibrium",
                        "source": "data/raw/physics/notes.txt",
                        "chunk_id": "phy-1",
                        "score": 0.88,
                    }
                ],
                "confidence": 0.77,
                "retrieved_chunks": [],
                "refused": False,
                "answer": "Lesson ready: Equilibrium",
            }
        return {
            "type": "chat",
            "mode": "study",
            "answer": f"stub:{question}",
            "citations": [
                {
                    "subject": "physics",
                    "topic": "equilibrium",
                    "source": "data/raw/physics/notes.txt",
                    "chunk_id": "phy-1",
                    "score": 0.88,
                }
            ],
            "confidence": 0.77,
            "retrieved_chunks": [],
            "refused": False,
        }

    def stream_ask(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        **_: Any,
    ) -> Any:
        self.calls.append({"question": question, "history": history or []})
        if "fail_stream" in question:
            raise RuntimeError("Simulated stream engine crash")
        if "empty_stream" in question:
            return
        yield {
            "type": "meta",
            "mode": "study",
            "citations": [
                {
                    "subject": "physics",
                    "topic": "equilibrium",
                    "source": "data/raw/physics/notes.txt",
                    "chunk_id": "phy-1",
                    "score": 0.88,
                }
            ],
            "confidence": 0.77,
            "refused": False,
        }
        for token in ["Equi", "librium ", "is ", "balance."]:
            yield {"type": "token", "token": token}


class _StubGradeLLM:
    def generate(self, system: str, user: str) -> str:
        return (
            '{"correct": true, "feedback": "Yes - net force is zero at equilibrium.",'
            ' "encouragement": "Nice work - keep going!"}'
        )


@asynccontextmanager
async def _stub_lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pipeline = StubPipeline()
    yield


def _client() -> TestClient:
    return TestClient(create_app(lifespan_fn=_stub_lifespan))


def test_health_ok() -> None:
    with _client() as client:
        res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["offline"] is True
    assert body["model"] == MODEL_NAME


def test_chat_returns_pipeline_schema_and_latency() -> None:
    with _client() as client:
        res = client.post(
            "/chat",
            json={
                "message": "Explain equilibrium.",
                "history": [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello"},
                ],
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["type"] == "chat"
    assert body["mode"] == "study"
    assert body["answer"] == "stub:Explain equilibrium."
    assert body["refused"] is False
    assert isinstance(body["citations"], list)
    assert body["citations"][0]["chunk_id"] == "phy-1"
    assert body["confidence"] == 0.77
    assert "latency_ms" in body
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0


def test_chat_lesson_discriminated_response() -> None:
    with _client() as client:
        res = client.post(
            "/chat",
            json={"message": "Teach me equilibrium.", "history": []},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["type"] == "lesson"
    assert body["mode"] == "lesson"
    assert body["title"] == "Equilibrium"
    assert body["practice"]["correct_answer"] == "A"
    assert body["revision_card"]["front"]
    assert "latency_ms" in body


def test_chat_forwards_history_to_pipeline() -> None:
    app = create_app(lifespan_fn=_stub_lifespan)
    with TestClient(app) as client:
        res = client.post(
            "/chat",
            json={
                "message": "Explain simpler",
                "history": [{"role": "user", "content": "What is concord?"}],
            },
        )
        assert res.status_code == 200
        pipeline = app.state.pipeline
        assert isinstance(pipeline, StubPipeline)
        assert pipeline.calls[-1]["history"] == [
            {"role": "user", "content": "What is concord?"}
        ]


def test_lesson_feedback_endpoint() -> None:
    with _client() as client:
        res = client.post(
            "/lesson/feedback",
            json={
                "question": "Net force in equilibrium?",
                "expected_answer": "A",
                "student_answer": "A",
                "explanation": "Net force is zero.",
                "kind": "practice",
                "title": "Equilibrium",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["type"] == "feedback"
    assert body["correct"] is True
    assert body["feedback"]
    assert body["feedback"].strip().lower() not in {"correct.", "correct"}


def test_static_learning_routes() -> None:
    with _client() as client:
        for path in ("/lesson", "/quiz", "/progress", "/revision"):
            res = client.get(path)
            assert res.status_code == 200, path
            assert isinstance(res.json(), dict)


# ---------------------------------------------------------------------------
# Input validation tests (Pydantic field limits)
# ---------------------------------------------------------------------------

class TestChatInputValidation:
    """Verify that the chat endpoint enforces input length and history limits."""

    def test_message_too_long_returns_422(self) -> None:
        with _client() as client:
            res = client.post("/chat", json={"message": "x" * 4001, "history": []})
        assert res.status_code == 422

    def test_empty_message_returns_422(self) -> None:
        with _client() as client:
            res = client.post("/chat", json={"message": "", "history": []})
        assert res.status_code == 422

    def test_message_at_max_length_accepted(self) -> None:
        with _client() as client:
            res = client.post("/chat", json={"message": "a" * 4000, "history": []})
        assert res.status_code == 200

    def test_history_too_many_turns_returns_422(self) -> None:
        turn = {"role": "user", "content": "hi"}
        with _client() as client:
            res = client.post("/chat", json={"message": "hello", "history": [turn] * 21})
        assert res.status_code == 422

    def test_history_at_max_turns_accepted(self) -> None:
        turn = {"role": "user", "content": "hi"}
        with _client() as client:
            res = client.post("/chat", json={"message": "hello", "history": [turn] * 20})
        assert res.status_code == 200

    def test_history_content_too_long_returns_422(self) -> None:
        turn = {"role": "user", "content": "x" * 2001}
        with _client() as client:
            res = client.post("/chat", json={"message": "hello", "history": [turn]})
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# SSE Streaming endpoint tests
# ---------------------------------------------------------------------------

class TestChatStreaming:
    """Verify SSE streaming behavior on /chat/stream."""

    def test_stream_normal_response_and_done(self) -> None:
        with _client() as client:
            res = client.post(
                "/chat/stream",
                json={"message": "What is equilibrium?", "history": []},
            )
            assert res.status_code == 200
            assert "text/event-stream" in res.headers["content-type"]
            text = res.text
            assert "data: " in text
            assert "data: [DONE]" in text
            # Ensure metadata chunk is present
            assert '"type": "meta"' in text
            # Ensure tokens are present
            assert '"token": "Equi"' in text
            assert '"token": "balance."' in text

    def test_stream_failure_emits_error_and_no_done(self) -> None:
        with _client() as client:
            res = client.post(
                "/chat/stream",
                json={"message": "fail_stream query", "history": []},
            )
            assert res.status_code == 200
            text = res.text
            assert "data: " in text
            assert '"error":' in text
            # Should NOT emit [DONE] on failure
            assert "[DONE]" not in text

    def test_stream_empty_generation_emits_error(self) -> None:
        with _client() as client:
            res = client.post(
                "/chat/stream",
                json={"message": "empty_stream query", "history": []},
            )
            assert res.status_code == 200
            text = res.text
            assert '"error": "No response was generated."' in text
            assert "[DONE]" not in text

    def test_stream_input_validation(self) -> None:
        with _client() as client:
            res = client.post(
                "/chat/stream",
                json={"message": "x" * 4001, "history": []},
            )
            assert res.status_code == 422
