"""Unit tests for offline QueryRouter classification (no GGUF / network)."""

from __future__ import annotations

import pytest

from app.generation.router import QueryMode, QueryRouter, get_router, reset_router


@pytest.fixture
def router() -> QueryRouter:
    return QueryRouter()


@pytest.mark.parametrize(
    "question,expected",
    [
        ("hi", QueryMode.GENERAL),
        ("hello", QueryMode.GENERAL),
        ("good morning", QueryMode.GENERAL),
        ("WAEC physics past question on Ohm's law", QueryMode.STUDY),
        ("write a Python function", QueryMode.GENERAL),
        ("how do transformers work in ML?", QueryMode.GENERAL),
        ("how do I start a startup?", QueryMode.GENERAL),
        ("hey, solve this NECO quadratic", QueryMode.STUDY),
        ("what is love?", QueryMode.GENERAL),
        ("explain subject-verb concord", QueryMode.STUDY),
        ("Teach me equilibrium.", QueryMode.LESSON),
        ("lesson on refraction", QueryMode.LESSON),
        ("help me understand electrolysis", QueryMode.LESSON),
        ("explain the topic of quadratic equations", QueryMode.LESSON),
        ("I want to learn about Ohm's law", QueryMode.LESSON),
    ],
)
def test_classify_plan_cases(
    router: QueryRouter, question: str, expected: QueryMode
) -> None:
    assert router.classify(question) is expected


def test_mixed_greeting_with_waec_is_study(router: QueryRouter) -> None:
    assert router.classify("hi, explain WAEC refraction") is QueryMode.STUDY


def test_learn_intent_beats_study_keywords(router: QueryRouter) -> None:
    assert router.classify("teach me WAEC refraction") is QueryMode.LESSON


def test_empty_is_general(router: QueryRouter) -> None:
    assert router.classify("   ") is QueryMode.GENERAL


def test_get_router_singleton() -> None:
    reset_router()
    a = get_router()
    b = get_router()
    assert a is b
    reset_router()
