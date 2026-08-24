"""Sanitize and generate simple lesson SVGs."""

from __future__ import annotations

import html
import re
from typing import Any
from xml.etree import ElementTree as ET

from app.utils.logging import get_logger

logger = get_logger(__name__)

_SVG_RE = re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE)
_EVENT_ATTR_RE = re.compile(r"^on", re.IGNORECASE)

_ALLOWED_TAGS = {
    "svg",
    "g",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "path",
    "text",
    "tspan",
    "title",
}
_ALLOWED_ATTRS = {
    "viewbox",
    "xmlns",
    "x",
    "y",
    "width",
    "height",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "x1",
    "y1",
    "x2",
    "y2",
    "points",
    "d",
    "fill",
    "stroke",
    "stroke-width",
    "strokewidth",
    "font-size",
    "fontsize",
    "font-family",
    "fontfamily",
    "text-anchor",
    "textanchor",
    "transform",
    "opacity",
}


def fallback_diagram_svg(caption: str) -> str:
    """Simple labelled boxes when the model cannot draw."""
    label = html.escape((caption or "Diagram").strip()[:80] or "Diagram")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360">'
        '<rect width="640" height="360" fill="#FFF8E8"/>'
        '<rect x="40" y="40" width="560" height="280" rx="16" fill="#FBF3DD" '
        'stroke="#1C2740" stroke-width="2"/>'
        '<circle cx="120" cy="180" r="36" fill="#D39212"/>'
        '<text x="180" y="170" fill="#1C2740" font-size="18" '
        'font-family="Outfit, sans-serif">Naza\'s sketch</text>'
        f'<text x="180" y="204" fill="#4A4038" font-size="14" '
        f'font-family="Outfit, sans-serif">{label}</text>'
        "</svg>"
    )


def sanitize_svg(raw: str | None) -> str | None:
    """Keep a tiny SVG subset. Drop scripts, events, and foreignObject."""
    if not raw:
        return None
    match = _SVG_RE.search(raw)
    if not match:
        return None
    blob = match.group(0)
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return None
    tag = root.tag.split("}")[-1].lower()
    if tag != "svg":
        return None
    cleaned = _clean_node(root)
    if cleaned is None:
        return None
    if "viewBox" not in cleaned.attrib and "viewbox" not in {
        k.lower() for k in cleaned.attrib
    }:
        cleaned.set("viewBox", "0 0 640 360")
    cleaned.set("xmlns", "http://www.w3.org/2000/svg")
    xml = ET.tostring(cleaned, encoding="unicode")
    if "<script" in xml.lower() or "javascript:" in xml.lower():
        return None
    return xml


def _clean_node(node: ET.Element) -> ET.Element | None:
    tag = node.tag.split("}")[-1].lower()
    if tag not in _ALLOWED_TAGS:
        return None
    out = ET.Element(tag)
    for key, value in node.attrib.items():
        attr = key.split("}")[-1]
        low = attr.lower()
        if _EVENT_ATTR_RE.match(low):
            continue
        if low not in _ALLOWED_ATTRS:
            continue
        text = str(value)
        if "javascript:" in text.lower() or "data:" in text.lower():
            continue
        out.set("viewBox" if low == "viewbox" else attr, text)
    if node.text and tag in {"text", "tspan", "title"}:
        out.text = node.text
    for child in list(node):
        cleaned = _clean_node(child)
        if cleaned is not None:
            out.append(cleaned)
    if node.tail:
        out.tail = node.tail
    return out


def generate_diagram_svg(llm: Any, caption: str) -> str:
    """LLM SVG if possible, else a labelled fallback."""
    caption = (caption or "").strip() or "Lesson diagram"
    fallback = fallback_diagram_svg(caption)
    generate = getattr(llm, "generate", None)
    if not callable(generate):
        return fallback
    try:
        from app.config import PROMPTS_DIR

        system = (PROMPTS_DIR / "diagram_svg.txt").read_text(encoding="utf-8")
    except Exception:
        system = "Return only a simple <svg viewBox='0 0 640 360'> diagram."
    user = f"Diagram to draw: {caption}"
    try:
        try:
            raw = generate(system, user, max_tokens=800)
        except TypeError:
            raw = generate(system, user)
    except Exception:
        logger.exception("Diagram SVG generate failed")
        return fallback
    cleaned = sanitize_svg(raw)
    return cleaned or fallback
