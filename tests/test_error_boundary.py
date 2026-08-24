"""Tiny ErrorBoundary contract: a child throw must offer Reload / Go home."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "desktop" / "src" / "components" / "layout" / "ErrorBoundary.tsx"
APP = ROOT / "desktop" / "src" / "App.tsx"


def test_error_boundary_fallback_has_reload_and_go_home() -> None:
    src = BOUNDARY.read_text(encoding="utf-8")
    assert "Reload" in src
    assert "Go home" in src
    assert "getDerivedStateFromError" in src
    app = APP.read_text(encoding="utf-8")
    assert "ErrorBoundary" in app
    assert "<ErrorBoundary>" in app
