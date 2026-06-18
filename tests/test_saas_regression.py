"""
SaaS regression matrix — product success criteria from KB requirements.
"""
from __future__ import annotations

import pytest

from kb_query_types import QueryType, detect_query_type, extract_entities, needs_document_wide_scan
from kb_rag_decision import evaluate_retrieval
from kb_validate import validate_answer


REGRESSION_QUERIES = [
    ("Difference between 300 and 307", QueryType.COMPARISON, ["300", "307"], False),
    ("Compare 299 300 307", QueryType.COMPARISON, ["299", "300", "307"], False),
    ("Summarize all criminal offences", QueryType.LIST_EXTRACTION, [], True),
    ("List all IPC sections", QueryType.LIST_EXTRACTION, [], True),
    ("What topics are covered", QueryType.TOPIC_QUERY, [], True),
    ("What topics are discussed", QueryType.TOPIC_QUERY, [], True),
    ("What is IPC 307", QueryType.SECTION_EXPLANATION, ["307"], False),
    ("Explain 307", QueryType.SECTION_EXPLANATION, ["307"], False),
]


@pytest.mark.regression
@pytest.mark.parametrize("query,qtype,entities_min,doc_scan", REGRESSION_QUERIES)
def test_regression_query_classification(query, qtype, entities_min, doc_scan):
    got = detect_query_type(query)
    ent = extract_entities(query)
    assert got == qtype, f"{query}: got {got}, want {qtype}"
    for e in entities_min:
        assert e in ent["entities"], f"{query}: missing entity {e}"
    assert needs_document_wide_scan(got, query) == doc_scan


@pytest.mark.regression
def test_regression_comparison_never_single_section_gate():
    chunks = [{"content": "IPC 300 only", "final_score": 0.8}]
    found, _, _, debug = evaluate_retrieval(
        "300 vs 307",
        chunks,
        entities=["300", "307"],
        query_type="comparison",
    )
    assert not found
    assert debug.get("reason") == "comparison_incomplete"


@pytest.mark.regression
def test_regression_summary_found_with_entities(sample_legal_chunks):
    from kb_document_scan import extract_all_offences_from_chunks

    entities = extract_all_offences_from_chunks(sample_legal_chunks)
    found, _, _, _ = evaluate_retrieval(
        "Summarize all criminal offences",
        sample_legal_chunks,
        query_type="summary",
        extracted_count=len(entities),
    )
    assert found
    assert len(entities) >= 5


@pytest.mark.regression
def test_regression_comparison_answer_validation(comparison_chunks_300_307):
    answer = (
        "# IPC 300 vs IPC 307\n\n"
        "| **IPC Section 300** | **IPC Section 307** |\n"
        "| Murder | Attempt to Murder |\n\n"
        "## Key Difference\nIPC 300 requires death. IPC 307 covers attempts."
    )
    ok, reason = validate_answer(
        answer,
        "Difference between 300 and 307",
        comparison_chunks_300_307,
        QueryType.COMPARISON,
        profile_sections=["300", "307"],
    )
    assert ok, reason
