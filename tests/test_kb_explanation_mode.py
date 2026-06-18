"""EXPLANATION MODE — detect teach/explain queries; block list-only constitutional dumps."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.legacy_kb


@pytest.mark.parametrize(
    "q,expected",
    [
        ("Fundamental Rights explain it properly", True),
        ("explain IPC 499 in detail", True),
        ("what does this mean", True),
        ("teach me about Article 21", True),
        ("summarize fundamental rights", True),
        ("IPC Section 304", False),
        ("list fundamental rights", False),
    ],
)
def test_explanation_mode_active(q: str, expected: bool):
    from backend.app.core.kb_explanation_mode import explanation_mode_active

    assert explanation_mode_active(q) is expected


def test_format_constitutional_skips_explanation_mode():
    from answer_orchestrator import format_constitutional_rights_answer

    chunks = [
        {
            "content": (
                "Fundamental Rights: Right to Equality (Article 14), "
                "Right to Freedom (Article 19), Right Against Exploitation (Article 23)"
            ),
            "metadata": {"filename": "constitution.pdf"},
        }
    ]
    assert format_constitutional_rights_answer(
        "Fundamental Rights explain properly", chunks
    ) == ""


def test_build_explanation_from_chunks():
    from backend.app.core.kb_explanation_mode import build_explanation_from_chunks

    chunks = [
        {
            "content": (
                "Fundamental Rights: Right to Equality (Article 14), "
                "Right to Freedom (Article 19), Right to Life (Article 21)."
            )
        }
    ]
    out = build_explanation_from_chunks("Fundamental Rights explain properly", chunks)
    assert "### Definition" in out
    assert "### Key Components" in out
    assert "Article 14" in out
    assert len(out) > 400


def test_strip_virtue_padding():
    from backend.app.core.kb_explanation_mode import strip_virtue_padding

    spam = (
        "Important because justice fairness accountability transparency trustworthiness "
        "reliability dependability stability resilience strength courage perseverance."
    )
    assert strip_virtue_padding(spam) == ""


def test_sanitize_prefers_excerpt_fallback():
    from backend.app.core.kb_explanation_mode import sanitize_explanation_answer

    chunks = [
        {
            "content": "Right to Equality (Article 14), Right to Freedom (Article 19).",
            "metadata": {},
        }
    ]
    bad = (
        "### Definition\nFoo.\n### Detailed Explanation\n"
        "justice fairness accountability transparency trustworthiness reliability "
        "dependability stability resilience fortitude compassion empathy."
    )
    out = sanitize_explanation_answer(bad, chunks)
    assert "justice fairness accountability" not in out.lower()
    assert "Article 14" in out or "equality" in out.lower()


def test_looks_like_chunk_dump():
    from backend.app.core.kb_explanation_mode import looks_like_chunk_dump

    dump = (
        "Right to Equality (Article 14)\n"
        "Right to Freedom (Article 19)\n"
        "Right Against Exploitation (Article 23)"
    )
    good = (
        "### Definition\nFundamental rights are constitutional guarantees.\n\n"
        "### Detailed Explanation\nThey protect citizens from state overreach.\n\n"
        "### Key Components\n- **Equality (Art. 14):** equal protection of laws.\n"
    )
    assert looks_like_chunk_dump(dump)
    assert not looks_like_chunk_dump(good)
