"""
KB query diagnostics — intent, entities, document scope, retrieval trace.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def run_kb_debug_query(
    user_id: str,
    query: str,
    *,
    index_dir: Any = None,
    session_id: Optional[str] = None,
    history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Full diagnostic pass without synthesizing a long answer."""
    from app import get_user_index_dir, resolve_rag_index_dir

    if index_dir is None:
        try:
            from backend.app.core.kb_retrieval_router import resolve_global_kb_index_dir

            index_dir = resolve_global_kb_index_dir(user_id)
        except Exception:
            index_dir = get_user_index_dir(user_id)

    q = (query or "").strip()
    out: Dict[str, Any] = {"query": q, "user_id": user_id}

    session_mem: Dict[str, Any] = {}
    if session_id:
        try:
            from backend.app.core.conversation_memory import get_session_legal_memory

            session_mem = get_session_legal_memory(session_id)
        except Exception:
            pass
    out["session_memory_keys"] = list(session_mem.keys())

    try:
        from backend.app.core.kb_context_resolver import classify_retrieval_context

        out["context"] = classify_retrieval_context(q, session_mem, history)
    except Exception as exc:
        out["context_error"] = str(exc)

    try:
        from backend.legal_engine.query_parser import parse_legal_query

        parsed = parse_legal_query(q, history, session_state=session_mem)
        out["intent"] = {
            "resolved_query": getattr(parsed, "resolved_query", ""),
            "intent": getattr(parsed, "intent", ""),
            "section": getattr(parsed, "section", ""),
            "law": getattr(parsed, "law", ""),
            "case_name": getattr(parsed, "case_name", ""),
        }
    except Exception as exc:
        out["intent_error"] = str(exc)

    scope: Dict[str, Any] = {}
    try:
        from backend.app.core.kb_doc_scope import (
            apply_unlinked_only_scope,
            filter_chunks_unlinked_only,
            list_unlinked_only_index_documents,
            resolve_document_scope,
        )
        from backend.app.core.kb_doc_ranker import apply_document_ranking_to_scope, rank_documents_for_query

        scope = resolve_document_scope(user_id, q, index_dir, history=history)
        scope = apply_document_ranking_to_scope(q, index_dir, scope, user_id=user_id)
        scope = apply_unlinked_only_scope(user_id, scope, index_dir)
        out["document_rank"] = rank_documents_for_query(q, index_dir, user_id=user_id)
        out["document_scope"] = scope
        out["unlinked_documents"] = list_unlinked_only_index_documents(user_id, index_dir)
    except Exception as exc:
        out["scope_error"] = str(exc)

    try:
        from backend.app.core.faiss_index_stats import count_index_vectors, index_exists

        vec = count_index_vectors(index_dir) if index_exists(index_dir) else 0
        out["index_stats"] = {
            "vectors_indexed": vec,
            "chunks_indexed": vec,
            "index_path": str(index_dir),
            "unlinked_documents": len(out.get("unlinked_documents") or []),
        }
    except Exception as exc:
        out["index_stats_error"] = str(exc)

    chunks: List[Dict[str, Any]] = []
    try:
        from backend.app.services.legal_orchestrator_v2 import run_legal_orchestrator_v2

        answer, chunks, pipe_diag = run_legal_orchestrator_v2(
            user_id=user_id,
            query=q,
            history=history,
            index_dir=index_dir,
            session_id=session_id,
        )
        out["answer_preview"] = (answer or "")[:300]
        out["pipeline"] = pipe_diag
        out["retrieval_mode"] = pipe_diag.get("retrieval_mode") or ""
        out["query_class"] = pipe_diag.get("query_class") or ""
        out["found"] = pipe_diag.get("found")
        out["found_reason"] = pipe_diag.get("found_reason") or ""
    except Exception as exc:
        out["orchestrator_error"] = str(exc)
        try:
            from backend.app.services.legal_orchestrator_v2 import (
                build_retrieval_plan,
                execute_retrieval,
                parse_query,
            )

            parsed_q = parse_query(q)
            out["query_class"] = parsed_q.query_class.value
            plan = build_retrieval_plan(parsed_q)
            chunks, mode = execute_retrieval(plan, parsed_q, index_dir, scope=scope)
            chunks = filter_chunks_unlinked_only(user_id, chunks or [], index_dir=index_dir)
            out["retrieval_mode"] = mode
        except Exception as exc2:
            out["retrieval_error"] = str(exc2)

    out["chunk_count"] = len(chunks)
    out["chunks"] = [
        {
            "rank": i + 1,
            "score": float(c.get("final_score") or c.get("score") or 0),
            "filename": str((c.get("metadata") or {}).get("filename", "")),
            "excerpt": (c.get("content") or "")[:240],
        }
        for i, c in enumerate(chunks[:8])
    ]
    try:
        from backend.app.core.kb_retrieval_debug import get_last_retrieval_debug

        dc = get_last_retrieval_debug()
        if dc:
            out["debug_console"] = dc
        else:
            from backend.app.core.kb_retrieval_debug import build_retrieval_debug_report

            out["debug_console"] = build_retrieval_debug_report(
                original_query=q,
                expanded_query=str(out.get("intent", {}).get("resolved_query") or q),
                retrieval_mode=str(out.get("retrieval_mode") or "KB"),
                chunks=chunks,
                session_mem=session_mem,
                scope=scope,
                index_dir=str(index_dir),
                index_stats=out.get("index_stats"),
                context_passed_to_llm=bool(chunks),
            )
    except Exception as exc:
        out["debug_console_error"] = str(exc)
    return out


KB_DEBUG_TEST_QUERIES = (
    "Article 14",
    "Article 19",
    "Article 21",
    "Article 32",
    "IPC 302",
    "IPC 304",
    "IPC 320",
    "Witness Rahul Ghosh",
    "Who sought custody?",
    "Fundamental Rights",
)


def run_kb_debug_batch(
    user_id: str,
    *,
    session_id: Optional[str] = None,
    queries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run the standard retrieval test set — chunks, context, tokens per query."""
    qs = list(queries or KB_DEBUG_TEST_QUERIES)
    rows: List[Dict[str, Any]] = []
    for q in qs:
        r = run_kb_debug_query(user_id, q, session_id=session_id)
        dc = r.get("debug_console") or {}
        rows.append(
            {
                "query": q,
                "chunks_found": int(r.get("chunk_count") or dc.get("chunk_count") or 0),
                "chunks_passed": len(r.get("chunks") or []),
                "context_built": bool(dc.get("context_passed_to_llm")),
                "tokens_sent": int(dc.get("prompt_token_estimate") or 0),
                "retrieval_mode": r.get("retrieval_mode") or dc.get("retrieval_mode") or "",
                "found_reason": r.get("found_reason") or "",
                "llm_response_preview": (r.get("answer_preview") or "")[:200],
                "stage_failures": dc.get("stage_failures") or [],
                "rejections": (dc.get("rejections") or [])[:5],
            }
        )
    return {"queries_run": len(rows), "results": rows}
