"""Professional site chrome: icons, manifest, and no leftover Vite favicon."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
INDEX = DESKTOP / "index.html"
PUBLIC = DESKTOP / "public"


def test_index_html_has_product_icons_and_metadata() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert "vite.svg" not in html
    assert 'rel="icon" href="/favicon.svg"' in html or 'href="/favicon.svg"' in html
    assert 'rel="apple-touch-icon"' in html
    assert 'rel="manifest"' in html
    assert 'name="theme-color"' in html
    assert 'property="og:image"' in html
    assert 'name="description"' in html
    assert "Naza" in html


def test_public_icon_set_exists() -> None:
    required = [
        PUBLIC / "favicon.svg",
        PUBLIC / "favicon.ico",
        PUBLIC / "apple-touch-icon.png",
        PUBLIC / "og-image.png",
        PUBLIC / "site.webmanifest",
        PUBLIC / "safari-pinned-tab.svg",
        PUBLIC / "icons" / "icon-192.png",
        PUBLIC / "icons" / "icon-512.png",
        PUBLIC / "icons" / "maskable-512.png",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert missing == []


def test_webmanifest_names_naza() -> None:
    manifest = (PUBLIC / "site.webmanifest").read_text(encoding="utf-8")
    assert '"short_name": "Naza"' in manifest
    assert "icon-512.png" in manifest
