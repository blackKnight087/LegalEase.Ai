"""Web Intel answer body must not show raw grounding redirect URLs."""
from __future__ import annotations

from backend.app.core.web_answer_cleaner import strip_inline_sources_from_web_answer

_GROUNDING = (
    "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
    "AQzI7kAbCdEfGhIjKlMnOpQrStUvWxYz"
)


def test_strips_sources_section_with_grounding_links():
    raw = (
        "Justice Surya Kant is the current CJI.\n\n"
        "## Sources\n\n"
        f"- [Wikipedia]({_GROUNDING})\n"
        f"- [The Hindu]({_GROUNDING})\n"
    )
    out = strip_inline_sources_from_web_answer(raw)
    assert "vertexaisearch" not in out.lower()
    assert "## Sources" not in out
    assert "Justice Surya Kant" in out


def test_strips_bare_grounding_urls():
    raw = f"See also {_GROUNDING} for details."
    out = strip_inline_sources_from_web_answer(raw)
    assert "vertexaisearch" not in out
    assert "See also" in out
