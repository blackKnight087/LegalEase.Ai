"""Constitutional domain routing — no IPC section false positives."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.app.core.constitutional_concept_map import (
    expand_constitutional_query,
    is_constitutional_query,
    resolve_article,
)
from backend.app.core.legal_domain_router import LegalDomain, route_legal_domain
from backend.app.services.legal_orchestrator_v2 import parse_query, QueryClass


@pytest.mark.parametrize(
    "query,article",
    [
        ("Explain Right to Equality", "14"),
        ("Explain Article 21", "21"),
        ("Right to Life", "21"),
    ],
)
def test_constitutional_article_resolution(query, article):
    assert is_constitutional_query(query)
    assert resolve_article(query) == article
    route = route_legal_domain(query)
    assert route.domain == LegalDomain.CONSTITUTION
    assert route.block_ipc
    assert "Article" in route.expanded_query


def test_expand_query_not_ipc():
    exp = expand_constitutional_query("Explain Right to Equality")
    assert "Article 14" in exp
    assert "IPC" not in exp.upper() or "CONSTITUTION" in exp.upper()


def test_parse_query_constitutional_not_ipc_section():
    p = parse_query("Explain Right to Equality")
    assert p.query_class == QueryClass.CONSTITUTIONAL
    assert p.constitutional_article == "14"
    assert p.sections == []
    assert "IPC" not in (p.law_systems or [])


@pytest.fixture
def _indexed_kb(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "db"))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss"))
    monkeypatch.setenv("LEARNING_ENGINE_ENABLED", "0")
    from backend.app.core.core_db import ensure_app_schemas

    ensure_app_schemas()
    text = Path("Data/20260523211315_915ca1c5_legal_kb_test_document.auto.extracted.txt").read_text(
        encoding="utf-8"
    )
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = "const-route"
    index_dir = get_unlinked_index_dir(uid)
    index_documents(
        [
            {
                "doc_id": str(uuid.uuid4()),
                "filename": "legal_kb_test_document.pdf",
                "text": text,
            }
        ],
        index_dir=index_dir,
    )
    return uid, index_dir


def test_e2e_right_to_equality(_indexed_kb):
    uid, index_dir = _indexed_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(
        uid, "Explain Right to Equality", [], index_dir=index_dir
    )
    assert diag.get("query_class") == "constitutional"
    assert "Article 14" in ans or "article 14" in ans.lower()
    assert "IPC Section 14" not in ans
    assert "IPC Section 299" not in ans


def test_e2e_ipc_307_still_works(_indexed_kb):
    uid, index_dir = _indexed_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(uid, "Explain IPC 307", [], index_dir=index_dir)
    assert "307" in ans
    assert diag.get("query_class") != "constitutional"


def test_extract_article_snippet_from_list_line():
    from backend.app.core.constitutional_concept_map import extract_article_snippet

    line = (
        "Right to Equality (Article 14), Right to Freedom (Article 19), "
        "Right Against Exploitation (Article 23), Right to Freedom of Religion (Article 25)"
    )
    snip = extract_article_snippet(line, "23", topic="right against exploitation")
    assert "23" in snip
    assert "25" not in snip
    assert "14" not in snip


def test_constitutional_follow_up_expand():
    from backend.app.core.conversation_memory import _resolve_follow_up_rules

    mem = {
        "last_domain": "constitution",
        "last_constitutional_article": "23",
        "last_topic": "right against exploitation",
    }
    out = _resolve_follow_up_rules("Summarize key points", mem)
    assert "Article 23" in out or "Exploitation" in out
    assert "IPC" not in out.upper()


def test_e2e_exploitation_not_multi_right_list(_indexed_kb):
    uid, index_dir = _indexed_kb
    from kb_pipeline import kb_pipeline

    ans, _, _ = kb_pipeline(
        uid, "Explain Right against Exploitation", [], index_dir=index_dir
    )
    assert "Article 23" in ans or "article 23" in ans.lower()
    assert "Article 25" not in ans
    assert len(ans.strip()) > 30


def test_e2e_summarize_follow_up_constitutional(_indexed_kb):
    uid, index_dir = _indexed_kb
    from kb_pipeline import kb_pipeline
    from backend.app.core.conversation_memory import _resolve_follow_up_rules

    kb_pipeline(uid, "Explain Right to Equality", [], index_dir=index_dir)
    mem = {
        "last_domain": "constitution",
        "last_constitutional_article": "14",
        "last_topic": "right to equality",
    }
    expanded = _resolve_follow_up_rules("Summarize key points", mem)
    ans, _, diag = kb_pipeline(uid, expanded, [], index_dir=index_dir)
    assert diag.get("query_class") == "constitutional"
    assert "IPC Section" not in ans
    assert "Article 14" in ans or "equality" in ans.lower()


def test_e2e_compare_ipc_299_300(_indexed_kb):
    uid, index_dir = _indexed_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(
        uid, "Difference between IPC 299 and IPC 300", [], index_dir=index_dir
    )
    assert "| Aspect |" in ans or "299" in ans
    assert "300" in ans
    assert diag.get("query_class") != "constitutional"
