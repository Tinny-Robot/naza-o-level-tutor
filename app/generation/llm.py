"""Offline Gemma 4 E4B LLM via llama.cpp (CPU-only singleton)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

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
        from llama_cpp import Llama

        kwargs = build_llama_kwargs(
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
        self._llama = Llama(**kwargs)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.last_gen_tokens: int = 0
        self.llama_kwargs = dict(kwargs)

    def count_tokens(self, text: str) -> int:
        """Count tokens using the model's ``tokenize`` API (no heuristics)."""
        if not text:
            return 0
        tokens = self._llama.tokenize(text.encode("utf-8"), add_bos=False)
        return len(tokens)

    def generate(self, system: str, user: str, *, max_tokens: int | None = None) -> str:
        """Chat completion via llama.cpp (GGUF chat template)."""
        logger.info("LLM request via llama.cpp model=%s", self.model_name)
        response = self._llama.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
        )
        content = response["choices"][0]["message"]["content"]
        if not content:
            self.last_gen_tokens = 0
            raise RuntimeError("llama.cpp returned an empty completion.")
        cleaned = strip_reasoning(content)
        usage = response.get("usage") or {}
        completion_tokens = usage.get("completion_tokens")
        if isinstance(completion_tokens, int) and completion_tokens > 0:
            self.last_gen_tokens = completion_tokens
        else:
            self.last_gen_tokens = self.count_tokens(cleaned)
        if not cleaned:
            raise RuntimeError(
                "llama.cpp completion was empty after stripping reasoning blocks."
            )
        return cleaned


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
