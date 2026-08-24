"""Unit tests for RSS helpers and llama.cpp kwargs wiring (no GGUF load)."""

from __future__ import annotations

from pathlib import Path

from app.config import FLASH_ATTN, SWA_FULL
from app.generation.llm import build_llama_kwargs
from app.utils.runtime import RssStageLogger, peak_rss_mb, rss_mb


def test_rss_mb_positive() -> None:
    assert rss_mb() > 0
    assert peak_rss_mb() > 0


def test_rss_stage_logger_deltas() -> None:
    lines: list[str] = []
    log = RssStageLogger(printer=lines.append)
    a = log.mark("start")
    b = log.mark("next")
    assert a.name == "start"
    assert b.delta_mb == b.rss_mb - a.rss_mb
    table = log.summary_table()
    assert "start" in table
    assert "next" in table
    assert lines and lines[0].startswith("[rss] start:")


def test_build_llama_kwargs_defaults() -> None:
    kwargs = build_llama_kwargs(model_path=Path("models/fake.gguf"))
    assert kwargs["model_path"].endswith("fake.gguf")
    assert kwargs["n_gpu_layers"] == 0
    assert kwargs["verbose"] is False
    assert kwargs["flash_attn"] is FLASH_ATTN
    assert kwargs["swa_full"] is SWA_FULL
    # Profiled production defaults: FA on, full SWA off.
    assert kwargs["flash_attn"] is True
    assert kwargs["swa_full"] is False


def test_build_llama_kwargs_overrides() -> None:
    kwargs = build_llama_kwargs(
        model_path="x.gguf",
        n_ctx=2048,
        n_threads=3,
        flash_attn=False,
        swa_full=True,
    )
    assert kwargs == {
        "model_path": "x.gguf",
        "n_ctx": 2048,
        "n_threads": 3,
        "n_gpu_layers": 0,
        "verbose": False,
        "flash_attn": False,
        "swa_full": True,
    }
