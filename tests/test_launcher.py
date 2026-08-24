"""Unit tests for the desktop Application Manager (no Gemma warm-start)."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from app.utils.offline import SelfCheckItem, SelfCheckResult
from launcher.manager import (
    ApplicationManager,
    LauncherError,
    terminate_process_group,
    wait_for_health,
)


def _failing_self_check() -> SelfCheckResult:
    return SelfCheckResult(
        items=(
            SelfCheckItem("Gemma GGUF found", False, "missing.gguf"),
            SelfCheckItem("Embedding model found locally", True, "ok"),
            SelfCheckItem("FAISS index found", True, "ok"),
            SelfCheckItem("Prompt templates found", True, "ok"),
            SelfCheckItem("Offline mode enabled", True, "ok"),
        )
    )


def test_preflight_fails_when_self_check_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing GGUF (via monkeypatched self-check) fails preflight fast."""
    root = tmp_path
    (root / "scripts").mkdir()
    (root / "scripts" / "serve_api.py").write_text("# stub\n", encoding="utf-8")
    desktop = root / "desktop"
    desktop.mkdir()
    (desktop / "package.json").write_text("{}", encoding="utf-8")
    (desktop / "node_modules").mkdir()

    monkeypatch.setattr("launcher.manager.run_self_check", _failing_self_check)
    monkeypatch.setattr("launcher.manager.enable_offline_mode", lambda: None)
    monkeypatch.setattr("launcher.manager.shutil.which", lambda name: "/usr/bin/npm")

    manager = ApplicationManager(project_root=root, open_window=False)
    with pytest.raises(LauncherError, match="Offline preflight failed"):
        manager.preflight()


def _ok_self_check() -> SelfCheckResult:
    return SelfCheckResult(
        items=(
            SelfCheckItem("Gemma GGUF found", True, "ok"),
            SelfCheckItem("Embedding model found locally", True, "ok"),
            SelfCheckItem("FAISS index found", True, "ok"),
            SelfCheckItem("Prompt templates found", True, "ok"),
            SelfCheckItem("Offline mode enabled", True, "ok"),
        )
    )


def test_preflight_accepts_dist_without_npm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path
    (root / "scripts").mkdir()
    (root / "scripts" / "serve_api.py").write_text("# stub\n", encoding="utf-8")
    desktop = root / "desktop"
    desktop.mkdir()
    (desktop / "package.json").write_text("{}", encoding="utf-8")
    dist = desktop / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>built</html>", encoding="utf-8")

    monkeypatch.setattr("launcher.manager.run_self_check", _ok_self_check)
    monkeypatch.setattr("launcher.manager.enable_offline_mode", lambda: None)
    monkeypatch.setattr("launcher.manager.shutil.which", lambda name: None)

    ApplicationManager(project_root=root, open_window=False).preflight()


def test_static_server_spa_fallback(tmp_path: Path) -> None:
    from urllib.request import urlopen

    from launcher.static_server import make_handler

    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("<html>INDEX-SPA</html>", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("ASSET_JS", encoding="utf-8")

    server = HTTPServer(("127.0.0.1", 0), make_handler(root))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        spa = urlopen(f"http://{host}:{port}/learn", timeout=2).read().decode()
        assert "INDEX-SPA" in spa
        tutor = urlopen(f"http://{host}:{port}/tutor", timeout=2).read().decode()
        assert "INDEX-SPA" in tutor
        asset = urlopen(f"http://{host}:{port}/assets/app.js", timeout=2).read().decode()
        assert asset == "ASSET_JS"
    finally:
        server.shutdown()


def test_static_server_rejects_non_loopback() -> None:
    from launcher.static_server import assert_bind_host

    with pytest.raises(ValueError, match="loopback"):
        assert_bind_host("0.0.0.0")
    with pytest.raises(ValueError, match="loopback"):
        assert_bind_host("192.168.1.10", allow_all_interfaces=True)
    assert_bind_host("127.0.0.1")
    assert_bind_host("0.0.0.0", allow_all_interfaces=True)


def test_preflight_fails_when_gguf_missing_via_real_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Direct MODEL_PATH miss surfaces through run_self_check."""
    import app.utils.offline as offline_mod

    missing = tmp_path / "no-model.gguf"
    monkeypatch.setattr(offline_mod, "MODEL_PATH", missing)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    result = offline_mod.run_self_check()
    assert result.ok is False
    assert any(not item.ok and "GGUF" in item.label for item in result.items)

    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "serve_api.py").write_text("# stub\n", encoding="utf-8")
    (root / "desktop").mkdir()
    (root / "desktop" / "package.json").write_text("{}", encoding="utf-8")
    (root / "desktop" / "node_modules").mkdir()

    monkeypatch.setattr("launcher.manager.run_self_check", offline_mod.run_self_check)
    monkeypatch.setattr("launcher.manager.shutil.which", lambda name: "/usr/bin/npm")

    manager = ApplicationManager(project_root=root, open_window=False)
    with pytest.raises(LauncherError, match="Offline preflight failed"):
        manager.preflight()


class _HealthHandler(BaseHTTPRequestHandler):
    ready_after: float = 0.0
    started_at: float = 0.0

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        if time.monotonic() < self.started_at + self.ready_after:
            body = json.dumps({"status": "starting"}).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps({"status": "ok", "offline": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def _serve_health(*, ready_after: float = 0.0) -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), _HealthHandler)
    _HealthHandler.ready_after = ready_after
    _HealthHandler.started_at = time.monotonic()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/health"


def test_wait_for_health_success() -> None:
    server, url = _serve_health(ready_after=0.15)
    try:
        wait_for_health(url, timeout=5.0, poll_interval=0.05, progress_every=10.0)
    finally:
        server.shutdown()


def test_wait_for_health_timeout() -> None:
    server, url = _serve_health(ready_after=60.0)
    try:
        with pytest.raises(LauncherError, match="Timed out"):
            wait_for_health(url, timeout=0.35, poll_interval=0.05, progress_every=10.0)
    finally:
        server.shutdown()


def test_wait_for_health_detects_early_process_exit() -> None:
    proc = subprocess.Popen(  # noqa: S603,S607 - intentional short sleep
        ["sleep", "0.05"],
        start_new_session=True,
    )
    try:
        with pytest.raises(LauncherError, match="exited early"):
            wait_for_health(
                "http://127.0.0.1:9/health",
                timeout=5.0,
                poll_interval=0.05,
                process=proc,
            )
    finally:
        if proc.poll() is None:
            terminate_process_group(proc, wait_s=1.0)


def test_terminate_process_group_cleans_sleep_children() -> None:
    """Cleanup must kill a process-group leader (and not leave orphans)."""
    proc = subprocess.Popen(  # noqa: S603,S607 - intentional long sleep
        ["sleep", "60"],
        start_new_session=True,
    )
    assert proc.poll() is None
    terminate_process_group(proc, wait_s=2.0)
    assert proc.poll() is not None


def test_application_manager_cleanup_terminates_both() -> None:
    manager = ApplicationManager(project_root=Path.cwd(), open_window=False)
    api = subprocess.Popen(  # noqa: S603,S607
        ["sleep", "60"],
        start_new_session=True,
    )
    desktop = subprocess.Popen(  # noqa: S603,S607
        ["sleep", "60"],
        start_new_session=True,
    )
    manager._api = api
    manager._desktop = desktop
    manager.cleanup()
    assert api.poll() is not None
    assert desktop.poll() is not None
    assert manager._api is None
    assert manager._desktop is None
