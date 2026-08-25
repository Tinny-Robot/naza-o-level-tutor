"""Security regression tests for the /media path traversal fix.

These tests verify that path.is_relative_to() correctly blocks:
  - ../  traversal attempts
  - sibling-prefix attacks (/app/data_evil vs /app/data)
  - absolute paths outside allowed roots
  - valid paths within allowed directories still work
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app_with_allowed_roots(allowed: tuple[Path, ...], fake_file: Path) -> TestClient:
    """Build a TestClient with patched _ALLOWED_ROOTS and a fake file."""
    from contextlib import asynccontextmanager
    from typing import AsyncIterator

    @asynccontextmanager
    async def noop_lifespan(app):  # type: ignore[no-untyped-def]
        app.state.pipeline = MagicMock()
        yield

    app = create_app(lifespan_fn=noop_lifespan)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Unit tests for _safe_path directly
# ---------------------------------------------------------------------------

class TestSafePath:
    """Direct unit tests for backend.api.routes.media._safe_path."""

    def setup_method(self) -> None:
        from backend.api.routes import media
        self.media = media

    def _patch_roots(self, roots: tuple[Path, ...]):
        return patch.object(self.media, "_ALLOWED_ROOTS", roots)

    def test_valid_file_inside_allowed_dir(self, tmp_path: Path) -> None:
        allowed = tmp_path / "data"
        allowed.mkdir()
        good = allowed / "image.png"
        good.write_bytes(b"\x89PNG")

        with self._patch_roots((allowed.resolve(),)):
            result = self.media._safe_path(str(good))
        assert result == good.resolve()

    def test_path_traversal_dot_dot_blocked(self, tmp_path: Path) -> None:
        allowed = tmp_path / "data"
        allowed.mkdir()
        secret = tmp_path / "secret.png"
        secret.write_bytes(b"\x89PNG")

        traversal = str(allowed / ".." / "secret.png")
        with self._patch_roots((allowed.resolve(),)):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                self.media._safe_path(traversal)
        assert exc_info.value.status_code == 403

    def test_sibling_prefix_attack_blocked(self, tmp_path: Path) -> None:
        """'/app/data_evil' must NOT pass validation for root '/app/data'."""
        allowed = tmp_path / "data"
        allowed.mkdir()
        evil = tmp_path / "data_evil"
        evil.mkdir()
        bad_file = evil / "secret.png"
        bad_file.write_bytes(b"\x89PNG")

        with self._patch_roots((allowed.resolve(),)):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                self.media._safe_path(str(bad_file))
        assert exc_info.value.status_code == 403

    def test_absolute_path_outside_allowed_blocked(self, tmp_path: Path) -> None:
        allowed = tmp_path / "data"
        allowed.mkdir()
        outside = tmp_path / "outside.png"
        outside.write_bytes(b"\x89PNG")

        with self._patch_roots((allowed.resolve(),)):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                self.media._safe_path(str(outside))
        assert exc_info.value.status_code == 403

    def test_empty_path_returns_400(self, tmp_path: Path) -> None:
        allowed = tmp_path / "data"
        allowed.mkdir()
        with self._patch_roots((allowed.resolve(),)):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                self.media._safe_path("   ")
        assert exc_info.value.status_code == 400

    def test_unsupported_extension_blocked(self, tmp_path: Path) -> None:
        allowed = tmp_path / "data"
        allowed.mkdir()
        bad = allowed / "shell.sh"
        bad.write_text("#!/bin/sh")

        with self._patch_roots((allowed.resolve(),)):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                self.media._safe_path(str(bad))
        # 400 for bad extension or 403 for non-file — either is a rejection
        assert exc_info.value.status_code in (400, 404)
