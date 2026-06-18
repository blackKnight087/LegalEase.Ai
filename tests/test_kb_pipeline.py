"""Integration tests for kb_pipeline with mocked retrieval."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from kb_query_types import QueryType


@pytest.mark.integration
@patch("backend.app.services.legal_orchestrator_v2.run_legal_orchestrator_v2", side_effect=RuntimeError("legacy_test"))
@patch("app.get_user_index_dir")
@patch("kb_document_scan.search_entire_document")
def test_pipeline_summary_uses_document_scan(mock_scan, mock_index, mock_orch, sample_legal_chunks):
    from kb_document_scan import extract_all_offences_from_chunks
    from kb_pipeline import kb_pipeline

    entities = extract_all_offences_from_chunks(sample_legal_chunks)
    mock_index.return_value = "/tmp/fake"
    mock_scan.return_value = (sample_legal_chunks, entities)

    answer, chunks, diag = kb_pipeline("user-1", "Summarize all criminal offences discussed")
    assert answer != "NOT_FOUND_IN_KB"
    assert len(answer) > 50
    assert diag.get("found") or "299" in answer or "300" in answer


@pytest.mark.integration
@patch("backend.app.services.legal_orchestrator_v2.run_legal_orchestrator_v2", side_effect=RuntimeError("legacy_test"))
@patch("app.get_user_index_dir")
@patch("kb_compare_engine.retrieve_comparison_bundle")
@patch("kb_retrieval.retrieve_chunks_per_entity")
def test_pipeline_comparison_per_entity(
    mock_retrieve, mock_bundle, mock_index, mock_orch, comparison_chunks_300_307
):
    from kb_pipeline import kb_pipeline

    mock_index.return_value = "/tmp/fake"
    mock_retrieve.return_value = comparison_chunks_300_307
    bundle = MagicMock()
    bundle.all_chunks = comparison_chunks_300_307
    bundle.left_entity = {"section": "300"}
    bundle.right_entity = {"section": "307"}
    bundle.left_chunks = comparison_chunks_300_307[:1]
    bundle.right_chunks = comparison_chunks_300_307[1:]
    mock_bundle.return_value = bundle

    answer, chunks, diag = kb_pipeline("user-1", "section 300 and 307 difference")
    assert answer != "NOT_FOUND_IN_KB"
    al = answer.lower()
    assert "300" in al
    assert "307" in al
    assert diag.get("mode") in ("per_entity_comparison", "compare_independent") or len(chunks) >= 2


@pytest.mark.regression
@patch("app.get_user_index_dir")
@patch("kb_document_scan.search_entire_document")
def test_rag_query_summary_not_not_found(mock_scan, mock_index, sample_legal_chunks):
    """Regression: rag_query must not return NOT_FOUND when document has offences."""
    from kb_document_scan import extract_all_offences_from_chunks

    entities = extract_all_offences_from_chunks(sample_legal_chunks)
    mock_index.return_value = "/tmp/fake"
    mock_scan.return_value = (sample_legal_chunks, entities)

    with patch("rag.index_exists", return_value=True):
        with patch("app.get_user_document_count", return_value=1):
            with patch("app.build_faiss_index"):
                import app as app_mod

                answer, cases = app_mod.rag_query(
                    "user-regression",
                    "Summarize all criminal offences discussed",
                    k=12,
                    conversation_history=[],
                )
    assert answer != "NOT_FOUND_IN_KB"
    assert "couldn't find" not in answer.lower()[:200]
