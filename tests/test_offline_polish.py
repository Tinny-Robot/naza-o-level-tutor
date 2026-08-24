"""Unit tests for strip_reasoning and offline embedding path wiring."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.generation.llm import strip_reasoning
from app.utils.offline import (
    embedding_model_present,
    enable_offline_mode,
    missing_embedding_instructions,
    run_self_check,
)


def _tag(name: str, body: str = "") -> str:
    """Build XML-ish tags without embedding literal think markers in source."""
    return f"<{name}>{body}</{name}>"


def test_strip_reasoning_removes_think_block() -> None:
    block = _tag("think", "secret chain of thought\nstep 2")
    text = f"{block}\nFinal answer: Ohm's law is V = IR."
    assert strip_reasoning(text) == "Final answer: Ohm's law is V = IR."


def test_strip_reasoning_empty_think_block() -> None:
    empty = _tag("think", "\n\n")
    assert strip_reasoning(f"{empty}Visible answer") == "Visible answer"


def test_strip_reasoning_thinking_and_orphans() -> None:
    body = _tag("thinking", "scratch") + "Answer"
    assert strip_reasoning(body) == "Answer"
    open_only = "<" + "think" + ">" + "partial"
    assert strip_reasoning(open_only) == "partial"


def test_strip_reasoning_redacted_style() -> None:
    block = _tag("redacted_reasoning", "hidden")
    assert strip_reasoning(f"{block}\nDone.") == "Done."


def test_strip_reasoning_gemma_thought_channel() -> None:
    text = (
        "<|channel|>thought\nscratch pad here\n<|channel|>"
        "Final answer: force equals mass times acceleration."
    )
    assert strip_reasoning(text) == (
        "Final answer: force equals mass times acceleration."
    )


def test_enable_offline_mode_sets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    enable_offline_mode()
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_embedding_model_present_false_for_missing(tmp_path: Path) -> None:
    assert embedding_model_present(tmp_path / "missing") is False
    msg = missing_embedding_instructions(tmp_path / "missing")
    assert "never downloads" in msg.lower()


def test_embedder_raises_when_path_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.ingestion.embedder as embedder_module

    embedder_module.reset_embedder_singleton()
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    missing = tmp_path / "no-model"
    with pytest.raises(FileNotFoundError, match="never downloads"):
        emb = embedder_module.Embedder(model_name=missing)
        _ = emb.model


def test_embedder_loads_with_local_files_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure SentenceTransformer is constructed with local_files_only=True."""
    import app.ingestion.embedder as embedder_module

    embedder_module.reset_embedder_singleton()
    model_dir = tmp_path / "KEmbed"
    model_dir.mkdir()
    for name in ("config.json", "modules.json", "model.safetensors"):
        (model_dir / name).write_text("{}", encoding="utf-8")

    captured: dict[str, object] = {}

    class FakeST:
        def __init__(self, path: str, local_files_only: bool = False, **_: object) -> None:
            captured["path"] = path
            captured["local_files_only"] = local_files_only

        def encode(self, texts: list[str], **__: object):
            import numpy as np

            return np.zeros((len(texts), 4), dtype=np.float32)

    class FakeSTModule:
        SentenceTransformer = FakeST

    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", FakeSTModule)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    emb = embedder_module.Embedder(model_name=model_dir)
    _ = emb.model
    assert captured["local_files_only"] is True
    assert Path(str(captured["path"])).resolve() == model_dir.resolve()


@pytest.mark.skipif(
    not embedding_model_present(),
    reason="Local KEmbed snapshot not present under EMBEDDING_MODEL_PATH",
)
def test_real_embedder_offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration: load real local embedder with HF hub offline flags."""
    import app.ingestion.embedder as embedder_module
    from app.config import EMBEDDING_MODEL_PATH

    embedder_module.reset_embedder_singleton()
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    enable_offline_mode()

    emb = embedder_module.Embedder(model_name=EMBEDDING_MODEL_PATH)
    vector = emb.embed_query("subject verb concord")
    assert vector.ndim == 2
    assert vector.shape[0] == 1
    assert vector.shape[1] > 0


def test_self_check_reports_offline_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    enable_offline_mode()
    result = run_self_check()
    offline_item = next(i for i in result.items if i.label.startswith("Offline"))
    assert offline_item.ok is True
    lines = "\n".join(result.format_lines())
    assert "✓" in lines
