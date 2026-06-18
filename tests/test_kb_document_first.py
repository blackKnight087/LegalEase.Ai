"""Document-first KB — generic grounding for any PDF."""
from __future__ import annotations

from backend.app.core.kb_document_first import (
    KB_INSUFFICIENT_FULL,
    build_document_first_answer,
    chunks_answer_query,
    finalize_document_first,
    strip_insufficient_disclaimer,
)


def test_fundamental_rights_document_first():
    chunks = [
        {
            "content": (
                "Fundamental Rights\n"
                "Right to Equality (Article 14), Right to Freedom (Article 19), "
                "Right Against Exploitation (Article 23)."
            ),
            "metadata": {"filename": "test.pdf", "page": 2},
            "final_score": 0.9,
        }
    ]
    out = build_document_first_answer("Fundamental Rights explain", chunks)
    assert "insufficient information" not in out.lower()
    assert "article 14" in out.lower()
    assert "## Answer" in out or "### Definition" in out
    if "## Answer" in out:
        assert "## Supporting Evidence" in out
        assert "Confidence Score" in out


def test_nda_title_query():
    chunks = [
        {
            "content": (
                "[PAGE:3]\n\nSample NDA Agreement\n"
                "Parties involved: Disclosing Party and Receiving Party. "
                "Confidential information must not be disclosed."
            ),
            "metadata": {"filename": "test.pdf"},
            "final_score": 0.85,
        }
    ]
    out = build_document_first_answer("Sample NDA Agreement", chunks)
    assert "NDA" in out or "Disclosing Party" in out
    assert "insufficient information" not in out.lower()


def test_finalize_no_contradictory_disclaimer():
    chunks = [
        {
            "content": "Fundamental Rights Right to Equality (Article 14).",
            "metadata": {"filename": "test.pdf"},
        }
    ]
    bad = (
        "The uploaded document does not contain sufficient information.\n\n"
        "**From your documents:**\nFundamental Rights Article 14"
    )
    out = finalize_document_first(bad, "Fundamental Rights explain", chunks)
    assert "does not contain sufficient information" not in out.lower()
    assert "article 14" in out.lower()


def test_insufficient_when_no_overlap():
    chunks = [{"content": "IPC Section 499 defamation only.", "metadata": {}}]
    assert not chunks_answer_query("Fundamental Rights explain", chunks)
    out = finalize_document_first("Some guess", "Fundamental Rights explain", chunks)
    assert out == KB_INSUFFICIENT_FULL


def test_strip_disclaimer():
    t = strip_insufficient_disclaimer(
        "No sufficient info.\n\n**From your documents:**\nBlood pressure 160/100"
    )
    assert "160/100" in t
    assert "sufficient information" not in t.lower()
