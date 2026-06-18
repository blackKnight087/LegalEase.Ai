"""Golden-file style KB regression — expected structure in answers."""
from __future__ import annotations

import pytest

from answer_orchestrator import format_comparison_answer, format_criminal_offences_summary
from intent_engine import QueryIntent, classify_intent
from kb_pipeline import generate_answer
from kb_query_types import QueryType


@pytest.mark.regression
def test_golden_comparison_table(comparison_chunks_300_307):
    profile = classify_intent("Difference between IPC 300 and 307")
    profile.primary = QueryIntent.COMPARISON
    profile.signals["entities"] = ["300", "307"]
    profile.signals["sections"] = ["300", "307"]
    answer = format_comparison_answer(
        "Difference between IPC 300 and 307",
        comparison_chunks_300_307,
        profile,
    )
    assert "300" in answer and "307" in answer
    assert "|" in answer
    assert "Key Difference" in answer or "Difference" in answer


@pytest.mark.regression
def test_golden_offences_summary(sample_legal_chunks):
    profile = classify_intent("Summarize all criminal offences")
    entities = [
        {"section": "299", "law": "IPC", "title": "Culpable Homicide", "label": "IPC 299"},
        {"section": "300", "law": "IPC", "title": "Murder", "label": "IPC 300"},
        {"section": "307", "law": "IPC", "title": "Attempt", "label": "IPC 307"},
        {"section": "66C", "law": "IT Act", "title": "Identity Theft", "label": "IT Act 66C"},
    ]
    answer = format_criminal_offences_summary(
        "Summarize all criminal offences",
        entities,
        sample_legal_chunks,
        profile,
    )
    assert "Criminal Offences" in answer
    for token in ("299", "300", "307"):
        assert token in answer


@pytest.mark.regression
def test_golden_pipeline_generate_comparison(comparison_chunks_300_307):
    profile = classify_intent("section 300 and 307 difference")
    profile.primary = QueryIntent.COMPARISON
    profile.signals["entities"] = ["300", "307"]
    answer = generate_answer(
        "section 300 and 307 difference",
        comparison_chunks_300_307,
        profile,
        query_type=QueryType.COMPARISON,
    )
    assert "300" in answer.lower()
    assert "307" in answer.lower()
