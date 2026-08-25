"""Orchestrate Study (RAG) vs General (LLM-only) ask flows."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
import re
from typing import Any, TypedDict

from app.config import (
    CONFIDENCE_MEAN_WEIGHT,
    CONFIDENCE_TOP_WEIGHT,
    MAX_CONTEXT_TOKENS,
    PROJECT_ROOT,
    TOP_K,
)
from app.generation.citations import build_citations
from app.generation.context_builder import ContextBuilder
from app.generation.hallucination import refusal_message, should_refuse, warn_if_low_coverage
from app.generation.llm import LLMClient, get_llm
from app.generation.prompt_manager import PromptManager, get_prompt_manager
from app.generation.rag import RetrievalService
from app.generation.router import QueryMode, QueryRouter, get_router
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ChatResult(TypedDict, total=False):
    """Normalized dictionary returned by study and general chat handlers."""

    type: str
    mode: str
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    retrieved_chunks: list[dict[str, Any]]
    refused: bool
    image_refs: list[dict[str, Any]]


def blend_confidence(
    scores: list[float],
    *,
    top_weight: float = CONFIDENCE_TOP_WEIGHT,
    mean_weight: float = CONFIDENCE_MEAN_WEIGHT,
) -> float:
    """``0.7 * top + 0.3 * mean(top_3)`` (uses available scores if fewer than 3)."""
    if not scores:
        return 0.0
    top = scores[0]
    top3 = scores[:3]
    mean_top3 = sum(top3) / len(top3)
    return float(top_weight * top + mean_weight * mean_top3)


def _scores_from_results(results: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for item in results:
        score = item.get("score")
        if isinstance(score, (int, float)):
            out.append(float(score))
    return out


def format_history(
    history: list[dict[str, str]] | None,
    *,
    max_turns: int = 6,
) -> str:
    """Format the last ``max_turns`` chat messages for optional prompt context.

    Empty / missing history returns ``""`` so Study/General prompts are unchanged.
    Each turn's content is capped at 2000 characters to prevent oversized
    history from flooding the context window.
    """
    if not history:
        return ""
    lines: list[str] = []
    for turn in history[-max_turns:]:
        role = str(turn.get("role", "")).strip().lower()
        # Cap per-turn content — prevents oversized history from flooding context.
        content = str(turn.get("content", "")).strip()[:2000]
        if not content:
            continue
        label = "User" if role == "user" else "Assistant" if role == "assistant" else None
        if label is None:
            continue
        lines.append(f"{label}: {content}")
    if not lines:
        return ""
    return "Recent conversation:\n" + "\n".join(lines)


def _question_with_history(question: str, history_block: str) -> str:
    if not history_block:
        return question
    return f"{history_block}\n\n{question}"


def clean_chat_response(raw: str) -> str:
    """Normalize chat generation output: unwrap accidental JSON, unescape newlines, and clean math artifacts."""
    s = raw.strip()
    if not s:
        return ""

    # 1. Unwrap JSON wrapper if present (full or truncated by max_tokens)
    m = re.match(
        r'^\s*\{\s*"(?:answer|explanation|text|response|reply|content)"\s*:\s*"(.*)',
        s,
        re.DOTALL,
    )
    if m:
        s = m.group(1)
        s = re.sub(r'"\s*\}?\s*$', "", s)
        s = (
            s.replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\\\", "\\")
        )
    elif r"\n" in s and "\n" not in s:
        s = s.replace(r"\n", "\n").replace(r"\t", "\t")

    # 2. Clean duplicated MathML / KaTeX web-scraping artifacts:
    # e.g. single character on newline followed by same character: \nV\nV -> $V$
    s = re.sub(r"\n([A-Za-z0-9])\n\1\b", r" $\1$", s)
    # e.g. multi-line split symbols followed by compacted formula: \nV\n=\nR\nI\nV=RI -> $V=RI$
    s = re.sub(r"(?:\n[A-Za-z0-9=∝/+\-Δ]+)+\n([A-Za-z0-9=∝/+\-Δ]+)", r" $\1$", s)
    # Convert unicode math operators to LaTeX math representations
    s = s.replace("∝", r" \propto ").replace("Δ", r"\Delta ")

    return s.strip()


def _stream_clean_tokens(token_stream: Iterable[str]) -> Iterator[str]:
    """Filter out accidental leading JSON wrapper syntax and unescape newlines."""
    buf = ""
    prefix_checked = False
    in_json = False
    tail = ""

    for token in token_stream:
        if not prefix_checked:
            buf += token
            stripped = buf.lstrip()
            if stripped and not stripped.startswith("{"):
                prefix_checked = True
                yield buf
                buf = ""
                continue
            m = re.match(
                r'^\s*\{\s*"(?:answer|explanation|text|response|reply|content)"\s*:\s*"',
                buf,
            )
            if m:
                prefix_checked = True
                in_json = True
                rem = buf[m.end():]
                buf = ""
                if rem:
                    rem = (
                        rem.replace(r"\n", "\n")
                        .replace(r"\t", "\t")
                        .replace(r'\"', '"')
                    )
                    tail = rem
                continue
            elif len(buf) > 30:
                prefix_checked = True
                yield buf
                buf = ""
                continue
        else:
            if in_json:
                token = (
                    token.replace(r"\n", "\n")
                    .replace(r"\t", "\t")
                    .replace(r'\"', '"')
                )
                tail += token
                if len(tail) > 4:
                    to_yield = tail[:-4]
                    tail = tail[-4:]
                    yield to_yield
            else:
                yield token

    if buf:
        if not prefix_checked:
            m = re.match(
                r'^\s*\{\s*"(?:answer|explanation|text|response|reply|content)"\s*:\s*"',
                buf,
            )
            if m:
                buf = buf[m.end():]
        tail = buf

    if in_json and tail:
        tail = re.sub(r'"\s*\}?\s*$', "", tail)
        tail = tail.replace(r"\n", "\n").replace(r"\t", "\t").replace(r'\"', '"')

    if tail:
        yield tail


def personalized_system(base: str, language: str | None = None) -> str:
    """Prepend tutor persona + Learning Profile journal (never raw sessions)."""
    from app.i18n.language import language_instruction, resolve_language

    lang = resolve_language(language)
    instruction = language_instruction(lang)
    try:
        from app.student.context import build_prompt_context

        block = build_prompt_context()
    except Exception:
        logger.exception("Learning Profile context unavailable; using base system prompt")
        return f"{instruction}\n\n{base}"
    return f"{block}\n\n{instruction}\n\n{base}"


def collect_image_refs(chunks: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    """Extract textbook image paths from retrieved chunk metadata."""
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in chunks:
        meta = item.get("metadata") or {}
        page = meta.get("page") or meta.get("page_number")
        images = meta.get("images") or []
        if isinstance(images, str):
            images = [images]
        if not isinstance(images, list):
            continue
        for img in images:
            path = str(img).strip()
            if not path or path in seen:
                continue
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = (PROJECT_ROOT / file_path).resolve()
            if not file_path.is_file():
                continue
            seen.add(path)
            refs.append(
                {
                    "path": str(file_path),
                    "url": f"/media?path={file_path}",
                    "caption": str(meta.get("caption") or meta.get("topic") or "Textbook diagram"),
                    "page": page,
                }
            )
            if len(refs) >= limit:
                return refs
    return refs


class GenerationPipeline:
    """Route each question to Study (RAG) or General (same local Gemma)."""

    def __init__(
        self,
        *,
        retrieval: RetrievalService | None = None,
        llm: LLMClient | None = None,
        prompts: PromptManager | None = None,
        router: QueryRouter | None = None,
        max_context_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> None:
        self._retrieval = retrieval
        self._llm = llm
        self._prompts = prompts
        self._router = router
        self._max_context_tokens = max_context_tokens
        self._handlers: dict[QueryMode, Callable[..., dict[str, Any]]] = {
            QueryMode.STUDY: self._ask_study,
            QueryMode.GENERAL: self._ask_general,
            QueryMode.LESSON: self._ask_lesson,
        }

    @property
    def retrieval(self) -> RetrievalService:
        if self._retrieval is None:
            self._retrieval = RetrievalService()
        return self._retrieval

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    @property
    def prompts(self) -> PromptManager:
        if self._prompts is None:
            self._prompts = get_prompt_manager()
        return self._prompts

    @property
    def router(self) -> QueryRouter:
        if self._router is None:
            self._router = get_router()
        return self._router

    def ask(
        self,
        question: str,
        *,
        top_k: int = TOP_K,
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        history: list[dict[str, str]] | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Classify then dispatch Study / General / Lesson handlers.

        Study/General return::

            {
                "type": "chat",
                "mode": "study" | "general",
                "answer": str,
                "citations": list[dict],
                "confidence": float,
                "retrieved_chunks": list[dict],
                "refused": bool,
            }

        Lesson mode returns a structured ``type: "lesson"`` payload
        (see :class:`app.lesson.lesson_models.LessonPayload`).
        """
        cleaned = question.strip()
        if not cleaned:
            return {
                "type": "chat",
                "mode": QueryMode.GENERAL.value,
                "answer": "",
                "citations": [],
                "confidence": 0.0,
                "retrieved_chunks": [],
                "refused": True,
            }

        from app.i18n.language import resolve_language

        lang = resolve_language(language)
        history_block = format_history(history)
        mode = self.router.classify(cleaned)
        if mode is QueryMode.LESSON:
            return self._ask_lesson(
                cleaned,
                top_k=top_k,
                subject=subject,
                topic=topic,
                source=source,
                history=history,
                language=lang,
            )
        handler = self._handlers.get(mode)
        if handler is None:
            logger.warning("No handler for mode %s; falling back to general", mode)
            handler = self._ask_general
        return handler(
            cleaned,
            top_k=top_k,
            subject=subject,
            topic=topic,
            source=source,
            history_block=history_block,
            language=lang,
        )

    def stream_ask(
        self,
        question: str,
        *,
        top_k: int = TOP_K,
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        history: list[dict[str, str]] | None = None,
        language: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Stream chat tokens with query routing, retrieval, and guardrails."""
        cleaned = question.strip()
        if not cleaned:
            yield {
                "type": "meta",
                "mode": QueryMode.GENERAL.value,
                "citations": [],
                "confidence": 0.0,
                "refused": True,
            }
            return

        from app.i18n.language import resolve_language

        lang = resolve_language(language)
        history_block = format_history(history)
        mode = self.router.classify(cleaned)

        if mode is QueryMode.STUDY:
            retrieved = self.retrieval.retrieve(
                cleaned,
                top_k=top_k,
                subject=subject,
                topic=topic,
                source=source,
            )
            scores = _scores_from_results(retrieved)
            confidence = blend_confidence(scores)

            if should_refuse(retrieved):
                logger.info("Refusing answer in stream (empty or low retrieval score)")
                yield {
                    "type": "meta",
                    "mode": QueryMode.STUDY.value,
                    "citations": [],
                    "confidence": confidence,
                    "refused": True,
                }
                yield {"type": "token", "token": refusal_message(lang)}
                return

            prompt_question = _question_with_history(cleaned, history_block)
            builder = ContextBuilder(
                self.llm,
                max_context_tokens=self._max_context_tokens,
            )
            system = personalized_system(self.prompts.system_prompt, lang)
            scaffolding = self.prompts.render_user(context="", question=prompt_question)
            reserved = self.llm.count_tokens(system) + self.llm.count_tokens(scaffolding)
            builder.reserved_tokens = min(reserved, max(0, self._max_context_tokens // 4))

            context, selected = builder.build(retrieved)
            citations = build_citations(selected)
            user = self.prompts.render_user(context=context, question=prompt_question)

            yield {
                "type": "meta",
                "mode": QueryMode.STUDY.value,
                "citations": citations,
                "confidence": confidence,
                "refused": False,
            }

            accumulated: list[str] = []
            for token in _stream_clean_tokens(self.llm.stream_generate(system, user)):
                accumulated.append(token)
                yield {"type": "token", "token": token}

            warn_if_low_coverage("".join(accumulated), selected)
            try:
                from app.student.updater import LearningProfileUpdater

                LearningProfileUpdater().apply_event(
                    {"kind": "chat", "label": cleaned[:80], "mode": "study"}
                )
            except Exception:
                logger.exception("Failed to update Learning Profile after study stream")

        else:
            prompt_question = _question_with_history(cleaned, history_block)
            system = personalized_system(self.prompts.general_system_prompt, lang)
            user = self.prompts.render_general_user(question=prompt_question)

            yield {
                "type": "meta",
                "mode": QueryMode.GENERAL.value,
                "citations": [],
                "confidence": 1.0,
                "refused": False,
            }

            for token in _stream_clean_tokens(self.llm.stream_generate(system, user)):
                yield {"type": "token", "token": token}

            try:
                from app.student.updater import LearningProfileUpdater

                LearningProfileUpdater().apply_event(
                    {"kind": "chat", "label": cleaned[:80], "mode": "general"}
                )
            except Exception:
                logger.exception("Failed to update Learning Profile after general stream")

    def _ask_study(
        self,
        question: str,
        *,
        top_k: int = TOP_K,
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        history_block: str = "",
        language: str | None = None,
    ) -> ChatResult:
        """Existing offline RAG path: retrieve → guard → context → study prompts."""
        retrieved = self.retrieval.retrieve(
            question,
            top_k=top_k,
            subject=subject,
            topic=topic,
            source=source,
        )
        scores = _scores_from_results(retrieved)
        confidence = blend_confidence(scores)

        if should_refuse(retrieved):
            logger.info("Refusing answer (empty or low retrieval score)")
            return {
                "type": "chat",
                "mode": QueryMode.STUDY.value,
                "answer": refusal_message(language),
                "citations": [],
                "confidence": confidence,
                "retrieved_chunks": retrieved,
                "refused": True,
            }

        prompt_question = _question_with_history(question, history_block)
        builder = ContextBuilder(
            self.llm,
            max_context_tokens=self._max_context_tokens,
        )
        # Reserve a small allowance for system/user scaffolding when practical.
        system = personalized_system(self.prompts.system_prompt, language)
        scaffolding = self.prompts.render_user(context="", question=prompt_question)
        reserved = self.llm.count_tokens(system) + self.llm.count_tokens(scaffolding)
        builder.reserved_tokens = min(reserved, max(0, self._max_context_tokens // 4))

        context, selected = builder.build(retrieved)
        citations = build_citations(selected)
        user = self.prompts.render_user(context=context, question=prompt_question)
        answer = self.llm.generate(system, user)
        answer = clean_chat_response(answer)
        # Lightweight coverage check: warn if answer has little overlap with context.
        warn_if_low_coverage(answer, selected)
        try:
            from app.student.updater import LearningProfileUpdater

            LearningProfileUpdater().apply_event(
                {"kind": "chat", "label": question[:80], "mode": "study"}
            )
        except Exception:
            logger.exception("Failed to update Learning Profile after study chat")

        return {
            "type": "chat",
            "mode": QueryMode.STUDY.value,
            "answer": answer,
            "citations": citations,
            "confidence": confidence,
            "retrieved_chunks": selected,
            "image_refs": collect_image_refs(selected),
            "refused": False,
        }

    def _ask_general(
        self,
        question: str,
        *,
        top_k: int = TOP_K,  # unused; kept for uniform handler signature
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        history_block: str = "",
        language: str | None = None,
    ) -> ChatResult:
        """LLM-only path on the same ``get_llm()`` singleton; no retrieval."""
        _ = (top_k, subject, topic, source)
        prompt_question = _question_with_history(question, history_block)
        system = personalized_system(self.prompts.general_system_prompt, language)
        user = self.prompts.render_general_user(question=prompt_question)
        answer = self.llm.generate(system, user)
        answer = clean_chat_response(answer)
        try:
            from app.student.updater import LearningProfileUpdater

            LearningProfileUpdater().apply_event(
                {"kind": "chat", "label": question[:80], "mode": "general"}
            )
        except Exception:
            logger.exception("Failed to update Learning Profile after general chat")
        return {
            "type": "chat",
            "mode": QueryMode.GENERAL.value,
            "answer": answer,
            "citations": [],
            "confidence": 1.0,
            "retrieved_chunks": [],
            "image_refs": [],
            "refused": False,
        }

    def _ask_lesson(
        self,
        question: str,
        *,
        top_k: int = TOP_K,
        subject: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        history: list[dict[str, str]] | None = None,
        history_block: str = "",  # unused; LessonEngine formats history itself
        language: str | None = None,
    ) -> dict[str, Any]:
        """Delegate to LessonEngine (structured JSON lesson UI)."""
        _ = history_block
        from app.lesson.lesson_engine import LessonEngine

        return LessonEngine(self).teach(
            question,
            top_k=top_k,
            subject=subject,
            topic=topic,
            source=source,
            history=history,
            language=language,
        )


def ask(
    question: str,
    *,
    top_k: int = TOP_K,
    subject: str | None = None,
    topic: str | None = None,
    source: str | None = None,
    history: list[dict[str, str]] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper around a default :class:`GenerationPipeline`."""
    return GenerationPipeline().ask(
        question,
        top_k=top_k,
        subject=subject,
        topic=topic,
        source=source,
        history=history,
        language=language,
    )
