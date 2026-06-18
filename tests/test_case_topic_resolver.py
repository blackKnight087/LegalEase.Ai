"""Topical case queries — theft case, murder case, etc."""
from __future__ import annotations

from backend.app.core.case_topic_resolver import (
    chunk_matches_topic_case,
    extract_topic_case_needles,
    is_statute_stub_chunk,
    is_topic_case_query,
)


def test_topic_case_query_detected():
    assert is_topic_case_query("explain the theft case")
    assert not is_topic_case_query("Riya Banerjee vs State Medical Board")


def test_extract_theft_needle():
    assert extract_topic_case_needles("explain the theft case") == ["theft"]


def test_statute_stub_rejected():
    stub = (
        "Meaning: Theft — dishonest taking of movable property.\n"
        "Explanation: This section is included to rigorously test retrieval accuracy."
    )
    assert is_statute_stub_chunk(stub)
    case = (
        "Case 3: State vs Dev Mallick (Theft – IPC 379)\n"
        "The accused Dev Mallick was charged under IPC Section 379 after warehouse CCTV footage."
    )
    assert not is_statute_stub_chunk(case)
    assert chunk_matches_topic_case({"content": case}, ["theft"])
    assert not chunk_matches_topic_case({"content": stub}, ["theft"])
