"""Enforce and verify fully offline operation (no HF / cloud downloads)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.config import (
    EMBEDDING_MODEL_PATH,
    INDEX_PATH,
    MODEL_PATH,
    PROMPTS_DIR,
)


OFFLINE_ENV_KEYS: tuple[str, ...] = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")

_REQUIRED_PROMPTS: tuple[str, ...] = (
    "system.txt",
    "user.txt",
    "general_system.txt",
    "general_user.txt",
)

_EMBEDDING_MARKERS: tuple[str, ...] = (
    "config.json",
    "modules.json",
    "model.safetensors",
)


def enable_offline_mode() -> None:
    """Force Hugging Face / Transformers hubs to stay offline."""
    for key in OFFLINE_ENV_KEYS:
        os.environ[key] = "1"


def offline_mode_enabled() -> bool:
    """True when both offline env flags are set to a truthy value."""
    return all(os.environ.get(k, "").strip() in {"1", "true", "True", "yes"} for k in OFFLINE_ENV_KEYS)


def embedding_model_present(path: Path | None = None) -> bool:
    """Return True if ``path`` looks like a local SentenceTransformer snapshot."""
    root = Path(path) if path is not None else EMBEDDING_MODEL_PATH
    if not root.is_dir():
        return False
    return all((root / name).is_file() for name in _EMBEDDING_MARKERS)


def prompts_present(prompts_dir: Path | None = None) -> bool:
    """Return True when all study + general prompt templates exist."""
    root = Path(prompts_dir) if prompts_dir is not None else PROMPTS_DIR
    return all((root / name).is_file() for name in _REQUIRED_PROMPTS)


@dataclass(frozen=True)
class SelfCheckItem:
    """One startup self-check row."""

    label: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class SelfCheckResult:
    """Aggregate offline readiness checks for the tutor CLI."""

    items: tuple[SelfCheckItem, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)

    def format_lines(self) -> list[str]:
        lines: list[str] = ["Startup self-check"]
        for item in self.items:
            mark = "✓" if item.ok else "✗"
            suffix = f" ({item.detail})" if item.detail else ""
            lines.append(f"{mark} {item.label}{suffix}")
        return lines


def run_self_check() -> SelfCheckResult:
    """Verify GGUF, local embeddings, FAISS, prompts, and offline env flags."""
    items = (
        SelfCheckItem(
            "Gemma GGUF found",
            MODEL_PATH.is_file(),
            str(MODEL_PATH),
        ),
        SelfCheckItem(
            "Embedding model found locally",
            embedding_model_present(),
            str(EMBEDDING_MODEL_PATH),
        ),
        SelfCheckItem(
            "FAISS index found",
            INDEX_PATH.is_file(),
            str(INDEX_PATH),
        ),
        SelfCheckItem(
            "Prompt templates found",
            prompts_present(),
            str(PROMPTS_DIR),
        ),
        SelfCheckItem(
            "Offline mode enabled",
            offline_mode_enabled(),
            "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
        ),
    )
    return SelfCheckResult(items=items)


def missing_embedding_instructions(path: Path | None = None) -> str:
    """Human-readable offline placement instructions for the embedder."""
    root = Path(path) if path is not None else EMBEDDING_MODEL_PATH
    return (
        f"Embedding model not found at {root}. "
        "Place a local SentenceTransformer snapshot offline "
        "(e.g. copy or symlink the cached KEmbed-naija-v3 snapshot into "
        "`models/embeddings/KEmbed-naija-v3`). "
        "Required files include config.json, modules.json, and model.safetensors. "
        "The app never downloads from Hugging Face."
    )
