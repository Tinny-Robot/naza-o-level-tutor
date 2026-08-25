"""Tests for the offline generation layer (mocked LLM / retrieval; no GGUF)."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

import pytest

from app.generation.citations import build_citations
from app.generation.context_builder import ContextBuilder, format_chunk_block
from app.generation.hallucination import should_refuse
from app.generation.pipeline import ChatResult, GenerationPipeline, blend_confidence
from app.generation.prompt_manager import PromptManager
from app.generation.rag import RetrievalService
from app.generation.router import QueryMode


class _FixedRouter:
    """Stub router that always returns a fixed mode."""

    def __init__(self, mode: QueryMode) -> None:
        self.mode = mode
        self.calls: list[str] = []

    def classify(self, question: str) -> QueryMode:
        self.calls.append(question)
        return self.mode


def _sample_results() -> list[dict[str, Any]]:
    return [
        {
            "score": 0.91,
            "text": "Subject-verb concord requires the verb to agree with its subject.",
            "metadata": {
                "id": "12",
                "subject": "english",
                "topic": "concord",
                "source": "notes",
            },
        },
        {
            "score": 0.72,
            "text": "A singular subject takes a singular verb form.",
            "metadata": {
                "id": "34",
                "subject": "english",
                "topic": "grammar",
                "source": "notes",
            },
        },
        {
            "score": 0.55,
            "text": "Plural subjects take plural verbs.",
            "metadata": {
                "id": "56",
                "subject": "english",
                "topic": "grammar",
                "source": "notes",
            },
        },
    ]


class _StubLLM:
    """Records prompts and exposes a controllable tokenizer."""

    def __init__(self, *, token_fn=None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._token_fn = token_fn or (lambda text: max(1, len(text.split())))
        self.token_calls: list[str] = []

    def count_tokens(self, text: str) -> int:
        self.token_calls.append(text)
        return int(self._token_fn(text))

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return "Concord means the verb agrees with the subject."


class _StubRetriever:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self._results = results if results is not None else _sample_results()
        self.last_kwargs: dict[str, Any] = {}

    def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[dict[str, Any]]:
        self.last_kwargs = {"query": query, "top_k": top_k, **kwargs}
        return self._results[:top_k]


# ---------------------------------------------------------------------------
# Confidence blend
# ---------------------------------------------------------------------------


def test_blend_confidence_formula() -> None:
    # 0.7 * 0.91 + 0.3 * mean(0.91, 0.72, 0.55)
    scores = [0.91, 0.72, 0.55]
    mean_top3 = sum(scores) / 3
    expected = 0.7 * 0.91 + 0.3 * mean_top3
    assert blend_confidence(scores) == pytest.approx(expected)


def test_blend_confidence_fewer_than_three() -> None:
    scores = [0.8, 0.4]
    expected = 0.7 * 0.8 + 0.3 * ((0.8 + 0.4) / 2)
    assert blend_confidence(scores) == pytest.approx(expected)


def test_blend_confidence_empty() -> None:
    assert blend_confidence([]) == 0.0


# ---------------------------------------------------------------------------
# Hallucination / refuse
# ---------------------------------------------------------------------------


def test_should_refuse_empty() -> None:
    assert should_refuse([]) is True


def test_should_refuse_low_score() -> None:
    assert should_refuse([{"score": 0.1, "text": "x", "metadata": {}}]) is True


def test_should_refuse_ok() -> None:
    assert should_refuse([{"score": 0.9, "text": "x", "metadata": {}}]) is False


# ---------------------------------------------------------------------------
# Context builder - real token budget + [Chunk id]
# ---------------------------------------------------------------------------


def test_format_chunk_includes_chunk_id() -> None:
    block = format_chunk_block(_sample_results()[0])
    assert "[Chunk 12]" in block
    assert "Subject: english" in block
    assert "Topic: concord" in block
    assert "Source: notes" in block
    assert "Subject-verb concord" in block


def test_context_builder_uses_count_tokens() -> None:
    llm = _StubLLM(token_fn=lambda text: len(text))  # 1 token per char
    builder = ContextBuilder(llm, max_context_tokens=80, reserved_tokens=0)
    context, selected = builder.build(_sample_results())
    assert llm.token_calls, "ContextBuilder must call count_tokens"
    assert "[Chunk 12]" in context
    assert selected
    assert llm.count_tokens(context) <= 80
    # Tight budget: first chunk is truncated; later chunks may be omitted.
    assert len(selected) >= 1


def test_context_builder_dedupes_by_id() -> None:
    llm = _StubLLM()
    dup = _sample_results() + [_sample_results()[0]]
    builder = ContextBuilder(llm, max_context_tokens=10_000)
    _, selected = builder.build(dup)
    ids = [c["metadata"]["id"] for c in selected]
    assert ids == ["12", "34", "56"]


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


def test_build_citations() -> None:
    cites = build_citations(_sample_results()[:2])
    assert cites[0] == {
        "subject": "english",
        "topic": "concord",
        "source": "notes",
        "chunk_id": "12",
        "score": 0.91,
    }


# ---------------------------------------------------------------------------
# PromptManager cache
# ---------------------------------------------------------------------------


def test_prompt_manager_loads_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "system.txt").write_text("SYS {not_a_placeholder}", encoding="utf-8")
    (tmp_path / "user.txt").write_text("CTX={context} Q={question}", encoding="utf-8")
    (tmp_path / "general_system.txt").write_text("GEN_SYS", encoding="utf-8")
    (tmp_path / "general_user.txt").write_text("GQ={question}", encoding="utf-8")
    (tmp_path / "lesson_system.txt").write_text("LESSON_SYS", encoding="utf-8")
    (tmp_path / "lesson_user.txt").write_text("LCTX={context} LQ={question}", encoding="utf-8")

    prompt_names = {
        "system.txt",
        "user.txt",
        "general_system.txt",
        "general_user.txt",
        "lesson_system.txt",
        "lesson_user.txt",
    }
    reads: list[Path] = []
    original_read_text = Path.read_text

    def spy_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name in prompt_names:
            reads.append(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy_read_text)

    pm = PromptManager(prompts_dir=tmp_path)
    assert pm.load_count == 1
    first_reads = len(reads)

    _ = pm.system_prompt
    _ = pm.general_system_prompt
    rendered = pm.render_user(context="hello", question="world?")
    rendered2 = pm.render_user(context="again", question="more?")
    general = pm.render_general_user(question="hi there")
    lesson = pm.render_lesson_user(context="ctx", question="teach me x")

    assert rendered == "CTX=hello Q=world?"
    assert rendered2 == "CTX=again Q=more?"
    assert general == "GQ=hi there"
    assert lesson == "LCTX=ctx LQ=teach me x"
    assert pm.general_system_prompt == "GEN_SYS"
    assert pm.lesson_system_prompt == "LESSON_SYS"
    assert pm.load_count == 1
    assert len(reads) == first_reads  # no extra disk reads per ask


def test_prompt_manager_fallback_missing(tmp_path: Path) -> None:
    with pytest.warns(UserWarning, match="missing"):
        pm = PromptManager(prompts_dir=tmp_path)
    assert pm.system_prompt
    assert pm.general_system_prompt
    rendered = pm.render_user(context="ctx-body", question="q-body")
    assert "ctx-body" in rendered
    assert "q-body" in rendered
    general = pm.render_general_user(question="casual?")
    assert "casual?" in general


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def test_pipeline_success_path() -> None:
    llm = _StubLLM()
    retrieval = RetrievalService(retriever=_StubRetriever())  # type: ignore[arg-type]
    prompts = PromptManager()
    pipeline = GenerationPipeline(
        retrieval=retrieval,
        llm=llm,
        prompts=prompts,
        router=_FixedRouter(QueryMode.STUDY),  # type: ignore[arg-type]
    )

    result = pipeline.ask("Explain concord", top_k=2)

    assert result["mode"] == "study"
    assert result["type"] == "chat"
    assert result["refused"] is False
    assert result["answer"] == "Concord means the verb agrees with the subject."
    assert len(result["citations"]) >= 1
    assert result["citations"][0]["chunk_id"] == "12"
    assert result["confidence"] == pytest.approx(
        blend_confidence([0.91, 0.72])
    )
    assert result["retrieved_chunks"]
    assert len(llm.calls) == 1
    system, user = llm.calls[0]
    assert system
    assert "Explain concord" in user
    assert "[Chunk 12]" in user


def test_pipeline_refuses_and_skips_llm() -> None:
    llm = _StubLLM()
    low = [{"score": 0.1, "text": "noise", "metadata": {"id": "1", "subject": "x"}}]
    retrieval = RetrievalService(retriever=_StubRetriever(low))  # type: ignore[arg-type]
    pipeline = GenerationPipeline(
        retrieval=retrieval,
        llm=llm,
        prompts=PromptManager(),
        router=_FixedRouter(QueryMode.STUDY),  # type: ignore[arg-type]
    )

    result = pipeline.ask("Anything", top_k=1)

    assert result["mode"] == "study"
    assert result["refused"] is True
    assert "couldn't find enough information" in result["answer"].lower()
    assert result["citations"] == []
    assert result["confidence"] == pytest.approx(blend_confidence([0.1]))
    assert llm.calls == []


def test_pipeline_empty_question() -> None:
    llm = _StubLLM()
    stub = _StubRetriever()
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=stub),  # type: ignore[arg-type]
        llm=llm,
        prompts=PromptManager(),
    )
    result = pipeline.ask("   ")
    assert result["mode"] == "general"
    assert result["refused"] is True
    assert result["answer"] == ""
    assert llm.calls == []
    assert stub.last_kwargs == {}


def test_pipeline_general_skips_retrieval() -> None:
    llm = _StubLLM()
    stub = _StubRetriever()
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=stub),  # type: ignore[arg-type]
        llm=llm,
        prompts=PromptManager(),
        router=_FixedRouter(QueryMode.GENERAL),  # type: ignore[arg-type]
    )
    result = pipeline.ask("hello there", top_k=3)
    assert result["mode"] == "general"
    assert result["type"] == "chat"
    assert result["refused"] is False
    assert result["citations"] == []
    assert result["retrieved_chunks"] == []
    assert result["confidence"] == 1.0
    assert stub.last_kwargs == {}
    assert len(llm.calls) == 1
    system, user = llm.calls[0]
    assert "hello there" in user
    assert "[Chunk" not in user
    assert "Context" not in system or "offline" in system.lower() or system


def test_pipeline_study_still_retrieves() -> None:
    llm = _StubLLM()
    stub = _StubRetriever()
    router = _FixedRouter(QueryMode.STUDY)
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=stub),  # type: ignore[arg-type]
        llm=llm,
        prompts=PromptManager(),
        router=router,  # type: ignore[arg-type]
    )
    result = pipeline.ask("Explain Ohm's law", top_k=2)
    assert result["mode"] == "study"
    assert stub.last_kwargs.get("query") == "Explain Ohm's law"
    assert result["retrieved_chunks"]


def test_retrieval_service_forwards_filters() -> None:
    stub = _StubRetriever()
    service = RetrievalService(retriever=stub)  # type: ignore[arg-type]
    service.retrieve("q", top_k=3, subject="physics", topic="waves", source="book")
    assert stub.last_kwargs["subject"] == "physics"
    assert stub.last_kwargs["topic"] == "waves"
    assert stub.last_kwargs["source"] == "book"
    assert stub.last_kwargs["top_k"] == 3


# ---------------------------------------------------------------------------
# No cloud provider residue
# ---------------------------------------------------------------------------


def test_no_cloud_provider_imports_in_generation() -> None:
    gen_root = Path(__file__).resolve().parents[1] / "app" / "generation"
    banned = ("openai", "anthropic", "groq", "OpenAI", "Anthropic", "GROQ_API_KEY")
    for path in gen_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in banned:
            assert needle not in text, f"{path.name} still references {needle}"

    # Importing the package must not pull cloud SDKs.
    import app.generation as gen_pkg

    for mod in pkgutil.iter_modules(gen_pkg.__path__):
        importlib.import_module(f"app.generation.{mod.name}")

    cloud = {"openai", "anthropic", "groq"}
    loaded = {name.split(".")[0] for name in list(__import__("sys").modules)}
    assert cloud.isdisjoint(loaded) or not (cloud & loaded - {"groq"})
    # Stronger: openai/anthropic must not be loaded.
    assert "openai" not in __import__("sys").modules
    assert "anthropic" not in __import__("sys").modules


def test_config_has_no_cloud_keys() -> None:
    import app.config as cfg

    for name in (
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "LLM_PROVIDER",
        "resolve_llm_provider",
    ):
        assert not hasattr(cfg, name)

    assert cfg.MODEL_NAME == "Gemma-4-E4B-it"
    assert cfg.TEMPERATURE == 0.1
    assert cfg.THREADS >= 2
    assert cfg.MODEL_PATH.name.endswith(".gguf")
    assert cfg.EMBEDDING_MODEL_PATH.name == "KEmbed-naija-v3"
    assert isinstance(cfg.FLASH_ATTN, bool)
    assert isinstance(cfg.SWA_FULL, bool)


def test_build_llama_kwargs_wires_memory_knobs() -> None:
    from app.generation.llm import build_llama_kwargs

    kwargs = build_llama_kwargs(
        model_path="/tmp/model.gguf",
        n_ctx=4096,
        n_threads=4,
        flash_attn=True,
        swa_full=False,
    )
    assert kwargs["model_path"] == "/tmp/model.gguf"
    assert kwargs["n_ctx"] == 4096
    assert kwargs["n_threads"] == 4
    assert kwargs["n_gpu_layers"] == 0
    assert kwargs["flash_attn"] is True
    assert kwargs["swa_full"] is False
    assert kwargs["verbose"] is False


def test_llamacpp_llm_passes_kwargs_to_llama(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys
    import types

    from app.generation import llm as llm_mod

    gguf = tmp_path / "gemma-4-E4B-it-Q4_K_M.gguf"
    gguf.write_bytes(b"fake")

    captured: dict[str, Any] = {}

    class _StubLlama:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def tokenize(self, data: bytes, add_bos: bool = True) -> list[int]:
            return [1, 2, 3]

    fake_llama_cpp = types.ModuleType("llama_cpp")
    fake_llama_cpp.Llama = _StubLlama  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp)
    monkeypatch.setattr(llm_mod, "MODEL_PATH", gguf)

    client = llm_mod.LlamaCppLLM(
        model_path=gguf,
        n_ctx=2048,
        n_threads=3,
        flash_attn=True,
        swa_full=False,
    )
    assert captured["model_path"] == str(gguf)
    assert captured["n_ctx"] == 2048
    assert captured["n_threads"] == 3
    assert captured["flash_attn"] is True
    assert captured["swa_full"] is False
    assert captured["n_gpu_layers"] == 0
    assert client.llama_kwargs["flash_attn"] is True


# ---------------------------------------------------------------------------
# JSON recovery / _unescape_json_string hardening tests
# ---------------------------------------------------------------------------

class TestUnescapeJsonString:
    """Tests for lesson_formatter._unescape_json_string after hardening."""

    def setup_method(self) -> None:
        from app.lesson.lesson_formatter import _unescape_json_string
        self._fn = _unescape_json_string

    def test_empty_string(self) -> None:
        assert self._fn("") == ""

    def test_newline_escape(self) -> None:
        assert self._fn("hello\\nworld") == "hello\nworld"

    def test_tab_escape(self) -> None:
        assert self._fn("a\\tb") == "a\tb"

    def test_embedded_quote_does_not_crash(self) -> None:
        """This previously caused json.loads(f'"{value}"') to raise JSONDecodeError."""
        result = self._fn('say \\"hello\\" please')
        assert '"hello"' in result

    def test_backslash_escape(self) -> None:
        result = self._fn("path\\\\file")
        assert result == "path\\file"

    def test_plain_text_unchanged(self) -> None:
        text = "Photosynthesis converts light to glucose."
        assert self._fn(text) == text

    def test_multiple_escapes(self) -> None:
        result = self._fn("line1\\nline2\\nline3")
        assert result.count("\n") == 2

    def test_hausa_text_unchanged(self) -> None:
        """Hausa characters with hooked letters should pass through untouched."""
        text = "Makaranta tana koyar da ilimi mai fa'ida ga ɗalibai da ƙwararru."
        assert self._fn(text) == text

    def test_hausa_unicode_escapes_decoded(self) -> None:
        """Verify \\u018a (Ɗ) and \\u0199 (ƙ) are decoded correctly."""
        raw = "\\u018aalibi yana son karatu a \\u0199asar Hausa."
        assert self._fn(raw) == "Ɗalibi yana son karatu a ƙasar Hausa."

    def test_combinations_escapes(self) -> None:
        """Verify combinations of \\", \\\\, \\n, \\t in a single string."""
        raw = 'Title: \\"Photosynthesis\\"\\n\\tPoint 1: Light\\\\Energy\\n\\tPoint 2: H2O'
        expected = 'Title: "Photosynthesis"\n\tPoint 1: Light\\Energy\n\tPoint 2: H2O'
        assert self._fn(raw) == expected

    def test_embedded_unescaped_quotes_and_newlines(self) -> None:
        """Handle broken JSON with unescaped literal quotes and escaped newlines."""
        raw = 'He said "listen carefully"\\nbefore writing \\"WAEC\\".'
        assert self._fn(raw) == 'He said "listen carefully"\nbefore writing "WAEC".'

    def test_consecutive_backslashes_and_quotes(self) -> None:
        raw = '\\\\\\"'
        # \\ is \, \" is "
        assert self._fn(raw) == '\\"'

    def test_preserves_intended_prose_accurately(self) -> None:
        """Verify typical LLM educational response text is fully preserved."""
        raw = (
            "Equation:\\n"
            "6CO2 + 6H2O -> C6H12O6 + 6O2\\n"
            'Note: \\"Chlorophyll\\" acts as catalyst.\\t[Important]'
        )
        expected = (
            "Equation:\n"
            "6CO2 + 6H2O -> C6H12O6 + 6O2\n"
            'Note: "Chlorophyll" acts as catalyst.\t[Important]'
        )
        assert self._fn(raw) == expected


class TestFormatLessonMalformedJson:
    """format_lesson should never raise on malformed LLM output."""

    def test_empty_raw(self) -> None:
        from app.lesson.lesson_formatter import format_lesson
        lesson = format_lesson(None, topic="Test")
        assert lesson.title == "Test"

    def test_garbage_raw(self) -> None:
        from app.lesson.lesson_formatter import format_lesson
        lesson = format_lesson("not json at all!!! @@@ ###", topic="Test")
        assert lesson.title == "Test"

    def test_truncated_json(self) -> None:
        from app.lesson.lesson_formatter import format_lesson
        truncated = '{"title": "Osmosis", "introduction": "Plants use osmosis'
        lesson = format_lesson(truncated, topic="Osmosis")
        assert lesson.title == "Osmosis"

    def test_valid_json_parsed_correctly(self) -> None:
        from app.lesson.lesson_formatter import format_lesson
        raw = """{
            "title": "Photosynthesis",
            "introduction": "Plants make food.",
            "objectives": ["Understand photosynthesis"],
            "sections": [{"heading": "Light", "body": "Light is needed."}],
            "worked_example": {"problem": "A plant...", "steps": ["step1"], "answer": "glucose"},
            "check_understanding": {"question": "What does a plant need?", "expected_answer": "light"},
            "practice": {"question": "Which gas?", "options": ["A. CO2", "B. N2"], "correct_answer": "A", "explanation": "CO2"},
            "summary": ["Plants use light"],
            "revision_card": {"front": "Photosynthesis?", "back": "Light + CO2 = glucose"}
        }"""
        lesson = format_lesson(raw, topic="Photosynthesis")
        assert lesson.title == "Photosynthesis"
        assert lesson.introduction == "Plants make food."
        assert len(lesson.sections) == 1


class TestWarnIfLowCoverage:
    """Tests for the hallucination coverage warning."""

    def test_no_warning_on_high_overlap(self, caplog) -> None:
        import logging
        from app.generation.hallucination import warn_if_low_coverage
        chunks = [{"text": "photosynthesis occurs in chlorophyll using sunlight carbon dioxide"}]
        answer = "Photosynthesis uses sunlight and carbon dioxide in the chlorophyll."
        with caplog.at_level(logging.WARNING, logger="app.generation.hallucination"):
            warn_if_low_coverage(answer, chunks)
        assert "Low curriculum coverage" not in caplog.text

    def test_warning_on_low_overlap(self, caplog) -> None:
        import logging
        from app.generation.hallucination import warn_if_low_coverage
        chunks = [{"text": "mitochondria cell energy atp respiration glucose oxygen"}]
        answer = "Cats are mammals that drink water."
        with caplog.at_level(logging.WARNING, logger="app.generation.hallucination"):
            warn_if_low_coverage(answer, chunks)
        assert "Low curriculum coverage" in caplog.text

    def test_empty_answer_no_error(self) -> None:
        from app.generation.hallucination import warn_if_low_coverage
        warn_if_low_coverage("", [{"text": "some context"}])

    def test_empty_chunks_no_error(self) -> None:
        from app.generation.hallucination import warn_if_low_coverage
        warn_if_low_coverage("some answer", [])


def test_chat_result_structure() -> None:
    """Verify ChatResult TypedDict keys and contract."""
    res: ChatResult = {
        "type": "chat",
        "mode": "study",
        "answer": "Photosynthesis is the process...",
        "citations": [],
        "confidence": 0.85,
        "retrieved_chunks": [],
        "refused": False,
    }
    assert res["type"] == "chat"
    assert res["mode"] == "study"
    assert res["refused"] is False


def test_clean_chat_response_json_unwrapping() -> None:
    """Verify clean_chat_response strips JSON envelopes and unescapes newlines."""
    from app.generation.pipeline import clean_chat_response

    # Full JSON
    sample_json = '{\n  "answer": "Ohm\'s Law states that current is proportional to voltage.\\n\\nFormula: V=RI"\n}'
    cleaned = clean_chat_response(sample_json)
    assert cleaned.startswith("Ohm's Law states")
    assert "{" not in cleaned
    assert '"answer"' not in cleaned
    assert "\n\nFormula:" in cleaned
    assert "\\n" not in cleaned

    # Truncated JSON (ended before closing quote/brace)
    sample_truncated = '{"answer": "Ohm\'s Law is V=RI.\\n\\nIt applies to'
    cleaned_trunc = clean_chat_response(sample_truncated)
    assert cleaned_trunc == "Ohm's Law is V=RI.\n\nIt applies to"


def test_clean_chat_response_katex_artifacts() -> None:
    """Verify clean_chat_response repairs KaTeX/MathML scraping artifacts."""
    from app.generation.pipeline import clean_chat_response

    raw = "If we let \nV\nV be the voltage and \nI\nI be the current, \nV\n=\nR\nI\nV=RI"
    cleaned = clean_chat_response(raw)
    assert "$V$" in cleaned
    assert "$I$" in cleaned
    assert "$V=RI$" in cleaned
    assert "\nV\nV" not in cleaned


def test_stream_clean_tokens() -> None:
    """Verify _stream_clean_tokens filters JSON prefixes and unescapes newlines."""
    from app.generation.pipeline import _stream_clean_tokens

    # JSON wrapped stream
    json_stream = ["{", ' "answer"', ': "', "Hello", " student!\\n\\n", "Here is ", "Ohm's law:\"", "}"]
    output = "".join(_stream_clean_tokens(json_stream))
    assert output == "Hello student!\n\nHere is Ohm's law:"
    assert "{" not in output
    assert '"answer"' not in output

    # Plain text stream
    plain_stream = ["Hello", " student! ", "Ohm's ", "law is $V = IR$."]
    output_plain = "".join(_stream_clean_tokens(plain_stream))
    assert output_plain == "Hello student! Ohm's law is $V = IR$."

