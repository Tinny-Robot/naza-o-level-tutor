"""Application Manager: offline preflight, FastAPI IPC, Vite UI, supervision."""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import IO, Any
from urllib.error import URLError
from urllib.request import urlopen

from app.utils.offline import enable_offline_mode, run_self_check

API_HOST = "127.0.0.1"
API_PORT = 8010
API_HEALTH_URL = f"http://{API_HOST}:{API_PORT}/health"
HEALTH_TIMEOUT_S = 600.0
HEALTH_POLL_INTERVAL_S = 1.0

VITE_HOST = "127.0.0.1"
VITE_PORT = 5151
VITE_URL = f"http://{VITE_HOST}:{VITE_PORT}"
VITE_TIMEOUT_S = 120.0
VITE_POLL_INTERVAL_S = 0.5

CLEANUP_WAIT_S = 5.0
SUPERVISE_POLL_S = 0.5

BROWSER_CANDIDATES: tuple[str, ...] = (
    "chromium",
    "google-chrome",
    "chromium-browser",
    "google-chrome-stable",
)


class LauncherError(RuntimeError):
    """Raised when the launcher cannot start or supervise the app."""


def resolve_project_root(start: Path | None = None) -> Path:
    """Return the project root (parent of ``launcher/``)."""
    if start is not None:
        return Path(start).resolve()
    return Path(__file__).resolve().parent.parent


def resolve_python(project_root: Path) -> Path:
    """Prefer ``.venv/bin/python``, else the current interpreter."""
    venv_python = project_root / ".venv" / "bin" / "python"
    if venv_python.is_file() and os.access(venv_python, os.X_OK):
        return venv_python
    return Path(sys.executable)


def health_status_ok(url: str = API_HEALTH_URL, *, timeout: float = 2.0) -> bool:
    """Return True when ``GET url`` yields JSON with ``status == "ok"``."""
    try:
        with urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("status") == "ok"


def http_responds(url: str, *, timeout: float = 2.0) -> bool:
    """Return True when ``url`` returns any HTTP response."""
    try:
        with urlopen(url, timeout=timeout) as resp:
            resp.read(1)
        return True
    except (URLError, TimeoutError, OSError):
        return False


def wait_for_health(
    url: str = API_HEALTH_URL,
    *,
    timeout: float = HEALTH_TIMEOUT_S,
    poll_interval: float = HEALTH_POLL_INTERVAL_S,
    process: subprocess.Popen[Any] | None = None,
    progress_every: float = 10.0,
    log_stream: IO[str] | None = None,
) -> None:
    """Poll ``/health`` until ``status == ok`` or fail on timeout / early exit."""
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    last_progress = started
    print(f"Waiting for API health at {url} (timeout {timeout:.0f}s)...", flush=True)

    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            detail = _read_log_tail(log_stream)
            raise LauncherError(
                f"API process exited early with code {process.returncode}."
                + (f"\n--- process output ---\n{detail}" if detail else "")
            )
        if health_status_ok(url):
            elapsed = time.monotonic() - started
            print(f"API ready after {elapsed:.1f}s.", flush=True)
            return
        now = time.monotonic()
        if now - last_progress >= progress_every:
            print(f"  still waiting for /health ({now - started:.0f}s)...", flush=True)
            last_progress = now
        time.sleep(poll_interval)

    detail = _read_log_tail(log_stream)
    raise LauncherError(
        f"Timed out after {timeout:.0f}s waiting for {url}."
        + (f"\n--- process output ---\n{detail}" if detail else "")
    )


def wait_for_http(
    url: str,
    *,
    timeout: float = VITE_TIMEOUT_S,
    poll_interval: float = VITE_POLL_INTERVAL_S,
    process: subprocess.Popen[Any] | None = None,
    label: str = "service",
    log_stream: IO[str] | None = None,
) -> None:
    """Poll until ``url`` responds or fail on timeout / early process exit."""
    deadline = time.monotonic() + timeout
    print(f"Waiting for {label} at {url}...", flush=True)
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            detail = _read_log_tail(log_stream)
            raise LauncherError(
                f"{label} process exited early with code {process.returncode}."
                + (f"\n--- process output ---\n{detail}" if detail else "")
            )
        if http_responds(url):
            print(f"{label} ready.", flush=True)
            return
        time.sleep(poll_interval)
    detail = _read_log_tail(log_stream)
    raise LauncherError(
        f"Timed out after {timeout:.0f}s waiting for {label} at {url}."
        + (f"\n--- process output ---\n{detail}" if detail else "")
    )


def terminate_process_group(
    proc: subprocess.Popen[Any] | None,
    *,
    wait_s: float = CLEANUP_WAIT_S,
) -> None:
    """Send SIGTERM to a process group, then SIGKILL if needed."""
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=wait_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass


def find_chromium() -> str | None:
    """Return the first available Chromium/Chrome binary on PATH."""
    for name in BROWSER_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def open_app_window(url: str) -> None:
    """Open ``url`` in Chromium ``--app`` mode, else the default browser."""
    browser = find_chromium()
    if browser:
        print(f"Opening app window via {browser}...", flush=True)
        subprocess.Popen(  # noqa: S603 - trusted local browser binary
            [browser, f"--app={url}", "--window-size=1280,800"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return
    print("Chromium/Chrome not found; opening default browser...", flush=True)
    webbrowser.open(url)


def _read_log_tail(log_stream: IO[str] | None, *, max_chars: int = 4000) -> str:
    if log_stream is None:
        return ""
    try:
        log_stream.flush()
        log_stream.seek(0)
        text = log_stream.read()
    except OSError:
        return ""
    if len(text) > max_chars:
        return text[-max_chars:]
    return text


class ApplicationManager:
    """Orchestrate offline preflight, FastAPI IPC, Vite desktop, and cleanup."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        open_window: bool = True,
        health_timeout: float = HEALTH_TIMEOUT_S,
        vite_timeout: float = VITE_TIMEOUT_S,
    ) -> None:
        self.project_root = resolve_project_root(project_root)
        self.open_window = open_window
        self.health_timeout = health_timeout
        self.vite_timeout = vite_timeout
        self.python = resolve_python(self.project_root)
        self._api: subprocess.Popen[Any] | None = None
        self._desktop: subprocess.Popen[Any] | None = None
        self._api_log: IO[str] | None = None
        self._desktop_log: IO[str] | None = None
        self._shutdown_requested = False

    def preflight(self) -> None:
        """Enable offline mode and fail fast if required assets are missing."""
        enable_offline_mode()
        result = run_self_check()
        for line in result.format_lines():
            print(line, flush=True)
        if not result.ok:
            failed = [item.label for item in result.items if not item.ok]
            raise LauncherError(
                "Offline preflight failed. Missing or invalid: "
                + ", ".join(failed)
                + ". Place GGUF, embedding snapshot, and FAISS index as documented in README.md."
            )

        serve_api = self.project_root / "scripts" / "serve_api.py"
        package_json = self.project_root / "desktop" / "package.json"
        if not serve_api.is_file():
            raise LauncherError(f"Missing API entry script: {serve_api}")
        if not package_json.is_file():
            raise LauncherError(f"Missing desktop package.json: {package_json}")
        dist_index = self.project_root / "desktop" / "dist" / "index.html"
        if dist_index.is_file():
            return
        if shutil.which("npm") is None:
            raise LauncherError(
                "npm is not on PATH. Install Node.js/npm, then run "
                "`npm install` inside desktop/, or build with `npm run build`."
            )
        node_modules = self.project_root / "desktop" / "node_modules"
        if not node_modules.is_dir():
            raise LauncherError(
                f"Missing {node_modules}. Run `npm install` inside desktop/ first."
            )

    def start_api(self) -> subprocess.Popen[Any]:
        """Start FastAPI via ``scripts/serve_api.py`` in a new process group."""
        script = self.project_root / "scripts" / "serve_api.py"
        env = os.environ.copy()
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        self._api_log = open(  # noqa: SIM115 - kept open for child lifetime
            self.project_root / ".launcher-api.log",
            "w+",
            encoding="utf-8",
        )
        print(f"Starting FastAPI IPC with {self.python} {script}...", flush=True)
        self._api = subprocess.Popen(  # noqa: S603 - fixed local script path
            [str(self.python), str(script)],
            cwd=str(self.project_root),
            env=env,
            stdout=self._api_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return self._api

    def start_desktop(self) -> subprocess.Popen[Any]:
        """Start the production dist UI, or Vite when dist is missing."""
        desktop_dir = self.project_root / "desktop"
        dist_index = desktop_dir / "dist" / "index.html"
        self._desktop_log = open(  # noqa: SIM115 - kept open for child lifetime
            self.project_root / ".launcher-desktop.log",
            "w+",
            encoding="utf-8",
        )
        if dist_index.is_file():
            cmd = [
                str(self.python),
                "-m",
                "launcher.static_server",
                "--host",
                VITE_HOST,
                "--port",
                str(VITE_PORT),
                "--root",
                str(dist_index.parent),
            ]
            print(
                f"Starting production desktop UI from {dist_index.parent}...",
                flush=True,
            )
            self._desktop = subprocess.Popen(  # noqa: S603 - local python module
                cmd,
                cwd=str(self.project_root),
                stdout=self._desktop_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            return self._desktop
        npm = shutil.which("npm")
        if npm is None:
            raise LauncherError("npm is not on PATH.")
        cmd = [
            npm,
            "run",
            "dev",
            "--",
            "--host",
            VITE_HOST,
            "--port",
            str(VITE_PORT),
            "--strictPort",
        ]
        print(f"Starting desktop UI in {desktop_dir}...", flush=True)
        self._desktop = subprocess.Popen(  # noqa: S603 - npm from PATH
            cmd,
            cwd=str(desktop_dir),
            stdout=self._desktop_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return self._desktop

    def cleanup(self) -> None:
        """Terminate API and desktop process groups; close log handles."""
        desktop = self._desktop
        api = self._api
        self._desktop = None
        self._api = None
        if desktop is not None:
            print("Stopping desktop...", flush=True)
            terminate_process_group(desktop)
        if api is not None:
            print("Stopping API...", flush=True)
            terminate_process_group(api)
        for stream in (self._api_log, self._desktop_log):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        self._api_log = None
        self._desktop_log = None

    def supervise(self) -> int:
        """Monitor children until one exits or a shutdown signal arrives."""
        assert self._api is not None
        assert self._desktop is not None
        print(
            "App running. Close the desktop window or press Ctrl+C to stop.",
            flush=True,
        )
        while not self._shutdown_requested:
            api_code = self._api.poll()
            desk_code = self._desktop.poll()
            if api_code is not None:
                print(
                    f"API process exited (code {api_code}); shutting down desktop.",
                    file=sys.stderr,
                    flush=True,
                )
                detail = _read_log_tail(self._api_log)
                if detail:
                    print(detail, file=sys.stderr, flush=True)
                return 1 if api_code == 0 else api_code
            if desk_code is not None:
                print(
                    f"Desktop process exited (code {desk_code}); shutting down API.",
                    flush=True,
                )
                return 0 if desk_code == 0 else desk_code
            time.sleep(SUPERVISE_POLL_S)
        return 0

    def _on_signal(self, signum: int, _frame: Any) -> None:
        self._shutdown_requested = True
        print(f"\nReceived signal {signum}; shutting down...", flush=True)

    def run(self) -> int:
        """Full launch sequence; always attempts cleanup."""
        previous_sigint = signal.signal(signal.SIGINT, self._on_signal)
        previous_sigterm = signal.signal(signal.SIGTERM, self._on_signal)
        exit_code = 1
        try:
            self.preflight()
            self.start_api()
            wait_for_health(
                API_HEALTH_URL,
                timeout=self.health_timeout,
                process=self._api,
                log_stream=self._api_log,
            )
            self.start_desktop()
            wait_for_http(
                VITE_URL,
                timeout=self.vite_timeout,
                process=self._desktop,
                label="desktop UI",
                log_stream=self._desktop_log,
            )
            if self.open_window:
                open_app_window(VITE_URL)
            else:
                print(f"--no-window: UI available at {VITE_URL}", flush=True)
            exit_code = self.supervise()
        except LauncherError as exc:
            print(f"Launcher error: {exc}", file=sys.stderr, flush=True)
            exit_code = 1
        except KeyboardInterrupt:
            print("\nInterrupted.", flush=True)
            exit_code = 130
        finally:
            self.cleanup()
            signal.signal(signal.SIGINT, previous_sigint)
            signal.signal(signal.SIGTERM, previous_sigterm)
        return exit_code
