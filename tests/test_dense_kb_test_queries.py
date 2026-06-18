"""Dense KB test document helpers."""
from __future__ import annotations

from backend.app.core.dense_kb_test_queries import (
    DENSE_KB_SMOKE_QUERIES,
    is_dense_kb_test_filename,
)


def test_dense_filename_detection():
    assert is_dense_kb_test_filename("LegalEase_Dense_KB_Test_Document.pdf")
    assert not is_dense_kb_test_filename("random_contract.pdf")


def test_dense_query_set_nonempty():
    assert len(DENSE_KB_SMOKE_QUERIES) >= 8
    assert any("406" in q["query"] for q in DENSE_KB_SMOKE_QUERIES)
