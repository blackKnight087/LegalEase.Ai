"""Regression tests — legal comparison engine (IPC/BNS, CrPC/BNSS, Evidence/BSA)."""
from __future__ import annotations

import pytest

from kb_compare_engine import (
    extract_typed_entities,
    format_comparison_pro,
    is_compare_query,
    retrieve_for_comparison,
    sanitize_chunk_text,
)
from kb_query_types import QueryType, detect_query_type, extract_entities


LAW_CHART = """
INDIAN OLD VS NEW CRIMINAL LAWS
Indian Penal Code (IPC), 1860 → Bharatiya Nyaya Sanhita (BNS), 2023
Code of Criminal Procedure (CrPC), 1973 → Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023
Indian Evidence Act, 1872 → Bharatiya Sakshya Adhiniyam (BSA), 2023

IPC 302 → BNS 103
Murder — punishment with death or imprisonment for life.

IPC 307 → BNS 109
Attempt to murder — imprisonment up to ten years.

IPC 375 → BNS 63
Sexual offences under updated BNS framework.

IPC 420 → BNS 318
Cheating and dishonest inducement.

Topic / Usage
IPC Section BNS Section Topic / Usage
"""


@pytest.fixture
def mapping_chunks():
    from kb_preprocess import split_semantic_legal_chunks

    chunks = []
    for i, (text, start, end) in enumerate(
        split_semantic_legal_chunks(LAW_CHART, chunk_size=900, chunk_overlap=100, max_chunk=1200)
    ):
        chunks.append(
            {
                "content": text,
                "metadata": {"filename": "criminal_laws_chart.pdf", "chunk_index": str(i)},
                "final_score": 0.75,
                "hybrid_score": 0.75,
            }
        )
    return chunks


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Compare IPC 302 and BNS 103", [("IPC", "302"), ("BNS", "103")]),
        ("Difference between IPC 307 and BNS equivalent", [("IPC", "307"), ("BNS", "109")]),
        ("IPC 375 vs BNS section", [("IPC", "375"), ("BNS", "63")]),
    ],
)
def test_typed_entity_extraction(query, expected):
    entities = extract_typed_entities(query)
    assert len(entities) >= 2
    for i, (law, sec) in enumerate(expected):
        assert entities[i]["type"] == law
        assert entities[i]["section"] == sec


def test_compare_intent_detection():
    assert detect_query_type("Compare IPC 302 and BNS 103") == QueryType.COMPARISON
    assert detect_query_type("CrPC vs BNSS procedure") == QueryType.COMPARISON
    assert detect_query_type("Evidence Act vs BSA") == QueryType.COMPARISON
    assert is_compare_query("IPC 375 vs BNS section")


def test_sanitize_removes_chart_boilerplate():
    cleaned = sanitize_chunk_text("Topic / Usage\nIPC 302 → BNS 103\nMurder punishment")
    assert "Topic / Usage" not in cleaned
    assert "302" in cleaned


def test_format_ipc_bns_comparison(mapping_chunks):
    entities = extract_typed_entities("Compare IPC 302 and BNS 103")
    answer = format_comparison_pro("Compare IPC 302 and BNS 103", mapping_chunks, entities)

    assert answer
    assert "302" in answer
    assert "103" in answer
    assert "IPC" in answer
    assert "BNS" in answer
    assert "Topic / Usage" not in answer
    assert "| Aspect |" in answer
    assert answer.count("—") < 3
    assert "Key Difference" in answer


def test_format_ipc_307_bns_equivalent(mapping_chunks):
    entities = extract_typed_entities("Difference between IPC 307 and BNS equivalent")
    answer = format_comparison_pro(
        "Difference between IPC 307 and BNS equivalent", mapping_chunks, entities
    )
    assert "307" in answer
    assert "109" in answer
    assert "Topic / Usage" not in answer


def test_format_ipc_375_vs_bns(mapping_chunks):
    entities = extract_typed_entities("IPC 375 vs BNS section")
    answer = format_comparison_pro("IPC 375 vs BNS section", mapping_chunks, entities)
    assert "375" in answer
    assert "63" in answer


def test_format_crpc_vs_bnss(mapping_chunks):
    entities = extract_typed_entities("Compare CrPC vs BNSS")
    answer = format_comparison_pro("Compare CrPC vs BNSS", mapping_chunks, entities)
    assert "CrPC" in answer
    assert "BNSS" in answer
    assert "Topic / Usage" not in answer


def test_format_evidence_vs_bsa(mapping_chunks):
    entities = extract_typed_entities("Evidence Act vs BSA")
    answer = format_comparison_pro("Evidence Act vs BSA", mapping_chunks, entities)
    assert "Evidence" in answer or "evidence" in answer.lower()
    assert "BSA" in answer
    assert "Topic / Usage" not in answer


def test_entity_in_chunk_matching(mapping_chunks):
    entities = extract_typed_entities("Compare IPC 302 and BNS 103")
    from kb_compare_engine import _entity_in_chunk

    combined = "\n".join(c["content"] for c in mapping_chunks)
    assert _entity_in_chunk(combined, entities[0])
    assert _entity_in_chunk(combined, entities[1])


def test_extract_entities_includes_typed():
    info = extract_entities("Compare IPC 302 and BNS 103")
    assert info["intent"] == QueryType.COMPARISON
    assert len(info.get("typed_entities") or []) >= 2


def test_no_placeholder_in_comparison_output(mapping_chunks):
    for query in [
        "Compare IPC 302 and BNS 103",
        "Difference between IPC 307 and BNS equivalent",
        "IPC 375 vs BNS section",
        "CrPC vs BNSS",
        "Evidence Act vs BSA",
    ]:
        entities = extract_typed_entities(query)
        answer = format_comparison_pro(query, mapping_chunks, entities)
        assert "Topic / Usage" not in answer
        assert "| **Offence** |" not in answer
        assert "couldn't find" not in answer.lower()
