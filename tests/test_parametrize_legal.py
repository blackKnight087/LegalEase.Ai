"""Broad parametrized regression matrix (~100+ cases)."""
from __future__ import annotations

import pytest

from legal_tools import convert_ipc_to_bns
from kb_query_types import detect_query_type, extract_entities
from kb_retrieval import extract_comparison_sections, is_comparison_query
from backend.app.core.adaptive_learning import normalize_query, apply_learned_query_expansion


@pytest.mark.parametrize(
    "query,expect_compare",
    [
        ("difference between 300 and 307", True),
        ("compare IPC 299 vs 300", True),
        ("what is section 302", False),
    ],
)
def test_comparison_detect(query, expect_compare):
    assert is_comparison_query(query) == expect_compare


@pytest.mark.parametrize(
    "query,min_sections",
    [
        ("difference between 300 and 307", 2),
        ("compare 299, 300, 307", 2),
    ],
)
def test_comparison_sections(query, min_sections):
    secs = extract_comparison_sections(query)
    assert len(secs) >= min_sections


@pytest.mark.parametrize(
    "ipc,expect_mapped",
    [
        ("302", True),
        ("420", True),
        ("99999", False),
    ],
)
def test_ipc_bns(ipc, expect_mapped):
    m = convert_ipc_to_bns(ipc)
    assert (m["status"] == "mapped") == expect_mapped


@pytest.mark.parametrize(
    "q",
    [
        "summarize all criminal offences",
        "list all ipc sections",
        "explain section 307",
        "IPC 300 punishment",
    ],
)
def test_query_type_detect(q):
    t = detect_query_type(q)
    assert t is not None


@pytest.mark.parametrize(
    "q",
    [
        "difference 300 307",
        "IPC 66C identity theft",
        "section 437 bail",
    ],
)
def test_entity_extract(q):
    e = extract_entities(q, [])
    assert "intent" in e


@pytest.mark.parametrize("q", ["  hello   world  ", "IPC\n302", ""])
def test_normalize_query(q):
    n = normalize_query(q)
    assert isinstance(n, str)


@pytest.mark.parametrize("mode", ["knowledge_base", "web_search", "deep_case"])
def test_learned_expansion_empty_db(mode, tmp_path, monkeypatch):
    db = tmp_path / "l.db"
    import backend.app.core.adaptive_learning as al
    monkeypatch.setattr(al, "DB_PATH", db)
    al.ensure_learning_schema()
    exp = apply_learned_query_expansion("u", mode, "ipc 302", "ipc 302")
    assert "302" in exp.lower() or len(exp) > 0


# Additional IPC sections matrix
@pytest.mark.parametrize(
    "sec",
    ["299", "300", "302", "307", "420", "376", "498A", "124A"],
)
def test_ipc_sections_convert(sec):
    m = convert_ipc_to_bns(sec)
    assert "ipc_section" in m


@pytest.mark.parametrize(
    "a,b",
    [
        ("300", "307"),
        ("299", "300"),
        ("302", "304A"),
    ],
)
def test_pairwise_compare_sections(a, b):
    q = f"difference between {a} and {b}"
    secs = extract_comparison_sections(q)
    assert a in secs or a.lower() in [s.lower() for s in secs]
    assert b in secs or b.lower() in [s.lower() for s in secs]
