"""Loopback static file server with SPA fallback to index.html."""

from __future__ import annotations

import argparse
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
ALL_INTERFACE_HOSTS = frozenset({"0.0.0.0", "::"})


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def assert_bind_host(host: str, *, allow_all_interfaces: bool = False) -> None:
    """Reject non-loopback binds unless Docker explicitly opts in."""
    if host in LOOPBACK_HOSTS:
        return
    if allow_all_interfaces and host in ALL_INTERFACE_HOSTS:
        return
    raise ValueError("Static UI must bind to loopback only (127.0.0.1).")


class SpaRequestHandler(SimpleHTTPRequestHandler):
    """Serve files from ``root``. Unknown paths return ``index.html``."""

    root: Path = Path(".").resolve()

    def translate_path(self, path: str) -> str:  # noqa: D401 - http.server API
        parsed = urlparse(path)
        rel = unquote(parsed.path).lstrip("/")
        candidate = (self.root / rel).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            return str(self.root / "index.html")
        if candidate.is_file():
            return str(candidate)
        return str(self.root / "index.html")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def make_handler(root: Path) -> type[SpaRequestHandler]:
    resolved = Path(root).resolve()

    class BoundHandler(SpaRequestHandler):
        root = resolved

    return BoundHandler


def serve(
    host: str,
    port: int,
    root: Path,
    *,
    allow_all_interfaces: bool | None = None,
) -> None:
    if allow_all_interfaces is None:
        allow_all_interfaces = _env_flag("NAZA_DOCKER")
    assert_bind_host(host, allow_all_interfaces=allow_all_interfaces)
    httpd = ThreadingHTTPServer((host, port), make_handler(root))
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve a built desktop UI on loopback.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5151)
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--allow-all-interfaces",
        action="store_true",
        help="Allow 0.0.0.0 (container publish only). Default is loopback.",
    )
    args = parser.parse_args(argv)
    serve(
        args.host,
        args.port,
        Path(args.root),
        allow_all_interfaces=args.allow_all_interfaces,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
