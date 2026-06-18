"""Permanent case narrative engine — any party names, FAQ rejection."""
from __future__ import annotations

from backend.app.core.case_narrative_engine import (
    build_case_answer_from_chunks,
    classify_chunk_content_kind,
    is_faq_or_boilerplate,
    segment_cases_in_text,
    select_best_case_segment,
)
from backend.app.core.case_entity_resolver import extract_case_needles


SAMPLE_MULTI_CASE = """
Case 1: State vs Rohan Mehta (IPC 307)
FIR No. 99/2025. Complainant Akash Verma alleged assault by Rohan Mehta with a metal rod.
Hearing 1: prosecution argued attempt to murder; defense argued self-defense.

Case 2: Priya Verma vs Rajesh Verma (Domestic Violence)
Petitioner Priya Verma alleged domestic violence and financial control.
Hearing 1: interim protection order granted.

Suggested Questions
? What is IPC 307?
? Summarize domestic violence case.
"""


def test_faq_chunk_detected():
    assert classify_chunk_content_kind("? What is IPC?\n? Who is party?") == "faq_list"
    assert is_faq_or_boilerplate("? Line one?\n? Line two?\n? Line three?")


def test_segments_split_by_case_header():
    segs = segment_cases_in_text(SAMPLE_MULTI_CASE)
    assert len(segs) >= 2
    rohan = select_best_case_segment(SAMPLE_MULTI_CASE, extract_case_needles("State vs Rohan Mehta"))
    assert "rohan mehta" in rohan.lower()
    assert "priya verma vs rajesh" not in rohan.lower() or "domestic violence" not in rohan.lower()


def test_priya_case_isolated():
    block = select_best_case_segment(
        SAMPLE_MULTI_CASE,
        extract_case_needles("Explain Priya Verma vs Rajesh Verma"),
    )
    assert "domestic violence" in block.lower() or "priya verma" in block.lower()
    assert "rohan mehta" not in block.lower()


def test_build_answer_no_faq_bullets():
    chunks = [
        {"content": SAMPLE_MULTI_CASE, "metadata": {"content_kind": "case_narrative"}},
        {
            "content": "? Random FAQ?\n? Another question?",
            "metadata": {"content_kind": "faq_list"},
        },
    ]
    ans = build_case_answer_from_chunks("State vs Rohan Mehta detailed", chunks)
    assert ans
    assert "?" not in ans or "FIR" in ans
    assert "Random FAQ" not in ans
