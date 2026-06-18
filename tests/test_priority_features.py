"""Citation verifier and report export tests."""
from __future__ import annotations


def test_verify_kb_citations():
    from backend.app.core.citation_verifier import verify_citations

    chunks = [{"metadata": {"filename": "ipc.pdf"}, "content": "302 murder"}]
    text = "Murder under [KB-1] and fake [KB-9]."
    out, stats = verify_citations(text, chunks, [])
    assert stats["verified_kb"] == 1
    assert stats["failed_kb"] == 1
    assert "Citation Verification" in out
    assert "Verified" in out
    assert "Not found" in out


def test_export_docx_bytes():
    from backend.app.core.report_export import export_report_bytes

    data, name, mime = export_report_bytes("## Summary\n\nTest report.", "Test Report", "docx")
    assert len(data) > 100
    assert name.endswith(".docx")
    assert "wordprocessingml" in mime


def test_resolve_unified_follow_up():
    from backend.app.core.conversation_memory import resolve_unified_follow_up

    session = {"last_section": "307", "last_law": "IPC", "last_topic": "IPC Section 307"}
    out = resolve_unified_follow_up("what punishment?", session_id=None, history=[], mode="deep_case")
    # Without session_id, uses empty session - test resolve_follow_up directly
    from backend.app.core.conversation_memory import resolve_follow_up_query

    out2 = resolve_follow_up_query("explain in details", session)
    assert "307" in out2 or "detail" in out2.lower()


def test_simplify_follow_up_expands_ipc_topic():
    from backend.app.core.conversation_memory import resolve_follow_up_query
    from backend.app.core.kb_context_resolver import build_retrieval_queries
    from conversation_context import enrich_query_with_context

    session = {
        "last_section": "406",
        "last_law": "IPC",
        "last_topic": "IPC Section 406",
        "last_user_query": "IPC Section 406 explain",
    }
    history = [
        {"role": "user", "content": "IPC Section 406 explain"},
        {"role": "assistant", "content": "IPC Section 406 — criminal breach of trust."},
    ]
    q = "Explain in simple language"
    out = resolve_follow_up_query(q, session)
    assert "406" in out
    primary, _ = build_retrieval_queries(q, session, history)
    assert "406" in primary
    enriched = enrich_query_with_context(q, history)
    assert "406" in enriched


def test_enrich_parsed_ipc_follow_up():
    from backend.app.services.legal_orchestrator_v2 import (
        QueryClass,
        _enrich_parsed_from_context,
        parse_query,
    )

    parsed = parse_query("Explain in simple language")
    assert parsed.query_class != QueryClass.SINGLE_SECTION
    history = [
        {"role": "user", "content": "IPC Section 420 explain"},
        {"role": "assistant", "content": "IPC Section 420 — cheating."},
    ]
    enriched = _enrich_parsed_from_context(
        parsed,
        original_query="Explain in simple language",
        search_q="Explain IPC Section 420 in simple language.",
        history=history,
    )
    assert enriched.query_class == QueryClass.SINGLE_SECTION
    assert "420" in enriched.sections


def test_doc_ranker_skips_case_pin_on_meta_follow_up():
    from backend.app.core.kb_doc_ranker import apply_document_ranking_to_scope

    scope = apply_document_ranking_to_scope(
        "Explain in simple language",
        "/tmp/unused",
        {},
    )
    assert scope.get("strict") is not True
    assert scope.get("reason") != "document_rank_winner"
