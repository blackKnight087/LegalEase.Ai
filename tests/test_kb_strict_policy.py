"""KB strict policy — block outside knowledge and topic mismatch."""
from __future__ import annotations

from backend.app.core.kb_strict_policy import (
    answer_has_outside_knowledge_bleed,
    chunks_support_query_topic,
    finalize_kb_answer,
)


def test_detect_outside_knowledge_bleed():
    bad = (
        "Fundamental rights are not explicitly mentioned in the document. "
        "In many legal systems, fundamental rights refer to basic human liberties."
    )
    assert answer_has_outside_knowledge_bleed(bad)


def test_chunks_support_fundamental_rights():
    chunks = [
        {
            "content": (
                "Fundamental Rights\n"
                "Right to Equality (Article 14), Right to Freedom (Article 19)."
            )
        }
    ]
    assert chunks_support_query_topic("Fundamental Rights explain", chunks)


def test_chunks_reject_ipc_only_for_rights_query():
    chunks = [{"content": "IPC Section 499 Meaning: Defamation under Indian Penal Code."}]
    assert not chunks_support_query_topic("Fundamental Rights explain", chunks)


def test_finalize_strips_outside_knowledge():
    chunks = [
        {
            "content": (
                "Fundamental Rights\n"
                "Right to Equality (Article 14), Right to Freedom (Article 19)."
            ),
            "metadata": {"filename": "test.pdf"},
            "final_score": 0.9,
        }
    ]
    bad = (
        "Not in the document. In many legal systems, rights include speech and religion."
    )
    out = finalize_kb_answer(bad, "Fundamental Rights explain", chunks)
    assert "many legal systems" not in out.lower()
    assert "article 14" in out.lower()
    assert "insufficient information" not in out.lower()
