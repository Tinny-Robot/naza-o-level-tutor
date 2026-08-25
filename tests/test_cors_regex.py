r"""CORS origin regex regression tests.

Verifies that the anchored regex:
  ^https?://(localhost|127\.0\.0\.1)(:\d+)?$

- Allows legitimate localhost origins
- Blocks subdomain/prefix bypass attacks
"""

from __future__ import annotations

import re

import pytest

# Import the regex directly from main to test the actual value.
from backend.api.main import _LOCAL_ORIGIN_RE

_RE = re.compile(_LOCAL_ORIGIN_RE)


def _matches(origin: str) -> bool:
    return bool(_RE.fullmatch(origin) or _RE.match(origin))


class TestCorsRegex:
    def test_http_localhost_allowed(self) -> None:
        assert _RE.fullmatch("http://localhost")

    def test_https_localhost_allowed(self) -> None:
        assert _RE.fullmatch("https://localhost")

    def test_localhost_with_port_allowed(self) -> None:
        assert _RE.fullmatch("http://localhost:3000")

    def test_localhost_port_5151_allowed(self) -> None:
        assert _RE.fullmatch("http://localhost:5151")

    def test_127_0_0_1_allowed(self) -> None:
        assert _RE.fullmatch("http://127.0.0.1")

    def test_127_0_0_1_with_port_allowed(self) -> None:
        assert _RE.fullmatch("http://127.0.0.1:8010")

    def test_localhost_evilsite_rejected(self) -> None:
        """http://localhost.evilsite.com must NOT match."""
        assert not _RE.fullmatch("http://localhost.evilsite.com")

    def test_127_evilsite_rejected(self) -> None:
        """http://127.0.0.1.evilsite.com must NOT match."""
        assert not _RE.fullmatch("http://127.0.0.1.evilsite.com")

    def test_evil_prefix_localhost_rejected(self) -> None:
        assert not _RE.fullmatch("http://evillocalhost.com")

    def test_ftp_scheme_rejected(self) -> None:
        assert not _RE.fullmatch("ftp://localhost")

    def test_empty_origin_rejected(self) -> None:
        assert not _RE.fullmatch("")

    def test_remote_ip_rejected(self) -> None:
        assert not _RE.fullmatch("http://192.168.1.1:8010")

    def test_regex_has_anchors(self) -> None:
        """The regex must have start and end anchors to prevent partial matching."""
        assert _LOCAL_ORIGIN_RE.startswith("^"), "Regex must start with ^"
        assert _LOCAL_ORIGIN_RE.endswith("$"), "Regex must end with $"
