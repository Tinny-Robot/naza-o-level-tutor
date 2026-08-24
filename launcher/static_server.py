"""Loopback static file server with SPA fallback and /api reverse proxy."""

from __future__ import annotations

import argparse
import os
import sys
from http.client import HTTPConnection
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
ALL_INTERFACE_HOSTS = frozenset({"0.0.0.0", "::"})
DEFAULT_API = "http://127.0.0.1:8010"


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
    """Serve files from ``root``. Proxy ``/api`` to the local FastAPI. Unknown paths → index.html."""

    root: Path = Path(".").resolve()
    api_base: str = DEFAULT_API

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

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api"):
            self._proxy_api()
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api"):
            self._proxy_api()
            return
        self.send_error(405, "Method Not Allowed")

    def do_PUT(self) -> None:  # noqa: N802
        if self.path.startswith("/api"):
            self._proxy_api()
            return
        self.send_error(405, "Method Not Allowed")

    def do_PATCH(self) -> None:  # noqa: N802
        if self.path.startswith("/api"):
            self._proxy_api()
            return
        self.send_error(405, "Method Not Allowed")

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path.startswith("/api"):
            self._proxy_api()
            return
        self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self.path.startswith("/api"):
            self._proxy_api()
            return
        self.send_error(405, "Method Not Allowed")

    def _proxy_api(self) -> None:
        """Forward /api/* to FastAPI, stripping the /api prefix (same as Vite)."""
        parsed = urlparse(self.path)
        upstream_path = parsed.path[len("/api") :] or "/"
        if parsed.query:
            upstream_path = f"{upstream_path}?{parsed.query}"

        api = urlparse(self.api_base)
        host = api.hostname or "127.0.0.1"
        port = api.port or 8010
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else None

        headers: dict[str, str] = {}
        for key in ("Content-Type", "Accept", "Authorization"):
            val = self.headers.get(key)
            if val:
                headers[key] = val

        try:
            conn = HTTPConnection(host, port, timeout=600)
            conn.request(self.command, upstream_path, body=body, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
        except OSError:
            self.send_error(502, "API unavailable")
            return

        self.send_response(resp.status)
        hop_by_hop = {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }
        for key, value in resp.getheaders():
            if key.lower() in hop_by_hop:
                continue
            if key.lower() == "content-length":
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)
        try:
            conn.close()
        except Exception:
            pass

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def make_handler(root: Path, api_base: str) -> type[SpaRequestHandler]:
    resolved = Path(root).resolve()
    upstream = api_base

    class BoundHandler(SpaRequestHandler):
        root = resolved
        api_base = upstream

    return BoundHandler


def serve(
    host: str,
    port: int,
    root: Path,
    *,
    api_base: str = DEFAULT_API,
    allow_all_interfaces: bool | None = None,
) -> None:
    if allow_all_interfaces is None:
        allow_all_interfaces = _env_flag("NAZA_DOCKER")
    assert_bind_host(host, allow_all_interfaces=allow_all_interfaces)
    httpd = ThreadingHTTPServer((host, port), make_handler(root, api_base))
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve a built desktop UI on loopback.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5151)
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--api-base",
        default=os.getenv("NAZA_API_BASE", DEFAULT_API),
        help="Upstream FastAPI base (default http://127.0.0.1:8010)",
    )
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
        api_base=args.api_base,
        allow_all_interfaces=args.allow_all_interfaces,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
