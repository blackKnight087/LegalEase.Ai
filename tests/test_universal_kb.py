"""Universal KB routing — any document type, not IPC-only."""
from __future__ import annotations

import pytest

from backend.app.core.universal_kb import is_statute_focused_query


@pytest.mark.unit
@pytest.mark.parametrize(
    "query,statute",
    [
        ("IPC Section 302", True),
        ("section 300", True),
        ("punishment under IPC 406", True),
        ("What are the confidentiality obligations in this NDA?", False),
        ("Summarize the sale deed terms", False),
        ("Basic constitutional rights", False),
        ("Who is the disclosing party?", False),
    ],
)
def test_statute_vs_document_query(query: str, statute: bool):
    assert is_statute_focused_query(query) is statute


@pytest.mark.unit
def test_chunks_overlap_query():
    from backend.app.core.universal_kb import chunks_overlap_query

    chunks = [{"content": "The disclosing party must keep all confidential information secret for five years."}]
    assert chunks_overlap_query("What are confidentiality obligations?", chunks) is True
    assert chunks_overlap_query("IPC Section 9999 quantum physics", chunks) is False
