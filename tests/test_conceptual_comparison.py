"""Conceptual offence comparisons (murder vs attempt) without section numbers."""
from __future__ import annotations

import pytest

from backend.app.core.legal_offence_resolver import (
    extract_conceptual_comparison_entities,
    is_conceptual_comparison_query,
)
from kb_compare_engine import extract_all_comparison_entities, format_comparison_pro
from kb_query_types import QueryType, detect_query_type


@pytest.mark.parametrize(
    "query",
    [
        "What is the difference between murder and attempt to murder?",
        "Difference between culpable homicide and murder",
    ],
)
def test_conceptual_comparison_detected(query):
    assert is_conceptual_comparison_query(query)
    ents = extract_conceptual_comparison_entities(query)
    assert len(ents) >= 2
    assert detect_query_type(query) == QueryType.COMPARISON


def test_murder_vs_attempt_maps_300_307():
    ents = extract_conceptual_comparison_entities(
        "What is the difference between murder and attempt to murder?"
    )
    secs = {e["section"] for e in ents}
    assert "300" in secs
    assert "307" in secs


def test_format_conceptual_comparison_table():
    chunks = [
        {
            "content": (
                "IPC Section 300\nMeaning: Murder — culpable homicide becomes murder when intent exists.\n"
                "IPC Section 307\nMeaning: Attempt to Murder — punishment may extend to 10 years."
            ),
            "metadata": {"filename": "test.pdf"},
            "final_score": 0.9,
        }
    ]
    ents = extract_all_comparison_entities(
        "What is the difference between murder and attempt to murder?"
    )
    out = format_comparison_pro(
        "What is the difference between murder and attempt to murder?", chunks, ents
    )
    assert "| Aspect |" in out
    assert "300" in out
    assert "307" in out
    assert "rigorously test retrieval" not in out.lower()
