"""Unit tests for FOUND / NOT_FOUND retrieval gating."""
import pytest

from kb_rag_decision import evaluate_retrieval, extract_query_sections


@pytest.mark.unit
def test_evaluate_document_scan_found():
    chunks = [{"content": "IPC 299", "final_score": 0.5, "source": "document_scan"}]
    found, score, decision, _ = evaluate_retrieval(
        "Summarize offences",
        chunks,
        query_type="summary",
        extracted_count=6,
    )
    assert found
    assert decision == "FOUND"


@pytest.mark.unit
def test_evaluate_comparison_requires_both_sections():
    chunks = [
        {"content": "IPC Section 300 Murder", "final_score": 0.7},
        {"content": "IPC Section 307 Attempt", "final_score": 0.65},
    ]
    found, _, decision, debug = evaluate_retrieval(
        "300 and 307 difference",
        chunks,
        entities=["300", "307"],
        query_type="comparison",
    )
    assert found
    assert debug.get("reason") in {"comparison_all_sections", "typed_comparison_both"}


@pytest.mark.unit
def test_evaluate_comparison_incomplete_fails():
    chunks = [{"content": "IPC Section 300 Murder only", "final_score": 0.7}]
    found, _, _, debug = evaluate_retrieval(
        "300 and 307",
        chunks,
        entities=["300", "307"],
        query_type="comparison",
    )
    assert not found
    assert debug.get("reason") == "comparison_incomplete"


@pytest.mark.unit
def test_extract_query_sections_single():
    assert extract_query_sections("What is Section 307?") == ["307"]
