"""
Unified Knowledge Base service — single entry for chat, API, and smoke tests.

Wraps indexing + query so app.py and orchestrator share one code path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def resolve_index(user_id: str, matter_id: Optional[str] = None) -> Path:
    from app import resolve_rag_index_dir

    return resolve_rag_index_dir(user_id, matter_id)


def execute_kb_query(
    user_id: str,
    question: str,
    *,
    conversation_history: Optional[List[Dict]] = None,
    matter_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    session_id: Optional[str] = None,
    k: int = 5,
    find_similar_cases: bool = True,
    retrieval_scope: str = "global",
) -> Tuple[str, List[Dict[str, Any]]]:
    """Primary KB Q&A — global_kb by default; matter scope only when explicitly set."""
    from app import rag_query

    return rag_query(
        user_id,
        question,
        k=k,
        find_similar_cases=find_similar_cases,
        conversation_history=conversation_history,
        thread_id=thread_id,
        matter_id=matter_id,
        session_id=session_id,
        retrieval_scope=retrieval_scope,
    )


def append_source_footer(
    answer: str,
    chunks: List[Dict[str, Any]],
) -> Tuple[str, Dict[str, str]]:
    """Attach primary source metadata for UI citation footer."""
    meta: Dict[str, str] = {"filename": "", "section": ""}
    if not chunks:
        return answer, meta
    top = chunks[0]
    m = top.get("metadata") or {}
    meta["filename"] = str(m.get("filename") or m.get("source_file") or "")
    secs = m.get("section_numbers") or m.get("section") or ""
    if secs:
        meta["section"] = str(secs).split(",")[0].strip()
    body = (answer or "").strip()
    if "**Source File:**" in body or "## Supporting Evidence" in body:
        return body, meta
    if meta["filename"] and meta["filename"] not in body:
        cite = f"\n\n**Source:** {meta['filename']}"
        if meta["section"]:
            cite += f" — Section {meta['section']}"
        body = body + cite
    return body, meta
