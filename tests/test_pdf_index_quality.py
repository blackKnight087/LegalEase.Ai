"""PDF extraction quality gates and chunk expectations."""
from __future__ import annotations

from backend.app.core.pdf_index_quality import (
    expected_min_chunks,
    is_underchunked,
    is_weak_extraction,
)


def test_weak_extraction_detects_sparse_pages():
    assert is_weak_extraction("short", page_count=60) is True


def test_expected_chunks_for_large_text():
    text = "x" * 100_000
    need = expected_min_chunks(text, page_count=60)
    assert need >= 100


def test_underchunked_large_pdf():
    text = "x" * 100_000
    assert is_underchunked(text, chunk_count=12, page_count=60) is True
    assert is_underchunked(text, chunk_count=250, page_count=60) is False
