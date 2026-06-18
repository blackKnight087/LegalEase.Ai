"""Hybrid must drop irrelevant KB (RG Kar query vs cyber-fraud upload)."""
from __future__ import annotations

from backend.app.core.kb_hybrid_gate import assess_kb_for_hybrid, should_skip_kb_retrieval

IMRAN_KB = """
Case 1: State vs Imran Khan (Cyber Fraud & Cheating - IPC 420)
FIR No. 44/2024, Bidhannagar Cyber Crime Police Station.
Complainant Ravi head. Witness Priya Das.
"""

RG_QUERY = "explain rg kar case and why cbi failed to provide more evidances"


def test_rg_kar_query_rejects_imran_khan_kb():
    chunks = [{"content": IMRAN_KB, "metadata": {"filename": "test.pdf"}, "final_score": 0.55}]
    use_kb, reason = assess_kb_for_hybrid(RG_QUERY, IMRAN_KB, chunks)
    assert use_kb is False
    assert reason in (
        "signature_mismatch",
        "public_case_not_in_kb",
        "entity_miss",
        "term_overlap",
        "case_needle_miss",
    )


def test_skip_kb_prefetch_for_rg_kar_public_query():
    assert should_skip_kb_retrieval(RG_QUERY) is True
    assert should_skip_kb_retrieval("What does my uploaded PDF say about Imran Khan") is False


def test_imran_query_accepts_imran_kb():
    q = "Explain State vs Imran Khan cyber fraud case"
    use_kb, reason = assess_kb_for_hybrid(q, IMRAN_KB, [
        {"content": IMRAN_KB, "final_score": 0.7},
    ])
    assert use_kb is True
    assert reason == "ok"
