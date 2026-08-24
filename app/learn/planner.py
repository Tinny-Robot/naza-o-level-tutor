"""Outline-only course planner, next-action hook, and lecture suggestions."""

from __future__ import annotations

import json
import re
import secrets
from typing import Any

from app.config import MAX_CONTEXT_TOKENS, PROMPTS_DIR
from app.generation.context_builder import ContextBuilder
from app.i18n.language import language_instruction, resolve_language
from app.i18n.messages import ui_string
from app.learn.models import (
    CONFIDENCE_LEVELS,
    GOALS,
    SUBJECTS,
    STYLES,
    empty_outcome,
    lesson_progress,
    new_course,
    new_lesson,
)
from app.learn.store import CourseStore, get_course_store
from app.student.store import StudentStore, _utc_now, get_student_store
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SUBJECT_HINTS: dict[str, tuple[str, ...]] = {
    "mathematics": (
        "algebra",
        "quadratic",
        "equation",
        "geometry",
        "trigonometry",
        "calculus",
        "logarithm",
        "probability",
        "statistic",
        "fraction",
        "number",
        "matrix",
        "vector",
        "surd",
        "inequalit",
    ),
    "physics": (
        "electric",
        "current",
        "voltage",
        "ohm",
        "force",
        "motion",
        "wave",
        "light",
        "heat",
        "energy",
        "magnet",
        "pressure",
        "optics",
        "mechanic",
        "gravity",
        "radioactiv",
    ),
    "chemistry": (
        "atom",
        "mole",
        "acid",
        "base",
        "salt",
        "organic",
        "equilibrium",
        "bond",
        "periodic",
        "gas",
        "redox",
        "electrolys",
        "titration",
        "hydrocarbon",
        "compound",
    ),
    "english": (
        "essay",
        "comprehension",
        "lexis",
        "oral",
        "grammar",
        "summary",
        "letter",
        "concord",
        "stress",
        "vowel",
        "register",
        "clause",
    ),
}

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def infer_subject(topic: str, hint: str | None = None) -> str:
    if hint and hint.lower().strip() in SUBJECTS:
        return hint.lower().strip()
    blob = (topic or "").lower()
    scores = {
        subject: sum(1 for token in tokens if token in blob)
        for subject, tokens in _SUBJECT_HINTS.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "chemistry"


def _slug_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def _topic_score(mastery_topics: list[Any], subject: str, topic: str) -> float | None:
    needle = (topic or "").strip().lower()
    subject = (subject or "").lower()
    if not needle:
        return None
    for item in mastery_topics:
        if getattr(item, "subject", "") == subject and needle in str(
            getattr(item, "topic", "")
        ).lower():
            return float(getattr(item, "score", 0.0))
        if isinstance(item, dict):
            if str(item.get("subject") or "").lower() == subject and needle in str(
                item.get("topic") or ""
            ).lower():
                return float(item.get("score") or 0.0)
    return None


class _TokenCounter:
    """Adapter so ContextBuilder can pack chunks without a 400-char clip."""

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def count_tokens(self, text: str) -> int:
        fn = getattr(self._llm, "count_tokens", None)
        if callable(fn):
            try:
                return int(fn(text))
            except Exception:
                pass
        return max(1, len(text) // 4)


def _strip_learn_diagrams(payload: dict[str, Any]) -> dict[str, Any]:
    """Learn lessons never attach figures; Tutor teach() still does."""
    data = dict(payload)
    data["image_refs"] = []
    sections: list[Any] = []
    for item in data.get("sections") or []:
        if not isinstance(item, dict):
            sections.append(item)
            continue
        copy = dict(item)
        copy["diagram_placeholder"] = None
        copy["diagram_svg"] = None
        copy.pop("image_refs", None)
        sections.append(copy)
    data["sections"] = sections
    return data


def _ensure_assessment_last(lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not lessons:
        return lessons
    assessments = [item for item in lessons if item.get("kind") == "assessment"]
    body = [item for item in lessons if item.get("kind") != "assessment"]
    if assessments:
        return body + [assessments[-1]]
    body[-1]["kind"] = "assessment"
    return body


def fallback_outline(
    *,
    topic: str,
    subject: str,
    goal: str = "understand",
    confidence: str = "some",
    style: str = "worked_examples",
    mastery_topics: list[Any] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Deterministic 8-12 lesson path; skips a strong foundation lesson."""
    topic = (topic or "this topic").strip() or "this topic"
    subject = infer_subject(topic, subject)
    lang = resolve_language(language)
    kw = {"topic": topic}
    candidates = [
        {
            "title": ui_string("outline_what", lang, **kw),
            "kind": "concept",
            "rationale": ui_string("outline_r_foundation", lang),
            "foundation": True,
        },
        {
            "title": ui_string("outline_laws", lang, **kw),
            "kind": "concept",
            "rationale": ui_string("outline_r_laws", lang),
            "foundation": False,
        },
        {
            "title": ui_string("outline_method_a", lang, **kw),
            "kind": "concept",
            "rationale": ui_string("outline_r_method_a", lang),
            "foundation": False,
        },
        {
            "title": ui_string("outline_method_b", lang, **kw),
            "kind": "concept",
            "rationale": ui_string("outline_r_method_b", lang),
            "foundation": False,
        },
        {
            "title": ui_string("outline_calc", lang, **kw),
            "kind": "examples",
            "rationale": ui_string("outline_r_calc", lang),
            "foundation": False,
        },
        {
            "title": ui_string("outline_mistakes", lang, **kw),
            "kind": "concept",
            "rationale": ui_string("outline_r_mistakes", lang),
            "foundation": False,
        },
        {
            "title": ui_string("outline_technique", lang, **kw),
            "kind": "concept",
            "rationale": ui_string("outline_r_technique", lang),
            "foundation": False,
        },
        {
            "title": ui_string("outline_typical", lang, **kw),
            "kind": "examples",
            "rationale": ui_string("outline_r_typical", lang),
            "foundation": False,
        },
        {
            "title": ui_string("outline_exam", lang, **kw),
            "kind": "assessment",
            "rationale": ui_string("outline_r_exam", lang),
            "foundation": False,
        },
    ]
    score = _topic_score(mastery_topics or [], subject, topic)
    skip_foundation = confidence == "confident" or (score is not None and score >= 0.7)
    if confidence == "beginner" or goal == "basics":
        skip_foundation = False

    skipped: list[dict[str, str]] = []
    kept: list[dict[str, Any]] = []
    for item in candidates:
        if item["foundation"] and skip_foundation:
            skipped.append(
                {
                    "title": item["title"],
                    "skipped_because": (
                        ui_string("outline_skip_mastery", lang, score=score)
                        if score is not None
                        else ui_string("outline_skip_confident", lang)
                    ),
                }
            )
            continue
        kept.append(item)

    if goal == "exam" and kept and kept[-1]["kind"] != "assessment":
        kept.append(candidates[-1])

    # Always keep 8+ lessons (named subtopic slots, last one assessment).
    if len(kept) < 8:
        extras = [
            {
                "title": ui_string("outline_worked", lang, **kw),
                "kind": "examples",
                "rationale": ui_string("outline_r_worked", lang),
                "foundation": False,
            },
            {
                "title": ui_string("outline_recap", lang, **kw),
                "kind": "concept",
                "rationale": ui_string("outline_r_recap", lang),
                "foundation": False,
            },
        ]
        assessment = [item for item in kept if item["kind"] == "assessment"]
        body = [item for item in kept if item["kind"] != "assessment"]
        existing = {item["title"] for item in kept}
        for item in extras:
            if item["title"] in existing:
                continue
            body.append(item)
            existing.add(item["title"])
            if len(body) + len(assessment) >= 8:
                break
        if not assessment:
            assessment = [candidates[-1]]
        kept = body + assessment

    lessons = [
        new_lesson(
            lesson_id=_slug_id("l"),
            title=item["title"],
            kind=item["kind"],
            rationale=item["rationale"],
            status="pending",
        )
        for item in kept[:12]
    ]
    lessons = _ensure_assessment_last(lessons)
    style_note = {
        "worked_examples": ui_string("style_worked", lang),
        "examples_first": ui_string("style_examples", lang),
        "visual": ui_string("style_visual", lang),
        "exam": ui_string("style_exam", lang),
    }.get(style, ui_string("style_clear", lang))
    objective = (
        ui_string("outline_obj", lang, goal=goal, topic=topic, style_note=style_note)
        if goal != "exam"
        else ui_string("outline_obj_exam", lang, subject=subject, topic=topic)
    )
    return {
        "title": topic.title() if topic.islower() else topic,
        "subject": subject,
        "topic": topic,
        "objective": objective,
        "lessons": lessons,
        "skipped": skipped,
    }


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
    if fence:
        text = fence.group(1)
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _lessons_from_llm(raw_lessons: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw_lessons:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        kind = str(item.get("kind") or "concept").strip().lower()
        if kind not in {"concept", "examples", "assessment", "remedial"}:
            kind = "concept"
        out.append(
            new_lesson(
                lesson_id=_slug_id("l"),
                title=title,
                kind=kind,
                rationale=str(item.get("rationale") or ""),
                status="pending",
            )
        )
    return out


def plan_course(
    *,
    topic: str,
    goal: str = "understand",
    confidence: str = "some",
    style: str = "worked_examples",
    subject: str | None = None,
    exam: str | None = None,
    pipeline: Any | None = None,
    store: StudentStore | None = None,
    course_store: CourseStore | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Create and persist an outline. Uses LLM when a real pipeline is passed."""
    st = store or get_student_store()
    cs = course_store or get_course_store()
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("Topic is required")
    goal = goal if goal in GOALS else "understand"
    confidence = confidence if confidence in CONFIDENCE_LEVELS else "some"
    style = style if style in STYLES else "worked_examples"
    subject = infer_subject(topic, subject)
    exam_board = (exam or st.goals().target_exam or "WAEC").upper()
    mastery = st.mastery().topics
    lang = resolve_language(language, store=st)

    outline = fallback_outline(
        topic=topic,
        subject=subject,
        goal=goal,
        confidence=confidence,
        style=style,
        mastery_topics=mastery,
        language=lang,
    )

    teach = getattr(pipeline, "llm", None)
    retrieve = getattr(getattr(pipeline, "retrieval", None), "retrieve", None)
    if teach is not None and callable(retrieve) and callable(getattr(teach, "generate", None)):
        try:
            query = f"{subject} {topic} WAEC NECO JAMB"
            chunks = retrieve(query, top_k=8, subject=subject) or []
            weak = [
                t
                for t in mastery
                if t.subject == subject
            ][:6]
            profile_lines = [
                f"Goal: {goal}",
                f"Confidence: {confidence}",
                f"Style: {style}",
                "Mastery:",
                *[f"- {t.topic}={t.score:.2f}" for t in weak],
            ]
            scaffolding = (
                f"Topic: {topic}\nSubject: {subject}\n"
                + "\n".join(profile_lines)
                + "\n\nTextbook notes:\n"
            )
            prompt_path = PROMPTS_DIR / "course_planner.txt"
            try:
                system = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""
            except Exception:
                system = ""
            if not system:
                system = "Return JSON for an 8-12 lesson O-Level course outline."
            system = f"{system.rstrip()}\n\n{language_instruction(lang)}"
            counter = _TokenCounter(teach)
            builder = ContextBuilder(
                counter,
                max_context_tokens=MAX_CONTEXT_TOKENS,
            )
            reserved = counter.count_tokens(system) + counter.count_tokens(scaffolding)
            builder.reserved_tokens = min(reserved, max(0, MAX_CONTEXT_TOKENS // 4))
            packed, _selected = builder.build(list(chunks))
            user = scaffolding + (packed or "(none)")
            raw = teach.generate(system, user)
            parsed = _extract_json_object(raw)
            if parsed:
                llm_lessons = _lessons_from_llm(list(parsed.get("lessons") or []))
                if len(llm_lessons) >= 8:
                    llm_lessons = _ensure_assessment_last(llm_lessons)
                    if len(llm_lessons) > 12:
                        llm_lessons = llm_lessons[:11] + llm_lessons[-1:]
                    outline["title"] = str(parsed.get("title") or outline["title"])
                    outline["objective"] = str(parsed.get("objective") or outline["objective"])
                    if parsed.get("subject") in SUBJECTS:
                        outline["subject"] = parsed["subject"]
                    outline["lessons"] = llm_lessons
                    skipped = []
                    for item in parsed.get("skipped") or []:
                        if isinstance(item, dict) and item.get("title"):
                            skipped.append(
                                {
                                    "title": str(item["title"]),
                                    "skipped_because": str(item.get("skipped_because") or ""),
                                }
                            )
                    if skipped:
                        outline["skipped"] = skipped
        except Exception:
            logger.exception("Course planner LLM failed; using fallback outline")

    course = new_course(
        course_id=secrets.token_hex(8),
        title=str(outline["title"]),
        subject=str(outline["subject"]),
        topic=str(outline["topic"]),
        goal=goal,
        confidence=confidence,
        style=style,
        exam=exam_board,
        objective=str(outline["objective"]),
        status="in_progress",
        lessons=list(outline["lessons"]),
        skipped=list(outline.get("skipped") or []),
        created_at=_utc_now(),
        language=lang,
    )
    return cs.save(course)


def decide_next_action(
    course: dict[str, Any],
    outcome: dict[str, Any] | None,
    mastery: Any | None = None,
) -> dict[str, Any]:
    """Phase 1: failed check/practice or struggled -> practice; else continue.

    ``remediate`` is reserved for a later generator; this helper never returns it
    unless outcome explicitly requests it.
    """
    del mastery  # reserved for Phase 2
    lessons = list(course.get("lessons") or [])
    current_index = int(course.get("current_index") or 0)
    current = lessons[current_index] if 0 <= current_index < len(lessons) else None
    outcome = outcome or {}
    check = outcome.get("check_correct")
    practice = outcome.get("practice_correct")
    struggled = bool(outcome.get("struggled"))
    failed = check is False or practice is False or struggled
    next_id = ""
    for idx, item in enumerate(lessons):
        if idx > current_index and item.get("status") != "complete":
            next_id = str(item.get("id") or "")
            break
    if failed:
        return {
            "kind": "practice",
            "reason": "Let's strengthen this concept before moving on.",
            "lesson_id": str((current or {}).get("id") or ""),
        }
    if outcome.get("force_remediate"):
        return {
            "kind": "remediate",
            "reason": "Insert a remedial lesson before continuing.",
            "lesson_id": str((current or {}).get("id") or ""),
        }
    return {
        "kind": "continue",
        "reason": "Ready for the next lesson.",
        "lesson_id": next_id,
    }


def record_lesson_outcome(
    course: dict[str, Any],
    lesson_id: str,
    outcome: dict[str, Any],
    *,
    course_store: CourseStore | None = None,
    student_store: StudentStore | None = None,
) -> dict[str, Any]:
    cs = course_store or get_course_store()
    st = student_store or get_student_store()
    lessons = list(course.get("lessons") or [])
    found = None
    found_idx = -1
    for idx, item in enumerate(lessons):
        if item.get("id") == lesson_id:
            found = item
            found_idx = idx
            break
    if found is None:
        raise KeyError(lesson_id)

    payload = empty_outcome()
    payload["check_correct"] = outcome.get("check_correct")
    payload["practice_correct"] = outcome.get("practice_correct")
    payload["struggled"] = bool(outcome.get("struggled"))
    if payload["check_correct"] is False or payload["practice_correct"] is False:
        payload["struggled"] = True
    payload["completed_at"] = _utc_now()
    found["outcome"] = payload
    found["status"] = "complete"
    course["lessons"] = lessons
    course["current_index"] = found_idx
    course["next_action"] = decide_next_action(course, payload, st.mastery())

    if course["next_action"]["kind"] == "continue":
        nxt = course["next_action"].get("lesson_id")
        for idx, item in enumerate(lessons):
            if item.get("id") == nxt:
                course["current_index"] = idx
                break
        progress = lesson_progress(course)
        if progress["completed"] >= progress["total"] and progress["total"]:
            course["status"] = "completed"

    cs.save(course)

    try:
        from app.student.updater import LearningProfileUpdater

        LearningProfileUpdater(store=st).apply_event(
            {
                "kind": "lesson",
                "subject": course.get("subject") or "",
                "topic": found.get("title") or course.get("topic") or "",
                "label": found.get("title") or course.get("title"),
                "correct": not payload["struggled"],
            }
        )
    except Exception:
        logger.exception("Failed to update Learning Profile after course lesson")
    return course


def suggest_lectures(
    *,
    limit: int = 4,
    store: StudentStore | None = None,
    course_store: CourseStore | None = None,
) -> list[dict[str, Any]]:
    """Weak topics + misconceptions + in-progress courses, without duplicates."""
    st = store or get_student_store()
    cs = course_store or get_course_store()
    taken = cs.in_progress_topics()
    suggestions: list[dict[str, Any]] = []

    for course in cs.list_courses(status="in_progress")[:2]:
        progress = course.get("progress") or {}
        suggestions.append(
            {
                "kind": "resume",
                "subject": course.get("subject"),
                "topic": course.get("topic"),
                "title": course.get("title"),
                "reason": f"Continue lesson {(progress.get('current_index') or 0) + 1} of {progress.get('total') or '?'}",
                "course_id": course.get("id"),
            }
        )

    weak = sorted(st.mastery().topics, key=lambda t: t.score)
    for item in weak:
        key = (item.subject, item.topic.strip().lower())
        if key in taken:
            continue
        suggestions.append(
            {
                "kind": "weak_topic",
                "subject": item.subject,
                "topic": item.topic,
                "title": item.topic,
                "reason": f"Mastery {round(item.score * 100)}% - a focused lecture would help.",
                "course_id": None,
            }
        )
        taken.add(key)
        if len(suggestions) >= limit:
            return suggestions[:limit]

    for mis in st.misconceptions().items:
        key = (mis.subject, mis.topic.strip().lower())
        if not mis.topic or key in taken:
            continue
        suggestions.append(
            {
                "kind": "misconception",
                "subject": mis.subject,
                "topic": mis.topic,
                "title": mis.topic,
                "reason": f"Review {mis.confused}" if mis.confused else "A mix-up showed up here recently.",
                "course_id": None,
            }
        )
        taken.add(key)
        if len(suggestions) >= limit:
            break

    defaults = [
        ("chemistry", "Chemical Equilibrium"),
        ("physics", "Electricity"),
        ("mathematics", "Quadratic Equations"),
        ("english", "Lexis & Structure"),
    ]
    for subject, topic in defaults:
        key = (subject, topic.lower())
        if key in taken:
            continue
        suggestions.append(
            {
                "kind": "starter",
                "subject": subject,
                "topic": topic,
                "title": topic,
                "reason": "A strong O-Level starting lecture.",
                "course_id": None,
            }
        )
        taken.add(key)
        if len(suggestions) >= limit:
            break
    return suggestions[:limit]


def generate_lesson(
    course: dict[str, Any],
    lesson_id: str,
    *,
    pipeline: Any | None = None,
    course_store: CourseStore | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Fill a lesson payload (cached). Assessment lessons stay bank-backed."""
    from app.i18n.language import resolve_language
    from app.lesson.lesson_formatter import fallback_lesson

    cs = course_store or get_course_store()
    lang = resolve_language(language or course.get("language"))
    lesson = None
    for item in course.get("lessons") or []:
        if item.get("id") == lesson_id:
            lesson = item
            break
    if lesson is None:
        raise KeyError(lesson_id)
    if lesson.get("payload"):
        lesson["status"] = "ready" if lesson.get("status") == "pending" else lesson.get("status")
        return course
    if lesson.get("kind") == "assessment":
        lesson["status"] = "ready"
        cs.save(course)
        return course

    prior = [
        str(item.get("title"))
        for item in course.get("lessons") or []
        if item.get("id") != lesson_id
    ]
    question = (
        f"Teach this course lesson.\n"
        f"Course: {course.get('title')}\n"
        f"Subject: {course.get('subject')}\n"
        f"Objective: {course.get('objective')}\n"
        f"This lesson: {lesson.get('title')}\n"
        f"Why it is here: {lesson.get('rationale')}\n"
        f"Student goal: {course.get('goal')}\n"
        f"Confidence: {course.get('confidence')}\n"
        f"Preferred style: {course.get('style')}\n"
        f"Prior / other lessons: {', '.join(prior) or 'none'}\n"
        f"Skipped: {course.get('skipped_because') or []}\n"
        f"Teach only this lesson, not the whole course."
    )
    payload: dict[str, Any]
    generated = False
    if pipeline is not None:
        try:
            from app.generation.pipeline import GenerationPipeline
            from app.lesson.lesson_engine import LessonEngine

            if isinstance(pipeline, GenerationPipeline):
                rag_query = " ".join(
                    part
                    for part in (
                        str(course.get("topic") or "").strip(),
                        str(lesson.get("title") or "").strip(),
                        str(lesson.get("rationale") or "").strip(),
                    )
                    if part
                )
                payload = LessonEngine(pipeline).teach_course_lesson(
                    question,
                    subject=str(course.get("subject") or "") or None,
                    topic=str(course.get("topic") or "") or None,
                    query=rag_query or None,
                    update_profile=False,
                    language=lang,
                )
                generated = True
        except Exception:
            logger.exception("Lesson generate failed; using fallback")
            payload = fallback_lesson(
                topic=str(lesson.get("title") or course.get("topic") or "Lesson"),
                language=lang,
            ).model_dump()
            generated = True
    if not generated:
        payload = fallback_lesson(
            topic=str(lesson.get("title") or course.get("topic") or "Lesson"),
            language=lang,
        ).model_dump()

    lesson["payload"] = _strip_learn_diagrams(payload)
    if lesson.get("status") == "pending":
        lesson["status"] = "ready"
    cs.save(course)
    return course


def clear_course_payloads_for_language(
    course: dict[str, Any],
    language: str,
    *,
    course_store: CourseStore | None = None,
) -> dict[str, Any]:
    """Set course language, drop cached lesson text, keep titles and progress."""
    from app.i18n.language import normalize_language

    cs = course_store or get_course_store()
    course["language"] = normalize_language(language)
    for item in course.get("lessons") or []:
        item["payload"] = None
        if item.get("kind") == "assessment":
            continue
        if item.get("status") == "ready":
            item["status"] = "pending"
    return cs.save(course)
