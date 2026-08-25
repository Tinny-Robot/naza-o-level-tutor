"""Orchestrate structured lessons via GenerationPipeline primitives (no FAISS copy)."""

from __future__ import annotations

import re
from typing import Any

from app.config import MAX_CONTEXT_TOKENS, TOP_K
from app.generation.citations import build_citations
from app.generation.context_builder import ContextBuilder
from app.generation.hallucination import should_refuse
from app.generation.pipeline import (
    GenerationPipeline,
    _question_with_history,
    _scores_from_results,
    blend_confidence,
    collect_image_refs,
    format_history,
    personalized_system,
)
from app.lesson.lesson_formatter import (
    answers_match,
    extract_json_object,
    fallback_lesson,
    format_feedback,
    format_lesson,
    sanitize_section_body,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

COURSE_LESSON_TOP_K = 8
COURSE_FRAME_MAX_TOKENS = 768
COURSE_SECTION_MAX_TOKENS = 640
COURSE_ENRICH_MAX_TOKENS = 512

_COURSE_LESSON_SYSTEM = (
    "You are Naza, a friendly eagle who tutors Nigerian O-Level students "
    "(WAEC / NECO / JAMB). Return ONLY valid JSON. Ground the lesson in the "
    "provided textbook passages. Never use em dashes or en dashes. Use a "
    "normal hyphen. Do not describe or request diagrams. Set "
    "diagram_placeholder to null. If a passage mentions a figure, describe "
    "it in prose in the relevant section body. Never write "
    "'refer to the diagram below'."
)

_ENRICH_SYSTEM = (
    "You are Naza, a friendly eagle who tutors Nigerian O-Level students. "
    "Return ONLY valid JSON. Never use em dashes or en dashes. Use a normal hyphen."
)

_TOPIC_STRIP_RE = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"teach\s+me(?:\s+about)?|"
    r"help\s+me\s+(?:to\s+)?(?:learn|understand)|"
    r"i\s+want\s+to\s+learn(?:\s+about)?|"
    r"learn(?:\s+about)?|"
    r"lesson\s+on|"
    r"explain\s+the\s+topic(?:\s+of)?|"
    r"give\s+me\s+a\s+lesson\s+on|"
    r"walk\s+me\s+through"
    r")\s+",
    re.IGNORECASE,
)


def extract_topic(question: str) -> str:
    """Pull a short topic label from a lesson-intent utterance."""
    cleaned = question.strip().rstrip(".!?")
    topic = _TOPIC_STRIP_RE.sub("", cleaned).strip(" :,-")
    if not topic:
        return cleaned or "this topic"
    # Drop leading "about "
    topic = re.sub(r"^(?:about|on)\s+", "", topic, flags=re.IGNORECASE).strip()
    return topic or cleaned or "this topic"


def _llm_generate(llm: Any, system: str, user: str, *, max_tokens: int | None = None) -> str:
    """Call llm.generate, passing max_tokens when the client supports it."""
    generate = llm.generate
    if max_tokens is None:
        return generate(system, user)
    try:
        return generate(system, user, max_tokens=max_tokens)
    except TypeError:
        return generate(system, user)


def _strip_course_diagrams(data: dict[str, Any]) -> dict[str, Any]:
    data["image_refs"] = []
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section["diagram_placeholder"] = None
        section["diagram_svg"] = None
        section.pop("image_refs", None)
    return data


def _normalize_frame_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Turn pass-A heading lists into section objects with empty bodies."""
    headings = data.get("section_headings") or data.get("headings")
    sections = data.get("sections")
    normalized: list[dict[str, Any]] = []
    if isinstance(headings, list) and headings:
        source = headings
    elif isinstance(sections, list):
        source = sections
    else:
        source = []
    for item in source:
        if isinstance(item, str) and item.strip():
            normalized.append(
                {"heading": item.strip(), "body": "", "diagram_placeholder": None}
            )
        elif isinstance(item, dict):
            heading = str(item.get("heading") or item.get("title") or "").strip()
            if not heading:
                continue
            normalized.append(
                {
                    "heading": heading,
                    "body": str(item.get("body") or item.get("content") or ""),
                    "diagram_placeholder": None,
                }
            )
    if normalized:
        data = dict(data)
        data["sections"] = normalized[:7]
    return data


def _body_from_section_output(raw: str, heading: str) -> str:
    return sanitize_section_body(raw or "", heading=heading)


_FEEDBACK_SYSTEM = (
    "You are a warm Nigerian secondary-school teacher giving feedback. "
    "Always teach - never reply with only 'Correct.' or 'Wrong.'. "
    "Be brief (2-4 sentences), encouraging, and specific. "
    "If the student is wrong, name the likely confusion (e.g. Diffusion vs Osmosis). "
    "Return ONLY JSON: "
    '{"correct": true|false, "feedback": "...", "encouragement": "...", '
    '"confused": "ConceptA ↔ ConceptB" or null}'
)


class LessonEngine:
    """Build structured lessons using a warm GenerationPipeline's retrieval + LLM."""

    def __init__(self, pipeline: GenerationPipeline) -> None:
        self._pipeline = pipeline

    @property
    def pipeline(self) -> GenerationPipeline:
        return self._pipeline

    def teach(
        self,
        question: str,
        *,
        top_k: int = TOP_K,
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        history: list[dict[str, str]] | None = None,
        update_profile: bool = True,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve context, prompt the local LLM for lesson JSON, normalize."""
        from app.i18n.language import resolve_language
        from app.i18n.messages import ui_string

        lang = resolve_language(language)
        cleaned = question.strip()
        topic_label = topic or extract_topic(cleaned)
        if not cleaned:
            lesson = fallback_lesson(
                topic="Lesson",
                reason=ui_string("fallback_empty_topic", lang),
                refused=True,
                language=lang,
            )
            return lesson.model_dump()

        history_block = format_history(history)
        prompt_question = _question_with_history(cleaned, history_block)

        retrieved = self._pipeline.retrieval.retrieve(
            cleaned,
            top_k=top_k,
            subject=subject,
            topic=topic,
            source=source,
        )
        scores = _scores_from_results(retrieved)
        confidence = blend_confidence(scores)
        refused = should_refuse(retrieved)

        builder = ContextBuilder(
            self._pipeline.llm,
            max_context_tokens=MAX_CONTEXT_TOKENS,
        )
        system = personalized_system(self._pipeline.prompts.lesson_system_prompt, lang)
        scaffolding = self._pipeline.prompts.render_lesson_user(
            context="",
            question=prompt_question,
        )
        reserved = self._pipeline.llm.count_tokens(system) + self._pipeline.llm.count_tokens(
            scaffolding
        )
        builder.reserved_tokens = min(reserved, max(0, MAX_CONTEXT_TOKENS // 4))

        if refused:
            context, selected = "", []
            citations: list[dict[str, Any]] = []
            # Still teach with a careful fallback-capable prompt (empty context).
            logger.info("Lesson retrieval weak; generating with empty context")
        else:
            context, selected = builder.build(retrieved)
            citations = build_citations(selected)

        user = self._pipeline.prompts.render_lesson_user(
            context=context or "(No strong textbook passages retrieved - teach carefully.)",
            question=prompt_question,
        )

        try:
            raw = self._pipeline.llm.generate(system, user)
        except Exception:
            logger.exception("Lesson LLM generate failed; using fallback lesson")
            lesson = fallback_lesson(
                topic=topic_label,
                citations=citations,
                confidence=confidence,
                refused=refused,
                language=lang,
            )
            lesson.retrieved_chunks = selected
            data = lesson.model_dump()
            data["image_refs"] = collect_image_refs(selected)
            return data

        lesson = format_lesson(
            raw,
            topic=topic_label,
            citations=citations,
            confidence=confidence,
            retrieved_chunks=selected,
            refused=refused,
        )
        data = lesson.model_dump()
        image_refs = collect_image_refs(selected)
        data["image_refs"] = image_refs
        # Prefer real figures on the first concept section when available.
        if image_refs and data.get("sections"):
            first = data["sections"][0]
            if isinstance(first, dict):
                first["image_refs"] = image_refs[:1]
                if not first.get("diagram_placeholder"):
                    first["diagram_placeholder"] = "Refer to the diagram below."
        try:
            from app.lesson.diagram import generate_diagram_svg

            for section in data.get("sections") or []:
                if not isinstance(section, dict):
                    continue
                if section.get("image_refs"):
                    continue
                caption = section.get("diagram_placeholder")
                if caption:
                    section["diagram_svg"] = generate_diagram_svg(
                        self._pipeline.llm, str(caption)
                    )
        except Exception:
            logger.exception("Lesson diagram SVG step failed")
        if update_profile:
            try:
                from app.student.updater import LearningProfileUpdater

                LearningProfileUpdater().apply_event(
                    {
                        "kind": "lesson",
                        "topic": topic_label,
                        "subject": subject or "",
                        "title": data.get("title"),
                        "label": data.get("title") or topic_label,
                    }
                )
            except Exception:
                logger.exception("Failed to update Learning Profile after lesson")
        return data

    def teach_course_lesson(
        self,
        question: str,
        *,
        top_k: int = COURSE_LESSON_TOP_K,
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        query: str | None = None,
        history: list[dict[str, str]] | None = None,
        update_profile: bool = False,
        include_diagrams: bool = False,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Two-pass Learn lesson: frame headings, then expand each section.

        Tutor ``teach()`` stays unchanged (diagrams on, global MAX_TOKENS).
        This path never raises that global cap. ``include_diagrams`` is always
        treated as False: skip ``collect_image_refs`` and ``generate_diagram_svg``.
        """
        from app.i18n.language import resolve_language
        from app.i18n.messages import ui_string

        del include_diagrams  # Learn never attaches figures
        lang = resolve_language(language)
        cleaned = question.strip()
        topic_label = topic or extract_topic(cleaned)
        if not cleaned:
            lesson = fallback_lesson(
                topic="Lesson",
                reason=ui_string("fallback_empty_topic", lang),
                refused=True,
                language=lang,
            )
            return _strip_course_diagrams(lesson.model_dump())

        history_block = format_history(history)
        prompt_question = _question_with_history(cleaned, history_block)
        rag_query = (query or cleaned).strip() or cleaned

        retrieved = self._pipeline.retrieval.retrieve(
            rag_query,
            top_k=top_k,
            subject=subject,
            source=source,
        )
        scores = _scores_from_results(retrieved)
        confidence = blend_confidence(scores)
        refused = should_refuse(retrieved)

        prompts = self._pipeline.prompts
        render_frame = getattr(prompts, "render_lesson_course_frame", None)
        render_section = getattr(prompts, "render_lesson_course_section", None)

        builder = ContextBuilder(
            self._pipeline.llm,
            max_context_tokens=MAX_CONTEXT_TOKENS,
        )
        system = personalized_system(_COURSE_LESSON_SYSTEM, lang)
        if callable(render_frame):
            scaffolding = render_frame(context="", question=prompt_question)
        else:
            scaffolding = (
                f"=== Context ===\n\n=== Student request ===\n{prompt_question}"
            )
        reserved = self._pipeline.llm.count_tokens(system) + self._pipeline.llm.count_tokens(
            scaffolding
        )
        builder.reserved_tokens = min(reserved, max(0, MAX_CONTEXT_TOKENS // 4))

        if refused:
            context, selected = "", []
            citations: list[dict[str, Any]] = []
            logger.warning("Course lesson retrieval weak; generating with empty context")
        else:
            context, selected = builder.build(retrieved)
            citations = build_citations(selected)

        context_block = context or (
            "(No strong textbook passages retrieved - teach carefully.)"
        )
        if callable(render_frame):
            frame_user = render_frame(context=context_block, question=prompt_question)
        else:
            frame_user = f"=== Context ===\n{context_block}\n\n=== Student request ===\n{prompt_question}"

        try:
            raw_frame = _llm_generate(
                self._pipeline.llm,
                system,
                frame_user,
                max_tokens=COURSE_FRAME_MAX_TOKENS,
            )
        except Exception:
            logger.exception("Course lesson frame generate failed; using fallback")
            lesson = fallback_lesson(
                topic=topic_label,
                citations=citations,
                confidence=confidence,
                refused=refused,
                language=lang,
            )
            lesson.retrieved_chunks = selected
            data = _strip_course_diagrams(lesson.model_dump())
            data = self._expand_course_sections(
                data,
                context_block=context_block,
                prompt_question=prompt_question,
                render_section=render_section,
                system=system,
            )
            data = self._enrich_worked_example(
                data, context_block=context_block, language=lang
            )
            return self._finalize_course_lesson(
                data,
                topic_label=topic_label,
                subject=subject,
                selected=selected,
                update_profile=update_profile,
            )

        parsed = extract_json_object(raw_frame)
        frame_raw: str | dict[str, Any] = (
            _normalize_frame_dict(parsed) if isinstance(parsed, dict) else raw_frame
        )
        lesson = format_lesson(
            frame_raw,
            topic=topic_label,
            citations=citations,
            confidence=confidence,
            retrieved_chunks=selected,
            refused=refused,
        )
        data = _strip_course_diagrams(lesson.model_dump())
        data = self._expand_course_sections(
            data,
            context_block=context_block,
            prompt_question=prompt_question,
            render_section=render_section,
            system=system,
        )
        data = self._enrich_worked_example(
            data, context_block=context_block, language=lang
        )
        return self._finalize_course_lesson(
            data,
            topic_label=topic_label,
            subject=subject,
            selected=selected,
            update_profile=update_profile,
        )

    def _expand_course_sections(
        self,
        data: dict[str, Any],
        *,
        context_block: str,
        prompt_question: str,
        render_section: Any,
        system: str,
    ) -> dict[str, Any]:
        """Pass B: long body for each heading, same packed textbook context.

        Sections that already have substantial prose from the frame pass (>= 60 words)
        are skipped to avoid redundant LLM calls. This reduces worst-case sequential
        calls from 7 down to only the sections that genuinely need expansion.
        """
        lesson_title = str(data.get("title") or "")
        # Cap at 5 sections — reduces worst-case calls from 7 to 5 while
        # preserving lesson quality for typical O-Level topics.
        sections = list(data.get("sections") or [])[:5]
        expanded: list[dict[str, Any]] = []
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                expanded.append(section)
                continue
            heading = str(section.get("heading") or f"Section {index + 1}").strip()
            existing_body = str(section.get("body") or "").strip()

            # Skip expansion if the frame already provided substantial prose.
            existing_word_count = len(existing_body.split()) if existing_body else 0
            if existing_word_count >= 60:
                logger.info(
                    "Skipping expansion for '%s' — frame provided %d words",
                    heading,
                    existing_word_count,
                )
                copy = dict(section)
                copy["heading"] = heading
                copy["diagram_placeholder"] = None
                copy["diagram_svg"] = None
                expanded.append(copy)
                continue

            if callable(render_section):
                user = render_section(
                    context=context_block,
                    question=prompt_question,
                    heading=heading,
                    lesson_title=lesson_title,
                )
            else:
                user = (
                    f"=== Context ===\n{context_block}\n\n"
                    f"=== Lesson title ===\n{lesson_title}\n"
                    f"=== Section heading ===\n{heading}\n\n"
                    f"=== Student request ===\n{prompt_question}\n\n"
                    "Return JSON with heading and a long body."
                )
            body = ""
            try:
                raw = _llm_generate(
                    self._pipeline.llm,
                    system,
                    user,
                    max_tokens=COURSE_SECTION_MAX_TOKENS,
                )
                body = _body_from_section_output(raw, heading)
            except Exception:
                logger.exception("Course section expand failed for %s", heading)
            copy = dict(section)
            if body:
                copy["body"] = body
            copy["heading"] = heading
            copy["diagram_placeholder"] = None
            copy["diagram_svg"] = None
            expanded.append(copy)
        data["sections"] = expanded
        return _strip_course_diagrams(data)

    def _enrich_worked_example(
        self,
        data: dict[str, Any],
        *,
        context_block: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """If the worked example has fewer than 6 steps, expand it (max_tokens=512)."""
        worked = data.get("worked_example")
        if not isinstance(worked, dict):
            return data
        steps = worked.get("steps")
        if not isinstance(steps, list):
            steps = []
        step_list = [str(item).strip() for item in steps if str(item).strip()]
        if len(step_list) >= 6:
            return data
        problem = str(worked.get("problem") or "").strip()
        answer = str(worked.get("answer") or "").strip()
        user = (
            f"Same textbook context.\n\n=== Context ===\n{context_block}\n\n"
            f"=== Worked example ===\nProblem: {problem or '(write a suitable exam-style problem)'}\n"
            f"Current steps: {step_list or '(none)'}\n"
            f"Answer: {answer or '(state the final answer)'}\n\n"
            "Expand the worked example to 6-10 reasoning steps, not three one-liners. "
            "Keep the same problem and final answer unless they are empty. "
            "Return ONLY JSON:\n"
            '{"problem": "...", "steps": ["...", "..."], "answer": "..."}'
        )
        try:
            raw = _llm_generate(
                self._pipeline.llm,
                personalized_system(_ENRICH_SYSTEM, language),
                user,
                max_tokens=COURSE_ENRICH_MAX_TOKENS,
            )
            parsed = extract_json_object(raw)
        except Exception:
            logger.exception("Worked-example enrich failed")
            return data
        if not isinstance(parsed, dict):
            return data
        new_steps = parsed.get("steps")
        if isinstance(new_steps, str) and new_steps.strip():
            new_list = [new_steps.strip()]
        elif isinstance(new_steps, list):
            new_list = [str(item).strip() for item in new_steps if str(item).strip()]
        else:
            new_list = []
        if len(new_list) < 6:
            return data
        data["worked_example"] = {
            "problem": str(parsed.get("problem") or problem).strip() or problem,
            "steps": new_list[:10],
            "answer": str(parsed.get("answer") or answer).strip() or answer,
        }
        return data

    def _finalize_course_lesson(
        self,
        data: dict[str, Any],
        *,
        topic_label: str,
        subject: str | None,
        selected: list[dict[str, Any]],
        update_profile: bool,
    ) -> dict[str, Any]:
        data = _strip_course_diagrams(data)
        data["retrieved_chunks"] = selected
        if update_profile:
            try:
                from app.student.updater import LearningProfileUpdater

                LearningProfileUpdater().apply_event(
                    {
                        "kind": "lesson",
                        "topic": topic_label,
                        "subject": subject or "",
                        "title": data.get("title"),
                        "label": data.get("title") or topic_label,
                    }
                )
            except Exception:
                logger.exception("Failed to update Learning Profile after course lesson")
        return data

    def grade(
        self,
        *,
        question: str,
        expected_answer: str,
        student_answer: str,
        explanation: str | None = None,
        kind: str = "practice",
        title: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Personalized teaching feedback; falls back to practice.explanation."""
        from app.i18n.language import resolve_language

        lang = resolve_language(language)
        correct = answers_match(expected_answer, student_answer)
        user = (
            f"Lesson topic: {title or 'this topic'}\n"
            f"Question kind: {kind}\n"
            f"Question: {question}\n"
            f"Expected answer: {expected_answer}\n"
            f"Student answer: {student_answer}\n"
            f"Deterministic match: {correct}\n"
            f"Teacher explanation (optional): {explanation or '(none)'}\n\n"
            "Write JSON feedback that teaches the idea. "
            "If the student is right, affirm and deepen slightly. "
            "If wrong, explain the misconception and the better answer."
        )
        raw = ""
        try:
            raw = self._pipeline.llm.generate(
                personalized_system(_FEEDBACK_SYSTEM, lang), user
            )
            feedback = format_feedback(
                raw,
                correct=correct,
                explanation=explanation,
                expected_answer=expected_answer,
            )
        except Exception:
            logger.exception("Feedback LLM failed; using deterministic explanation")
            feedback = format_feedback(
                None,
                correct=correct,
                explanation=explanation,
                expected_answer=expected_answer,
            )
        payload = feedback.model_dump()
        confused = None
        if raw:
            try:
                from app.lesson.lesson_formatter import extract_json_object

                parsed = extract_json_object(raw)
                if isinstance(parsed, dict) and parsed.get("confused"):
                    confused = str(parsed["confused"])
            except Exception:
                confused = None
        try:
            from app.student.updater import LearningProfileUpdater

            LearningProfileUpdater().apply_event(
                {
                    "kind": "practice",
                    "topic": title or "lesson",
                    "subject": "",
                    "correct": payload.get("correct", correct),
                    "confused": confused
                    or (
                        None
                        if payload.get("correct")
                        else f"Needs review: {title or question[:40]}"
                    ),
                    "label": f"Lesson {kind}",
                }
            )
        except Exception:
            logger.exception("Failed to update Learning Profile after lesson feedback")
        if confused:
            payload["confused"] = confused
        return payload
