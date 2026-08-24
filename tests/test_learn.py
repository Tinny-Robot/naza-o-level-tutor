"""Learn hub: planner fallback, course store statuses, next action, API."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.generation.pipeline import GenerationPipeline
from app.generation.prompt_manager import PromptManager
from app.generation.rag import RetrievalService
from app.generation.router import QueryMode
from app.learn.models import COURSE_STATUSES, new_course, new_lesson
from app.learn.planner import (
    decide_next_action,
    fallback_outline,
    generate_lesson,
    suggest_lectures,
)
from app.learn.store import CourseStore
from app.lesson.lesson_engine import LessonEngine
from app.student.models import MasteryState, Preferences, TopicMastery
from app.student.store import StudentStore, reset_student_store
from backend.api.main import create_app

_COURSE_SECTION_HEADINGS = (
    "Meaning of equilibrium",
    "Conditions for equilibrium",
    "Resolved forces",
    "Moments and turning effects",
    "Exam traps in equilibrium",
)


class _FixedRouter:
    def __init__(self, mode: QueryMode) -> None:
        self.mode = mode

    def classify(self, question: str) -> QueryMode:
        return self.mode


class _StubRetriever:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self._results = results if results is not None else [
            {
                "score": 0.9,
                "text": (
                    "Equilibrium is a state of balance of forces. "
                    "A body is in equilibrium when the net force and the net moment are zero."
                ),
                "metadata": {
                    "id": "eq-1",
                    "subject": "physics",
                    "topic": "equilibrium",
                    "source": "notes",
                    "images": ["figures/equilibrium.png"],
                    "caption": "Textbook force diagram",
                },
            }
        ]

    def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[dict[str, Any]]:
        return self._results[:top_k]


class _CourseLessonStubLLM:
    """Branching stub: frame vs Pass B vs worked-example enrich.

    generate(system, user) has no max_tokens so LessonEngine drops it on TypeError.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if "=== Section heading ===" in user:
            heading = _heading_from_section_prompt(user)
            return json.dumps({"heading": heading, "body": _long_section_body(heading)})
        if "=== Worked example ===" in user:
            return json.dumps(
                {
                    "problem": "A 5 N force and a 5 N force act opposite on a ring.",
                    "steps": [
                        "Draw the two forces along one line.",
                        "Assign signs: right positive, left negative.",
                        "Write net force as 5 N + (-5 N).",
                        "Simplify to 0 N.",
                        "Check moments about the centre: both lines of action pass through it.",
                        "Conclude the ring is in equilibrium.",
                    ],
                    "answer": "The ring is in equilibrium because net force and net moment are zero.",
                }
            )
        return json.dumps(
            {
                "type": "lesson",
                "title": "Equilibrium",
                "introduction": "Let's learn equilibrium for WAEC and NECO.",
                "objectives": [
                    "Define equilibrium",
                    "State the two conditions",
                    "Resolve forces in a worked example",
                ],
                "sections": [
                    {
                        "heading": heading,
                        "body": "",
                        "diagram_placeholder": "Force diagram",
                        "diagram_svg": "<svg viewBox='0 0 10 10'></svg>",
                    }
                    for heading in _COURSE_SECTION_HEADINGS
                ],
                "worked_example": {
                    "problem": "Two equal forces act opposite.",
                    "steps": ["Draw forces", "Net force is zero"],
                    "answer": "In equilibrium",
                },
                "check_understanding": {
                    "question": "What is equilibrium?",
                    "expected_answer": "A state of balanced forces",
                    "hint": "Think balance",
                },
                "practice": {
                    "question": "When is a body in equilibrium?",
                    "options": ["A. Net force zero", "B. Always moving", "C. Hot", "D. Soft"],
                    "correct_answer": "A",
                    "explanation": "Net force (and often net moment) is zero.",
                },
                "summary": ["Balance of forces", "Check moments too"],
                "revision_card": {"front": "Equilibrium?", "back": "Net force = 0"},
                "citations": [],
                "image_refs": [{"path": "/tmp/fake.png", "caption": "should be stripped"}],
            }
        )


def _heading_from_section_prompt(user: str) -> str:
    marker = "=== Section heading ==="
    start = user.find(marker)
    if start < 0:
        return "Section"
    rest = user[start + len(marker) :].strip()
    return rest.splitlines()[0].strip() or "Section"


def _long_section_body(heading: str) -> str:
    return (
        f"{heading} is the exam-language idea you must state before any calculation. "
        "Write it as a full definition, not a slogan, so it can earn the first mark.\n\n"
        f"WAEC, NECO, and JAMB set {heading.lower()} because it links a syllabus term "
        "to a method mark. A vague everyday sentence will not score.\n\n"
        "The rule from the passages is that opposing effects cancel: net force is zero "
        "and, when a body can turn, clockwise moments equal anticlockwise moments "
        "[Chunk eq-1].\n\n"
        "Concrete example: two 5 N forces pull a ring in opposite directions along a "
        "straight line. Net force = 5 N - 5 N = 0 N, so the ring stays at rest if it "
        f"started at rest. That is how {heading.lower()} shows up in numbers.\n\n"
        "A common examiner trap is to treat 'balanced' as 'equal size only' and forget "
        "opposite direction, or to ignore the moment condition when the body can rotate."
    )


def _course_pipeline(llm: _CourseLessonStubLLM) -> GenerationPipeline:
    return GenerationPipeline(
        retrieval=RetrievalService(retriever=_StubRetriever()),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        prompts=PromptManager(),
        router=_FixedRouter(QueryMode.LESSON),  # type: ignore[arg-type]
    )


def _assert_no_course_diagrams(payload: dict[str, Any]) -> None:
    assert payload.get("image_refs") in (None, [])
    for section in payload.get("sections") or []:
        assert not section.get("image_refs")
        assert not section.get("diagram_svg")
        assert not section.get("diagram_placeholder")


def test_fallback_outline_has_eight_lessons_and_skips_high_mastery() -> None:
    outline = fallback_outline(
        topic="Quadratic Equations",
        subject="mathematics",
        goal="exam",
        confidence="some",
        mastery_topics=[
            {
                "subject": "mathematics",
                "topic": "Quadratic Equations",
                "score": 0.85,
            }
        ],
    )
    lessons = outline["lessons"]
    assert len(lessons) >= 8
    titles = [item["title"].lower() for item in lessons]
    assert not any(title.startswith("what is") for title in titles)
    assert outline["skipped"]
    assert any(item["kind"] == "assessment" for item in lessons)
    assert lessons[-1]["kind"] == "assessment"


def test_fallback_outline_keeps_foundation_for_beginner() -> None:
    outline = fallback_outline(
        topic="Quadratic Equations",
        subject="mathematics",
        confidence="beginner",
        language="English",
        mastery_topics=[
            {
                "subject": "mathematics",
                "topic": "Quadratic Equations",
                "score": 0.9,
            }
        ],
    )
    titles = [item["title"].lower() for item in outline["lessons"]]
    assert any(title.startswith("what is") for title in titles)
    assert len(outline["lessons"]) >= 8
    assert outline["lessons"][-1]["kind"] == "assessment"


def test_course_store_statuses_round_trip(tmp_path: Path) -> None:
    store = CourseStore(tmp_path)
    for status in COURSE_STATUSES:
        store.save(
            new_course(
                course_id=status,
                title=status.replace("_", " ").title(),
                subject="chemistry",
                topic="Acids",
                status=status,
                lessons=[
                    new_lesson(lesson_id="l1", title="Intro", kind="concept"),
                ],
            )
        )
    listed = store.list_courses()
    ids = {item["id"] for item in listed}
    assert "archived" not in ids
    assert {"draft", "in_progress", "completed"} <= ids
    archived = store.list_courses(status="archived")
    assert len(archived) == 1
    assert archived[0]["status"] == "archived"
    loaded = store.get("in_progress")
    assert loaded is not None
    assert loaded["status"] == "in_progress"
    assert loaded["lessons"][0]["title"] == "Intro"


def test_course_language_missing_backfills_english(tmp_path: Path) -> None:
    store = CourseStore(tmp_path)
    course = new_course(
        course_id="old",
        title="Acids",
        subject="chemistry",
        topic="Acids",
        lessons=[new_lesson(lesson_id="l1", title="Intro", kind="concept")],
    )
    course.pop("language", None)
    path = store.root / "old.json"
    path.write_text(json.dumps(course), encoding="utf-8")
    loaded = store.get("old")
    assert loaded is not None
    assert loaded["language"] == "English"
    listed = store.list_courses()
    assert listed[0]["language"] == "English"


def test_regenerate_clears_payloads_and_sets_prefs_language(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr("app.learn.store.STUDENT_DIR", tmp_path)
    monkeypatch.setattr("app.student.store.STUDENT_DIR", tmp_path)
    monkeypatch.setattr("app.config.STUDENT_DIR", tmp_path)
    reset_student_store()
    try:
        StudentStore(tmp_path).save_preferences(
            Preferences(language="Hausa", onboarded=True)
        )
        store = CourseStore(tmp_path)
        course = new_course(
            course_id="acids",
            title="Acids",
            subject="chemistry",
            topic="Acids",
            language="English",
            lessons=[
                new_lesson(lesson_id="l1", title="Intro", kind="concept", status="ready"),
            ],
        )
        course["lessons"][0]["payload"] = {"type": "lesson", "title": "Intro"}
        store.save(course)
        with _client() as client:
            res = client.post("/learn/courses/acids/regenerate")
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["language"] == "Hausa"
            assert body["lessons"][0]["title"] == "Intro"
            assert body["lessons"][0].get("has_payload") is False
        loaded = store.get("acids")
        assert loaded is not None
        assert loaded["language"] == "Hausa"
        assert loaded["lessons"][0]["payload"] is None
        assert loaded["lessons"][0]["status"] == "pending"
    finally:
        reset_student_store()


def test_decide_next_action_failed_check_then_continue() -> None:
    course = {
        "current_index": 0,
        "lessons": [
            {"id": "l1", "status": "complete"},
            {"id": "l2", "status": "pending"},
        ],
    }
    failed = decide_next_action(course, {"check_correct": False})
    assert failed["kind"] == "practice"
    assert failed["lesson_id"] == "l1"
    passed = decide_next_action(
        course,
        {"check_correct": True, "practice_correct": True},
    )
    assert passed["kind"] == "continue"
    assert passed["lesson_id"] == "l2"
    struggled = decide_next_action(course, {"struggled": True})
    assert struggled["kind"] == "practice"


def test_suggestions_prefer_weak_topics_without_duplicating_in_progress(
    tmp_path: Path,
) -> None:
    root = tmp_path / "student"
    student = StudentStore(root)
    courses = CourseStore(root)
    student.save_mastery(
        MasteryState(
            topics=[
                TopicMastery(
                    subject="physics", topic="Electricity", score=0.2, attempts=4
                ),
                TopicMastery(
                    subject="chemistry",
                    topic="Chemical Equilibrium",
                    score=0.18,
                    attempts=5,
                ),
            ]
        )
    )
    courses.save(
        new_course(
            course_id="elec1",
            title="Electricity",
            subject="physics",
            topic="Electricity",
            status="in_progress",
            lessons=[new_lesson(lesson_id="l1", title="Current")],
        )
    )
    suggestions = suggest_lectures(limit=4, store=student, course_store=courses)
    assert suggestions
    assert any(item["kind"] == "resume" and item["course_id"] == "elec1" for item in suggestions)
    weak_topics = [
        item["topic"].lower()
        for item in suggestions
        if item["kind"] == "weak_topic"
    ]
    assert "electricity" not in weak_topics
    assert any("equilibrium" in topic for topic in weak_topics)


@asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pipeline = object()
    yield


def _client() -> TestClient:
    return TestClient(create_app(lifespan_fn=_noop_lifespan))


def test_learn_plan_and_list_api(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("app.learn.store.STUDENT_DIR", tmp_path)
    with _client() as client:
        created = client.post(
            "/learn/plan",
            json={
                "topic": "Quadratic Equations",
                "subject": "mathematics",
                "goal": "exam",
                "confidence": "some",
            },
        )
        assert created.status_code == 200, created.text
        course = created.json()
        assert course["status"] == "in_progress"
        assert len(course["lessons"]) >= 8
        assert course["lessons"][-1]["kind"] == "assessment"
        assert course["topic"] == "Quadratic Equations"

        listed = client.get("/learn/courses")
        assert listed.status_code == 200
        ids = [item["id"] for item in listed.json()["courses"]]
        assert course["id"] in ids

        lesson_id = course["lessons"][0]["id"]
        generated = client.post(
            f"/learn/courses/{course['id']}/lessons/{lesson_id}/generate"
        )
        assert generated.status_code == 200, generated.text
        payload = generated.json()["lessons"][0].get("payload")
        assert payload is None or payload.get("title") or payload.get("type")

        failed = client.post(
            f"/learn/courses/{course['id']}/lessons/{lesson_id}/complete",
            json={"check_correct": False, "struggled": True},
        )
        assert failed.status_code == 200, failed.text
        assert failed.json()["next_action"]["kind"] == "practice"

        suggestions = client.get("/learn/suggestions")
        assert suggestions.status_code == 200
        assert suggestions.json()["suggestions"]

        archived = client.post(
            f"/learn/courses/{course['id']}/progress",
            json={"status": "archived"},
        )
        assert archived.status_code == 200
        hidden = client.get("/learn/courses")
        assert course["id"] not in [item["id"] for item in hidden.json()["courses"]]
        shown = client.get("/learn/courses?status=archived")
        assert course["id"] in [item["id"] for item in shown.json()["courses"]]


def test_generate_lesson_attaches_no_diagrams(tmp_path: Path) -> None:
    store = CourseStore(tmp_path)
    outline = fallback_outline(
        topic="Equilibrium",
        subject="physics",
        goal="exam",
        confidence="beginner",
    )
    lesson = next(item for item in outline["lessons"] if item["kind"] != "assessment")
    course = new_course(
        course_id="eq-course",
        title=outline["title"],
        subject="physics",
        topic="Equilibrium",
        lessons=outline["lessons"],
    )
    store.save(course)
    llm = _CourseLessonStubLLM()
    updated = generate_lesson(
        course,
        lesson["id"],
        pipeline=_course_pipeline(llm),
        course_store=store,
    )
    payload = next(
        item["payload"] for item in updated["lessons"] if item["id"] == lesson["id"]
    )
    assert payload
    _assert_no_course_diagrams(payload)


def test_teach_course_lesson_attaches_no_diagrams() -> None:
    llm = _CourseLessonStubLLM()
    result = LessonEngine(_course_pipeline(llm)).teach_course_lesson(
        "Teach this course lesson on equilibrium.",
        subject="physics",
        topic="Equilibrium",
        query="Equilibrium Meaning of equilibrium Foundation terms",
        update_profile=False,
    )
    _assert_no_course_diagrams(result)
    assert not any(
        (section.get("diagram_svg") or "").strip()
        for section in result.get("sections") or []
    )


def test_teach_course_lesson_pass_b_fills_distinct_long_bodies() -> None:
    llm = _CourseLessonStubLLM()
    result = LessonEngine(_course_pipeline(llm)).teach_course_lesson(
        "Teach this course lesson on equilibrium.",
        subject="physics",
        topic="Equilibrium",
        query="Equilibrium Meaning of equilibrium Foundation terms",
        update_profile=False,
    )
    sections = result["sections"]
    assert len(sections) >= 3
    bodies = [str(item.get("body") or "") for item in sections]
    assert all(len(body) >= 280 for body in bodies)
    assert len(set(bodies)) == len(bodies)
    headings = [str(item.get("heading") or "") for item in sections]
    for heading, body in zip(headings, bodies):
        assert heading
        assert heading.lower() in body.lower()
    section_calls = [user for _system, user in llm.calls if "=== Section heading ===" in user]
    assert len(section_calls) >= 3
    frame_calls = [user for _system, user in llm.calls if "=== Section heading ===" not in user]
    assert frame_calls
    assert any("=== Student request ===" in user for user in frame_calls)

