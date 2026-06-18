"""Production RAG facade — delegates to existing rag.py pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from intent_engine import classify_intent
from conversation_context import merge_retrieval_query

from rag import (
    query_kb,
    get_last_query_diagnostics,
    get_last_query_error,
    index_exists,
    diagnose_kb_health,
)


def retrieve(
    user_id: str,
    question: str,
    *,
    k: int = 14,
    conversation_history: Optional[List[Dict]] = None,
    index_dir: Optional[Path] = None,
    matter_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    profile = classify_intent(question, conversation_history)
    retrieval_q = merge_retrieval_query(
        question,
        conversation_history,
        intent_expanded=profile.expanded_query or "",
    )
    effective_k = max(k, profile.retrieval_k)
    if index_dir is None:
        from app import resolve_rag_index_dir

        index_dir = resolve_rag_index_dir(user_id, matter_id)
    return query_kb(retrieval_q, k=effective_k, index_dir=index_dir)


def kb_health(user_id: str) -> Dict[str, Any]:
    from app import get_knowledge_base_status, get_user_document_count, get_user_index_dir, run_query
    uid = user_id
    kb = get_knowledge_base_status(uid) or {}
    doc_count = get_user_document_count(uid)
    index_dir = get_user_index_dir(uid)
    indexed = index_exists(index_dir)
    chunks = kb.get("total_chunks", 0)
    report = diagnose_kb_health(
        index_dir=index_dir,
        document_count=doc_count,
        db_chunk_count=chunks,
        db_status=kb.get("status", "unknown"),
    )
    return {
        "llm_ready": True,
        "vector_db_ready": indexed,
        "indexed_docs": doc_count,
        "chunks": chunks,
        "status": kb.get("status", "unknown"),
        "indexed": indexed,
        "diagnostics": report,
        "last_error": get_last_query_error(),
    }
