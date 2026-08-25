"""Parse / normalize LLM lesson JSON into safe LessonPayload models."""

from __future__ import annotations

import json
import re
from typing import Any

from app.lesson.lesson_models import (
    CheckUnderstanding,
    LessonFeedback,
    LessonPayload,
    LessonSection,
    PracticeItem,
    RevisionCard,
    WorkedExample,
)

_CODE_FENCE_RE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
_CHUNK_CITE_RE = re.compile(r"\s*\[Chunk\s+[^\]]+\]", re.IGNORECASE)
_BODY_FIELD_RE = re.compile(
    r'"(?:body|content|text)"\s*:\s*"((?:\\.|[^"\\])*)(?:"|\Z)',
    re.DOTALL,
)


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _looks_like_json_blob(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if s.startswith("```"):
        return True
    if s.startswith("{") and ("\"heading\"" in s or "\"body\"" in s or "\"sections\"" in s):
        return True
    return False


def strip_chunk_citations(text: str) -> str:
    """Remove internal RAG chunk markers from student-facing lesson prose."""
    cleaned = _CHUNK_CITE_RE.sub("", text or "")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _unescape_json_string(value: str) -> str:
    """Unescape JSON string content.

    Primary path: standard JSON parsing via json.loads (preserves all standard
    escapes including \\", \\\\, \\n, \\t, \\r, \\b, \\f, and \\uXXXX unicode).
    Recovery path: robust manual substitution for truncated or malformed JSON
    strings that contain unescaped quotes or invalid control characters.
    """
    if not value:
        return ""
    try:
        return json.loads(f'"{value}"')
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        pass

    def _replace_escape(match: re.Match[str]) -> str:
        esc = match.group(1)
        if esc == "n":
            return "\n"
        if esc == "t":
            return "\t"
        if esc == "r":
            return "\r"
        if esc == '"':
            return '"'
        if esc == "\\":
            return "\\"
        if esc.startswith("u") and len(esc) == 5:
            try:
                return chr(int(esc[1:], 16))
            except ValueError:
                return match.group(0)
        return match.group(0)

    return re.sub(r'\\(\\|"|n|t|r|u[0-9a-fA-F]{4})', _replace_escape, value)


def _body_from_broken_json(raw: str) -> str:
    """Pull a body field out of truncated / invalid JSON when json.loads fails."""
    text = (raw or "").strip()
    fence = _CODE_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    else:
        # Truncated fence with no closing ```
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    match = _BODY_FIELD_RE.search(text)
    if match:
        return strip_chunk_citations(_unescape_json_string(match.group(1)).strip())
    return ""


def sanitize_section_body(raw: str, *, heading: str = "") -> str:
    """Never leave fenced/raw JSON in a lesson section body."""
    text = (raw or "").strip()
    if not text:
        return ""
    if not _looks_like_json_blob(text):
        return strip_chunk_citations(text)

    parsed = extract_json_object(text)
    if isinstance(parsed, dict):
        for key in ("body", "content", "text"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return strip_chunk_citations(value.strip())
        sections = parsed.get("sections")
        if isinstance(sections, list):
            needle = heading.strip().lower()
            for item in sections:
                if not isinstance(item, dict):
                    continue
                item_heading = str(item.get("heading") or item.get("title") or "").strip().lower()
                body = str(item.get("body") or item.get("content") or "").strip()
                if body and (not needle or item_heading == needle or needle in item_heading):
                    return strip_chunk_citations(body)
            for item in sections:
                if isinstance(item, dict):
                    body = str(item.get("body") or item.get("content") or "").strip()
                    if body:
                        return strip_chunk_citations(body)
                elif isinstance(item, str) and item.strip() and not _looks_like_json_blob(item):
                    return strip_chunk_citations(item.strip())
        # Model returned only a heading - no usable prose
        return ""

    recovered = _body_from_broken_json(text)
    if recovered:
        return recovered
    # Last resort: drop JSON blobs rather than show them in the UI
    if _looks_like_json_blob(text):
        return ""
    return strip_chunk_citations(text)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            s = _as_str(item)
            if s:
                out.append(s)
        return out
    return []


def extract_json_object(raw: str) -> dict[str, Any] | None:
    """Best-effort extract of a JSON object from LLM text."""
    text = (raw or "").strip()
    if not text:
        return None

    candidates: list[str] = [text]

    # Prefer a whole-text parse first. Nested ```json fences inside string
    # values (section bodies) must not steal the outer lesson object.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fence = _CODE_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())

    match = _JSON_OBJECT_RE.search(text)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _section_from_any(item: Any) -> LessonSection | None:
    if isinstance(item, str):
        body = sanitize_section_body(item.strip())
        if not body:
            return None
        return LessonSection(heading="Key idea", body=body)
    if not isinstance(item, dict):
        return None
    heading = _as_str(item.get("heading") or item.get("title"), "Key idea")
    body = sanitize_section_body(
        _as_str(item.get("body") or item.get("content") or item.get("text")),
        heading=heading,
    )
    diagram = item.get("diagram_placeholder")
    if diagram is not None:
        diagram = _as_str(diagram) or None
    svg_raw = item.get("diagram_svg")
    from app.lesson.diagram import fallback_diagram_svg, sanitize_svg

    svg = sanitize_svg(_as_str(svg_raw) if svg_raw else None)
    if not svg and diagram:
        svg = fallback_diagram_svg(diagram)
    if not body and not heading:
        return None
    return LessonSection(
        heading=heading or "Key idea",
        body=body,
        diagram_placeholder=diagram,
        diagram_svg=svg,
    )


def _worked_example(data: Any) -> WorkedExample:
    if not isinstance(data, dict):
        return WorkedExample()
    steps = data.get("steps")
    if isinstance(steps, str):
        step_list = [steps.strip()] if steps.strip() else []
    else:
        step_list = _as_str_list(steps)
    return WorkedExample(
        problem=_as_str(data.get("problem") or data.get("question")),
        steps=step_list,
        answer=_as_str(data.get("answer") or data.get("final_answer")),
    )


def _check_understanding(data: Any) -> CheckUnderstanding:
    if not isinstance(data, dict):
        return CheckUnderstanding()
    return CheckUnderstanding(
        question=_as_str(data.get("question")),
        expected_answer=_as_str(
            data.get("expected_answer") or data.get("answer") or data.get("correct_answer")
        ),
        hint=_as_str(data.get("hint")),
    )


def _practice(data: Any) -> PracticeItem:
    if not isinstance(data, dict):
        return PracticeItem()
    options_raw = data.get("options")
    options: list[str] | None
    if options_raw is None:
        options = None
    elif isinstance(options_raw, list):
        options = _as_str_list(options_raw) or None
    else:
        options = None
    return PracticeItem(
        question=_as_str(data.get("question")),
        options=options,
        correct_answer=_as_str(
            data.get("correct_answer") or data.get("answer") or data.get("expected_answer")
        ),
        explanation=_as_str(data.get("explanation")),
    )


def _revision_card(data: Any) -> RevisionCard:
    if not isinstance(data, dict):
        return RevisionCard()
    return RevisionCard(
        front=_as_str(data.get("front") or data.get("question")),
        back=_as_str(data.get("back") or data.get("answer")),
    )


def fallback_lesson(
    *,
    topic: str,
    reason: str | None = None,
    citations: list[dict[str, Any]] | None = None,
    confidence: float = 0.0,
    refused: bool = False,
    language: str | None = None,
) -> LessonPayload:
    """Safe structured lesson when the LLM output cannot be used."""
    from app.i18n.language import resolve_language
    from app.i18n.messages import ui_string

    lang = resolve_language(language)
    title = topic.strip() or ui_string("fallback_title", lang)
    intro = reason or ui_string("fallback_intro", lang, title=title)
    from app.lesson.diagram import fallback_diagram_svg

    placeholder = f"Simple diagram for {title}"
    kw = {"title": title}
    return LessonPayload(
        type="lesson",
        title=title,
        introduction=intro,
        objectives=[
            ui_string("fallback_obj_1", lang, **kw),
            ui_string("fallback_obj_2", lang),
            ui_string("fallback_obj_3", lang),
        ],
        sections=[
            LessonSection(
                heading=ui_string("fallback_heading_idea", lang),
                body=ui_string("fallback_body_idea", lang, **kw),
                diagram_placeholder=placeholder,
                diagram_svg=fallback_diagram_svg(placeholder),
            ),
            LessonSection(
                heading=ui_string("fallback_heading_remember", lang),
                body=ui_string("fallback_body_remember", lang),
            ),
        ],
        worked_example=WorkedExample(
            problem=ui_string("fallback_problem", lang, **kw),
            steps=[
                ui_string("fallback_step_1", lang),
                ui_string("fallback_step_2", lang),
                ui_string("fallback_step_3", lang),
            ],
            answer=ui_string("fallback_answer", lang, **kw),
        ),
        check_understanding=CheckUnderstanding(
            question=ui_string("fallback_check_q", lang, **kw),
            expected_answer=ui_string("fallback_check_a", lang, **kw),
            hint=ui_string("fallback_hint", lang),
        ),
        practice=PracticeItem(
            question=ui_string("fallback_practice_q", lang, **kw),
            options=[
                ui_string("fallback_opt_a", lang, **kw),
                ui_string("fallback_opt_b", lang),
                ui_string("fallback_opt_c", lang),
                ui_string("fallback_opt_d", lang),
            ],
            correct_answer="A",
            explanation=ui_string("fallback_explain", lang, **kw),
        ),
        summary=[
            ui_string("fallback_sum_1", lang, **kw),
            ui_string("fallback_sum_2", lang),
            ui_string("fallback_sum_3", lang),
        ],
        revision_card=RevisionCard(
            front=ui_string("fallback_rev_front", lang, **kw),
            back=ui_string("fallback_rev_back", lang, **kw),
        ),
        citations=list(citations or []),
        mode="lesson",
        confidence=confidence,
        refused=refused,
        answer=ui_string("fallback_ready", lang, **kw),
    )


def format_lesson(
    raw: str | dict[str, Any] | None,
    *,
    topic: str = "Lesson",
    citations: list[dict[str, Any]] | None = None,
    confidence: float = 0.0,
    retrieved_chunks: list[dict[str, Any]] | None = None,
    refused: bool = False,
) -> LessonPayload:
    """Normalize LLM output into a complete LessonPayload."""
    data: dict[str, Any] | None
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        data = extract_json_object(raw)
    else:
        data = None

    if data is None:
        from app.i18n.messages import ui_string

        lesson = fallback_lesson(
            topic=topic,
            reason=ui_string("format_fallback_reason"),
            citations=citations,
            confidence=confidence,
            refused=refused,
        )
        lesson.retrieved_chunks = list(retrieved_chunks or [])
        return lesson

    title = _as_str(data.get("title"), topic.strip() or "Lesson")
    introduction = _as_str(data.get("introduction") or data.get("intro"))
    objectives = _as_str_list(data.get("objectives"))

    sections_raw = data.get("sections")
    sections: list[LessonSection] = []
    if isinstance(sections_raw, list):
        for item in sections_raw:
            section = _section_from_any(item)
            if section is not None:
                sections.append(section)

    worked = _worked_example(data.get("worked_example"))
    check = _check_understanding(data.get("check_understanding"))
    practice = _practice(data.get("practice"))
    summary = _as_str_list(data.get("summary"))
    revision = _revision_card(data.get("revision_card"))

    cites = data.get("citations")
    if isinstance(cites, list) and cites:
        final_citations = cites
    else:
        final_citations = list(citations or [])

    # Fill critical gaps from fallback so the UI never receives empties.
    if not introduction or not sections or not practice.question:
        base = fallback_lesson(
            topic=title,
            citations=final_citations,
            confidence=confidence,
            refused=refused,
        )
        if not introduction:
            introduction = base.introduction
        if not objectives:
            objectives = base.objectives
        if not sections:
            sections = base.sections
        if not worked.problem:
            worked = base.worked_example
        if not check.question:
            check = base.check_understanding
        if not practice.question:
            practice = base.practice
        if not summary:
            summary = base.summary
        if not revision.front:
            revision = base.revision_card

    return LessonPayload(
        type="lesson",
        title=title,
        introduction=introduction,
        objectives=objectives,
        sections=sections,
        worked_example=worked,
        check_understanding=check,
        practice=practice,
        summary=summary,
        revision_card=revision,
        citations=final_citations,
        mode="lesson",
        confidence=confidence,
        retrieved_chunks=list(retrieved_chunks or []),
        refused=refused,
        answer=f"Lesson ready: {title}",
    )


def answers_match(expected: str, student: str) -> bool:
    """Loose equality for short answers / option letters."""
    exp = re.sub(r"\s+", " ", (expected or "").strip().lower())
    stu = re.sub(r"\s+", " ", (student or "").strip().lower())
    if not exp or not stu:
        return False
    if exp == stu:
        return True
    # Option letter: "A" vs "A. …"
    if len(exp) == 1 and exp.isalpha():
        if stu == exp or stu.startswith(f"{exp}.") or stu.startswith(f"{exp})"):
            return True
    if exp in stu or stu in exp:
        return True
    return False


def format_feedback(
    raw: str | dict[str, Any] | None,
    *,
    correct: bool,
    explanation: str | None = None,
    expected_answer: str = "",
) -> LessonFeedback:
    """Normalize feedback LLM output; fall back to practice explanation."""
    data: dict[str, Any] | None
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        data = extract_json_object(raw)
        if data is None and raw.strip():
            # Plain teaching prose from the model
            text = raw.strip()
            if text.lower() in {"correct.", "correct", "wrong.", "incorrect."}:
                text = ""
            if text:
                return LessonFeedback(
                    correct=correct,
                    feedback=text,
                    encouragement=(
                        "Nice work - keep going!"
                        if correct
                        else "You're learning - try the next step with confidence."
                    ),
                )
    else:
        data = None

    if data is not None:
        feedback = _as_str(data.get("feedback") or data.get("explanation") or data.get("message"))
        encouragement = _as_str(data.get("encouragement"))
        if "correct" in data:
            correct = bool(data.get("correct"))
        if feedback and feedback.lower() not in {"correct.", "correct", "wrong.", "incorrect."}:
            return LessonFeedback(
                correct=correct,
                feedback=feedback,
                encouragement=encouragement
                or (
                    "Nice work - keep going!"
                    if correct
                    else "You're learning - try the next step with confidence."
                ),
            )

    # Deterministic teaching fallback
    if correct:
        body = explanation or (
            f"Yes - that's right. The expected idea is: {expected_answer}"
            if expected_answer
            else "Yes - that's right. You understood the key idea."
        )
        if body.strip().lower() in {"correct.", "correct"}:
            body = f"Yes - that's right. The expected idea is: {expected_answer}"
        return LessonFeedback(
            correct=True,
            feedback=body,
            encouragement="Nice work - keep going!",
        )

    body = explanation or (
        f"Not quite. The better answer is: {expected_answer}. "
        "Compare your wording with that idea and try again in your own words."
        if expected_answer
        else "Not quite. Re-read the key definition, then try again in your own words."
    )
    return LessonFeedback(
        correct=False,
        feedback=body,
        encouragement="You're learning - mistakes are part of mastery.",
    )
