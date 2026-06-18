"""Unit tests for KB answer formatting."""
import pytest

from answer_orchestrator import format_comparison_answer, format_criminal_offences_summary
from intent_engine import classify_intent


@pytest.mark.unit
def test_format_comparison_includes_both_sections(comparison_chunks_300_307):
    profile = classify_intent("Difference between 300 and 307")
    profile.signals["entities"] = ["300", "307"]
    profile.signals["sections"] = ["300", "307"]
    answer = format_comparison_answer(
        "Difference between 300 and 307",
        comparison_chunks_300_307,
        profile,
    )
    assert answer
    assert "300" in answer
    assert "307" in answer
    assert "Comparison" in answer or "Key Difference" in answer


@pytest.mark.unit
def test_format_criminal_offences_summary(sample_legal_chunks):
    profile = classify_intent("Summarize all criminal offences")
    entities = [
        {"section": "299", "law": "IPC", "title": "Culpable Homicide", "label": "IPC 299"},
        {"section": "300", "law": "IPC", "title": "Murder", "label": "IPC 300"},
        {"section": "302", "law": "IPC", "title": "Punishment", "label": "IPC 302"},
        {"section": "307", "law": "IPC", "title": "Attempt", "label": "IPC 307"},
        {"section": "66C", "law": "IT Act", "title": "Identity Theft", "label": "IT Act 66C"},
    ]
    answer = format_criminal_offences_summary(
        "Summarize all criminal offences discussed",
        entities,
        sample_legal_chunks,
        profile,
    )
    assert answer
    assert "Criminal Offences" in answer
    assert "299" in answer
    assert "66C" in answer or "66c" in answer.lower()
