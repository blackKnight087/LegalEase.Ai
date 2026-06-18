"""Tests for adaptive response mode controller."""
from __future__ import annotations

from backend.app.services.response_mode_controller import detect_response_mode
from intent_engine import classify_intent


def test_quick_answer_law_replacement():
    profile = classify_intent("What replaced IPC?")
    mode = detect_response_mode("What replaced IPC?", profile)
    assert mode.mode == "quick_answer"
    assert mode.complexity == "short"
    assert mode.max_tokens <= 350


def test_detailed_analysis_murder_comparison():
    q = "Explain differences between IPC and BNS in murder provisions"
    profile = classify_intent(q)
    mode = detect_response_mode(q, profile)
    assert mode.mode in ("detailed_analysis", "comparison")
    assert mode.complexity == "deep"
    assert mode.max_tokens >= 900


def test_case_explanation():
    profile = classify_intent("Explain Kesavananda Bharati case")
    mode = detect_response_mode("Explain Kesavananda Bharati case", profile)
    assert mode.mode == "case_explanation"
    assert "Citation Block" in mode.structure_hint or "Overview" in mode.headings


def test_vishaka_guidelines_case_mode():
    profile = classify_intent("Explain Vishaka Guidelines")
    mode = detect_response_mode("Explain Vishaka Guidelines", profile)
    assert mode.mode == "case_explanation"


def test_comparison_table_mode():
    q = "Compare IPC 420 vs BNS equivalent"
    profile = classify_intent(q)
    mode = detect_response_mode(q, profile)
    assert mode.mode == "comparison"
    assert mode.use_table is True


def test_legal_drafting_mode():
    q = "Draft a legal notice for unpaid salary under contract law"
    profile = classify_intent(q)
    mode = detect_response_mode(q, profile)
    assert mode.mode == "legal_drafting"
