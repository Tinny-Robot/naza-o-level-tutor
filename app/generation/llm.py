"""Offline Gemma 4 E4B LLM via llama.cpp (CPU-only singleton)."""

from __future__ import annotations

import atexit
import queue
import re
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar

from app.config import (
    CONTEXT_LENGTH,
    FLASH_ATTN,
    MAX_TOKENS,
    MODEL_NAME,
    MODEL_PATH,
    SWA_FULL,
    TEMPERATURE,
    THREADS,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

_llm_singleton: LlamaCppLLM | None = None

# llama.cpp GGUF handles are not safe across arbitrary FastAPI/anyio worker
# threads. Keep all Llama construct / tokenize / generate calls on one thread.
_LLM_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="naza-llama")
_T = TypeVar("_T")


def _run_on_llm_thread(fn: Callable[[], _T]) -> _T:
    """Run ``fn`` on the dedicated llama thread (inline if already there)."""
    if threading.current_thread().name.startswith("naza-llama"):
        return fn()
    return _LLM_EXECUTOR.submit(fn).result()


def _shutdown_llm_executor() -> None:
    _LLM_EXECUTOR.shutdown(wait=False)


atexit.register(_shutdown_llm_executor)

# Some models may emit visible reasoning / think blocks; strip globally.
_REASONING_BLOCK_RE = re.compile(
    r"<\s*(?:think|thinking|redacted_reasoning)\s*>"
    r".*?"
    r"<\s*/\s*(?:think|thinking|redacted_reasoning)\s*>",
    re.DOTALL | re.IGNORECASE,
)
_ORPHAN_REASONING_TAG_RE = re.compile(
    r"<\s*/?\s*(?:think|thinking|redacted_reasoning)\s*>",
    re.IGNORECASE,
)
# Gemma 4 optional thought channel (when thinking mode is enabled).
_GEMMA_THOUGHT_CHANNEL_RE = re.compile(
    r"<\|channel\|>\s*thought\b.*?<\|channel\|>",
    re.DOTALL | re.IGNORECASE,
)


def strip_reasoning(text: str) -> str:
    """Remove visible reasoning / think blocks from generated text."""
    if not text:
        return ""
    cleaned = _REASONING_BLOCK_RE.sub("", text)
    cleaned = _ORPHAN_REASONING_TAG_RE.sub("", cleaned)
    cleaned = _GEMMA_THOUGHT_CHANNEL_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Never surface em/en dashes in tutor output
    cleaned = cleaned.replace("\u2014", "-").replace("\u2013", "-")
    return cleaned.strip()


def build_llama_kwargs(
    *,
    model_path: str | Path,
    n_ctx: int = CONTEXT_LENGTH,
    n_threads: int = THREADS,
    flash_attn: bool = FLASH_ATTN,
    swa_full: bool = SWA_FULL,
    n_gpu_layers: int = 0,
    verbose: bool = False,
) -> dict[str, Any]:
    """Return kwargs for ``llama_cpp.Llama`` (CPU-only Gemma path)."""
    return {
        "model_path": str(model_path),
        "n_ctx": n_ctx,
        "n_threads": n_threads,
        "n_gpu_layers": n_gpu_layers,
        "verbose": verbose,
        "flash_attn": flash_attn,
        "swa_full": swa_full,
    }


class LLMClient(Protocol):
    """Minimal chat + tokenize interface used by the RAG pipeline."""

    def generate(self, system: str, user: str) -> str:
        """Return the assistant reply for a system + user prompt pair."""

    def count_tokens(self, text: str) -> int:
        """Return the number of tokens in ``text`` for the loaded model."""


class LlamaCppLLM:
    """Lazy-loaded llama.cpp wrapper for Gemma 4 E4B GGUF (CPU only)."""

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        n_ctx: int = CONTEXT_LENGTH,
        n_threads: int = THREADS,
        temperature: float = TEMPERATURE,
        max_tokens: int = MAX_TOKENS,
        model_name: str = MODEL_NAME,
        flash_attn: bool = FLASH_ATTN,
        swa_full: bool = SWA_FULL,
    ) -> None:
        path = MODEL_PATH if model_path is None else Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"GGUF model not found at {path}. "
                f"Place {MODEL_NAME} IQ3_M at MODEL_PATH before asking "
                "(run bash download_model.sh from the repository root). "
                "The app does not download model weights."
            )
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.last_gen_tokens: int = 0
        self.llama_kwargs = build_llama_kwargs(
            model_path=path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            flash_attn=flash_attn,
            swa_full=swa_full,
        )
        logger.info(
            "Loading %s from %s (n_ctx=%d, n_threads=%d, n_gpu_layers=0, "
            "flash_attn=%s, swa_full=%s)",
            model_name,
            path,
            n_ctx,
            n_threads,
            flash_attn,
            swa_full,
        )

        def _load() -> Any:
            from llama_cpp import Llama

            return Llama(**self.llama_kwargs)

        self._llama = _run_on_llm_thread(_load)

    def count_tokens(self, text: str) -> int:
        """Count tokens using the model's ``tokenize`` API (no heuristics)."""
        if not text:
            return 0

        def _count() -> int:
            tokens = self._llama.tokenize(text.encode("utf-8"), add_bos=False)
            return len(tokens)

        return _run_on_llm_thread(_count)

    def generate(self, system: str, user: str, *, max_tokens: int | None = None) -> str:
        """Chat completion via llama.cpp (GGUF chat template)."""
        logger.info("LLM request via llama.cpp model=%s", self.model_name)
        limit = max_tokens if max_tokens is not None else self.max_tokens

        def _generate() -> tuple[str, int]:
            response = self._llama.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_tokens=limit,
            )
            content = response["choices"][0]["message"]["content"]
            if not content:
                raise RuntimeError("llama.cpp returned an empty completion.")
            cleaned = strip_reasoning(content)
            usage = response.get("usage") or {}
            completion_tokens = usage.get("completion_tokens")
            if isinstance(completion_tokens, int) and completion_tokens > 0:
                gen_tokens = completion_tokens
            else:
                tokens = self._llama.tokenize(
                    cleaned.encode("utf-8"), add_bos=False
                )
                gen_tokens = len(tokens)
            if not cleaned:
                raise RuntimeError(
                    "llama.cpp completion was empty after stripping reasoning blocks."
                )
            return cleaned, gen_tokens

        cleaned, gen_tokens = _run_on_llm_thread(_generate)
        self.last_gen_tokens = gen_tokens
        return cleaned

    def stream_generate(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
    ) -> Generator[str, None, None]:
        """Stream token chunks from the llama thread via a queue bridge.

        Yields string token fragments as they are generated. Callers can wrap
        this in a FastAPI ``StreamingResponse`` for SSE.

        Architecture::

            llama thread (stream=True generator)
                ↓ puts tokens into
            threading.Queue
                ↑ drained by
            caller (FastAPI response generator)

        The ``_LLM_EXECUTOR`` (max_workers=1) still serializes all inference.
        """
        logger.info("LLM streaming request via llama.cpp model=%s", self.model_name)
        limit = max_tokens if max_tokens is not None else self.max_tokens
        # Sentinel: unique object signals end of stream; Exception instances signal errors.
        _SENTINEL = object()
        token_queue: queue.Queue[Any] = queue.Queue(maxsize=512)

        def _stream_on_llama_thread() -> None:
            try:
                for chunk in self._llama.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=self.temperature,
                    max_tokens=limit,
                    stream=True,
                ):
                    delta = chunk["choices"][0]["delta"].get("content", "") or ""
                    if delta:
                        token_queue.put(delta)
            except Exception as exc:  # noqa: BLE001
                logger.error("Streaming generation error: %s", exc)
                token_queue.put(exc)
            finally:
                token_queue.put(_SENTINEL)

        # Submit streaming task to the dedicated llama thread (non-blocking).
        _LLM_EXECUTOR.submit(_stream_on_llama_thread)

        # Drain the queue until the sentinel arrives.
        while True:
            item = token_queue.get()
            if item is _SENTINEL:
                break
            if isinstance(item, Exception):
                raise item
            yield item


def get_llm(force_reload: bool = False) -> LlamaCppLLM:
    """Return the process-wide LlamaCppLLM singleton."""
    global _llm_singleton
    if _llm_singleton is None or force_reload:
        _llm_singleton = LlamaCppLLM()
    return _llm_singleton


def reset_llm_singleton() -> None:
    """Clear the singleton (tests only)."""
    global _llm_singleton
    _llm_singleton = None
