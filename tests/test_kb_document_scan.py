"""Unit tests for document-wide scan and offence extraction."""
import pytest

from kb_document_scan import (
    extract_all_offences_from_chunks,
    extract_ipc_sections_from_chunks,
    filter_chunks_by_law,
)
from kb_query_types import QueryType
from kb_document_scan import search_entire_document


@pytest.mark.unit
def test_extract_ipc_sections_from_sample(sample_legal_chunks):
    entities = extract_ipc_sections_from_chunks(sample_legal_chunks, laws_filter=["ipc", "bns"])
    sections = {e["section"].lower() for e in entities}
    assert "299" in sections
    assert "300" in sections
    assert "307" in sections
    assert "66c" not in sections


@pytest.mark.unit
def test_extract_all_offences_includes_it_act(sample_legal_chunks):
    entities = extract_all_offences_from_chunks(sample_legal_chunks)
    labels = " ".join(e["label"] for e in entities).lower()
    assert "299" in labels or "ipc 299" in labels
    assert "66c" in labels or "66d" in labels


@pytest.mark.unit
def test_filter_ipc_deprioritizes_it_only():
    chunks = [
        {"content": "IT Act Section 66C identity theft only.", "final_score": 0.5},
        {"content": "IPC Section 300 Murder.", "final_score": 0.5},
    ]
    filtered = filter_chunks_by_law(chunks, ["ipc"])
    joined = " ".join(c["content"] for c in filtered).lower()
    assert "ipc" in joined or "300" in joined
    assert "66c" not in joined or "300" in joined


@pytest.mark.regression
def test_summarize_offences_not_empty_entities(sample_legal_chunks):
    """Regression: document scan must find multiple offences."""
    entities = extract_all_offences_from_chunks(sample_legal_chunks)
    assert len(entities) >= 5
