"""SVG sanitizer and fallback diagrams (no GGUF)."""

from app.lesson.diagram import fallback_diagram_svg, sanitize_svg
from app.lesson.lesson_formatter import fallback_lesson, format_lesson


def test_sanitize_keeps_simple_svg() -> None:
    raw = """
    <svg viewBox="0 0 640 360"><line x1="10" y1="10" x2="80" y2="80" stroke="#1C2740"/>
    <text x="20" y="40">Force</text></svg>
    """
    cleaned = sanitize_svg(raw)
    assert cleaned is not None
    assert "<svg" in cleaned
    assert "Force" in cleaned
    assert "line" in cleaned


def test_sanitize_drops_script() -> None:
    raw = '<svg viewBox="0 0 10 10"><script>alert(1)</script><rect width="10" height="10"/></svg>'
    cleaned = sanitize_svg(raw)
    assert cleaned is None or "<script" not in cleaned.lower()


def test_fallback_lesson_includes_diagram_svg() -> None:
    lesson = fallback_lesson(topic="Quadratic Equations")
    assert lesson.sections
    first = lesson.sections[0]
    assert first.diagram_placeholder
    assert first.diagram_svg
    assert first.diagram_svg.lstrip().startswith("<svg")
    assert "Quadratic" in first.diagram_svg or "sketch" in first.diagram_svg.lower()


def test_format_lesson_placeholder_gets_svg() -> None:
    lesson = format_lesson(
        {
            "title": "Types",
            "introduction": "Hello.",
            "objectives": ["One"],
            "sections": [
                {
                    "heading": "Question types",
                    "body": "Spot the type first.",
                    "diagram_placeholder": "Simple diagram for Identifying Question Types",
                }
            ],
            "practice": {"question": "Which is best?", "correct_answer": "A"},
        }
    )
    svg = lesson.sections[0].diagram_svg or ""
    assert svg.lstrip().startswith("<svg")
    assert "<script" not in svg.lower()


def test_fallback_diagram_svg_escapes() -> None:
    svg = fallback_diagram_svg('<b>bad</b>')
    assert "<b>" not in svg
    assert "&lt;b&gt;" in svg
