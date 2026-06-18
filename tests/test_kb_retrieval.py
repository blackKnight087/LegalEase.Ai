"""Unit tests for multi-section retrieval helpers."""
import pytest

from kb_retrieval import (
    build_section_retrieval_queries,
    ensure_per_section_chunks,
    extract_comparison_sections,
    is_comparison_query,
    section_in_chunk,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "query,expected",
    [
        ("Difference between 300 and 307", ["300", "307"]),
        ("section 300 and 307 difference", ["300", "307"]),
        ("Compare IPC 299, 300 and 307", ["299", "300", "307"]),
        ("What is IPC 307?", ["307"]),
    ],
)
def test_extract_comparison_sections(query, expected):
    got = extract_comparison_sections(query)
    for e in expected:
        assert e in got


@pytest.mark.unit
def test_ensure_per_section_chunks_both_present():
    ranked = [
        {"content": "IPC 300 Murder", "final_score": 0.9},
        {"content": "IPC 300 again", "final_score": 0.8},
        {"content": "IPC 307 Attempt", "final_score": 0.85},
    ]
    out = ensure_per_section_chunks(ranked, ["300", "307"], max_total=6)
    texts = " ".join(c["content"] for c in out).lower()
    assert "300" in texts
    assert "307" in texts
    assert len(out) >= 2


@pytest.mark.unit
def test_section_in_chunk():
    assert section_in_chunk("IPC Section 307 attempt", "307")
    assert not section_in_chunk("IPC Section 300 murder", "307")


@pytest.mark.unit
def test_build_section_retrieval_queries():
    qs = build_section_retrieval_queries(["300", "307"], "difference")
    assert any("300" in q for q in qs)
    assert any("307" in q for q in qs)


@pytest.mark.unit
def test_is_comparison_query():
    assert is_comparison_query("difference between 300 and 307")
    assert not is_comparison_query("What is IPC 307?")
