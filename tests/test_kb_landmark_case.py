"""Landmark case extraction — Kesavananda, Nirbhaya, no chunk dumps."""
from __future__ import annotations

from backend.app.core.kb_landmark_case import (
    build_landmark_case_answer,
    extract_landmark_passage,
    is_landmark_case_query,
)
from answer_orchestrator import format_case_topic_answer

MIXED = """
BNS Section 103 – Punishment for Murder
Provides punishment for murder under the new criminal law framework.
Five Constitutional Rights
1. Right to Equality (Article 14)
Kesavananda Bharati Case The Supreme Court introduced the Basic Structure Doctrine and ruled that Parliament cannot alter the Constitution's basic structure.
Nirbhaya Case (2012 Delhi Gang Rape Case) The case led to major criminal law reforms in India and stricter anti-rape laws through the Criminal Law Amendment Act, 2013.
LegalEase KB Testing Document – Realistic Indian Legal Cases (Volume 2)
Case 1: State vs Imran Khan (Cyber Fraud – IPC 420) FIR No. 44/2024
"""


def test_landmark_query_detected():
    assert is_landmark_case_query("Kesavananda Bharati Case EXPLAIN")
    assert is_landmark_case_query("Nirbhaya Case")


def test_extract_kesavananda_only():
    passage = extract_landmark_passage(MIXED, "kesavananda")
    assert "Basic Structure" in passage
    assert "Nirbhaya" not in passage
    assert "Right to Equality" not in passage


def test_build_kesavananda_answer():
    chunks = [{"content": MIXED, "metadata": {"filename": "legal_kb_test_document.pdf"}}]
    ans = build_landmark_case_answer("Kesavananda Bharati Case EXPLAIN", chunks)
    assert ans
    al = ans.lower()
    assert "basic structure" in al
    assert "nirbhaya" not in al
    assert "imran khan" not in al
    assert "legalease kb testing document" not in al


def test_nirbhaya_wrong_case_chunk_rejected():
    vol2 = {
        "content": (
            "LegalEase KB Testing Document – Realistic Indian Legal Cases (Volume 2) "
            "Case 1: State vs Imran Khan (Cyber Fraud – IPC 420) FIR No. 44/2024"
        ),
        "metadata": {"filename": "LegalEase_Realistic_Indian_Cases_Vol2.pdf"},
    }
    assert format_case_topic_answer("Nirbhaya Case", [vol2]) == ""
