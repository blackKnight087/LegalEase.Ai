"""Unit tests for answer validation layer."""
import pytest

from kb_query_types import QueryType
from kb_validate import validate_answer


@pytest.mark.unit
def test_comparison_requires_both_sections(comparison_chunks_300_307):
    good = (
        "# IPC 300 vs IPC 307\n\n"
        "| Section | Meaning |\n| 300 | Murder |\n| 307 | Attempt |\n\n"
        "IPC 300 applies when death occurs. IPC 307 applies for attempts."
    )
    ok, reason = validate_answer(
        good,
        "Difference between 300 and 307",
        comparison_chunks_300_307,
        QueryType.COMPARISON,
        profile_sections=["300", "307"],
    )
    assert ok, reason

    bad = "IPC Section 300 — Murder only."
    ok2, reason2 = validate_answer(
        bad,
        "Difference between 300 and 307",
        comparison_chunks_300_307,
        QueryType.COMPARISON,
        profile_sections=["300", "307"],
    )
    assert not ok2
    assert "comparison_missing" in reason2 or "307" in reason2


@pytest.mark.unit
def test_summary_passes_with_entity_count(sample_legal_chunks):
    answer = "# Criminal Offences\n\n1. IPC 299\n2. IPC 300\n3. IPC 307"
    ok, _ = validate_answer(
        answer,
        "Summarize all criminal offences",
        sample_legal_chunks,
        QueryType.SUMMARY,
        entity_count=6,
    )
    assert ok


@pytest.mark.unit
def test_not_found_phrase_allowed():
    from kb_response_state import KB_NOT_FOUND_MESSAGE

    ok, _ = validate_answer(
        KB_NOT_FOUND_MESSAGE,
        "unknown topic",
        [],
        QueryType.UNKNOWN,
    )
    assert ok

