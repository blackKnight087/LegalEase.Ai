"""Unit tests for kb_query_types — intent and entity extraction."""
import pytest

from kb_query_types import QueryType, detect_query_type, extract_entities, needs_document_wide_scan


@pytest.mark.unit
@pytest.mark.parametrize(
    "query,expected_type,expected_entities",
    [
        ("What is IPC 307?", QueryType.SECTION_EXPLANATION, ["307"]),
        ("Explain IPC 307", QueryType.SECTION_EXPLANATION, ["307"]),
        ("Difference between IPC 299 and 300", QueryType.COMPARISON, ["299", "300"]),
        ("section 300 and 307 difference", QueryType.COMPARISON, ["300", "307"]),
        ("Compare IPC 299, 300 and 307", QueryType.COMPARISON, ["299", "300", "307"]),
        ("Summarize all criminal offences discussed", QueryType.LIST_EXTRACTION, []),
        ("List all IPC sections mentioned", QueryType.LIST_EXTRACTION, []),
        ("What topics are covered?", QueryType.TOPIC_QUERY, []),
        ("What punishment under 302?", QueryType.PUNISHMENT_QUERY, ["302"]),
    ],
)
def test_detect_query_type_and_entities(query, expected_type, expected_entities):
    got_type = detect_query_type(query)
    ent = extract_entities(query)
    assert got_type == expected_type
    assert ent["intent"] == expected_type
    for e in expected_entities:
        assert e in ent["entities"]


@pytest.mark.unit
def test_comparison_never_single_entity():
    ent = extract_entities("Difference between Section 300 and 307")
    assert len(ent["entities"]) >= 2
    assert "300" in ent["entities"]
    assert "307" in ent["entities"]


@pytest.mark.unit
def test_contract_nda_query_is_entity_lookup_not_section():
    q = "what is Sample Non-Disclosure Agreement (NDA)"
    assert detect_query_type(q) == QueryType.ENTITY_LOOKUP
    ent = extract_entities(q)
    assert ent["intent"] == QueryType.ENTITY_LOOKUP
    assert "299" not in ent["entities"]


@pytest.mark.unit
def test_contract_query_not_rewritten_to_ipc_section():
    from conversation_context import enrich_query_with_context

    history = [
        {"role": "user", "content": "Explain IPC Section 299"},
        {"role": "assistant", "content": "IPC Section 299 defines culpable homicide."},
    ]
    q = "what is Sample Non-Disclosure Agreement (NDA)"
    enriched = enrich_query_with_context(q, history)
    assert "299" not in enriched
    assert enriched.strip() == q.strip()


@pytest.mark.unit
def test_contract_overview_answer_from_extractor():
    from contract_entity_extractor import answer_entity_lookup, extract_contract_entities

    body = (
        "Sample Non-Disclosure Agreement\n\n"
        "Confidential Information means information disclosed by the Disclosing Party. "
        "Upon termination, the Receiving Party shall return all materials."
    )
    entities = extract_contract_entities(body, "nda")
    answer = answer_entity_lookup("what is Sample Non-Disclosure Agreement (NDA)", entities, "nda")
    assert answer
    assert "NDA" in answer or "Agreement" in answer
    assert "299" not in answer


@pytest.mark.unit
def test_bare_section_after_comparison_history():
    history = [
        {"role": "user", "content": "Compare IPC 302 and BNS 103"},
        {"role": "assistant", "content": "Comparison table."},
    ]
    assert detect_query_type("section 300", history) == QueryType.SECTION_LOOKUP
    ent = extract_entities("section 300", history)
    assert ent["entities"] == ["300"]
    assert ent["intent"] != QueryType.COMPARISON


@pytest.mark.unit
@pytest.mark.parametrize(
    "query,should_scan",
    [
        ("Summarize all criminal offences discussed", True),
        ("List all IPC sections mentioned", True),
        ("What is IPC 307?", False),
        ("Difference between 300 and 307", False),
    ],
)
def test_document_wide_scan(query, should_scan):
    qt = detect_query_type(query)
    assert needs_document_wide_scan(qt, query) == should_scan


@pytest.mark.regression
def test_follow_up_with_history(follow_up_messages):
    ent = extract_entities("Explain it simply", follow_up_messages)
    assert ent["intent"] == QueryType.FOLLOW_UP
