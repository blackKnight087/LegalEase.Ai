"""Unit tests for KB response state machine."""
import pytest

from kb_response_state import (
    KB_NOT_FOUND_MESSAGE,
    build_found_answer,
    contains_not_found_phrase,
    enforce_single_state,
)
from intent_engine import classify_intent, QueryIntent


@pytest.mark.unit
def test_enforce_single_state_not_found():
    assert enforce_single_state("random", found=False) == KB_NOT_FOUND_MESSAGE


@pytest.mark.unit
def test_enforce_single_state_strips_false_not_found():
    mixed = (
        "IPC Section 307 — Attempt to Murder. "
        "I couldn't find a clear reference to that in the uploaded legal documents."
    )
    out = enforce_single_state(mixed, found=True)
    assert "307" in out
    assert not contains_not_found_phrase(out)


@pytest.mark.unit
def test_build_found_answer_comparison_table(comparison_chunks_300_307):
    profile = classify_intent("Difference between IPC 300 and 307")
    profile.signals["entities"] = ["300", "307"]
    profile.signals["sections"] = ["300", "307"]
    profile.primary = QueryIntent.COMPARISON
    answer = build_found_answer(
        "Difference between IPC 300 and 307",
        comparison_chunks_300_307,
        profile,
        use_llm=False,
    )
    assert answer
    al = answer.lower()
    assert "300" in al
    assert "307" in al
    assert "|" in answer or "difference" in al


@pytest.mark.unit
def test_build_found_answer_list_from_entities(sample_legal_chunks):
    profile = classify_intent("Summarize all criminal offences")
    profile.signals["extracted_entities"] = [
        {"section": "299", "law": "IPC", "title": "Culpable Homicide", "label": "IPC 299"},
        {"section": "300", "law": "IPC", "title": "Murder", "label": "IPC 300"},
        {"section": "307", "law": "IPC", "title": "Attempt", "label": "IPC 307"},
    ]
    profile.primary = QueryIntent.LIST_EXTRACTION
    answer = build_found_answer(
        "Summarize all criminal offences",
        sample_legal_chunks,
        profile,
        use_llm=False,
    )
    assert answer
    assert any(s in answer for s in ("299", "300", "302", "307"))
