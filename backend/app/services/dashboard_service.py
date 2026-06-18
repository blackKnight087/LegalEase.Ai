"""Unified workspace dashboard — KPIs, practice suite, recent activity."""
from __future__ import annotations

from typing import Any, Dict, List

from backend.app.core.adaptive_learning import ensure_learning_schema, learning_stats
from backend.app.core.chat_persistence import ensure_chat_schema, list_chat_threads
from backend.app.core.document_db import get_knowledge_base_status
from backend.app.services.practice_dashboard import practice_overview


def _user_counts(user_id: str) -> Dict[str, int]:
    try:
        from app import run_query

        docs = run_query(
            "SELECT COUNT(*) FROM documents WHERE uploader_id = ?",
            (user_id,),
            fetch=True,
        )
        queries = run_query(
            "SELECT COUNT(*) FROM chat_history WHERE user_id = ?",
            (user_id,),
            fetch=True,
        )
        return {
            "documents": int(docs[0][0]) if docs else 0,
            "queries": int(queries[0][0]) if queries else 0,
        }
    except Exception:
        return {"documents": 0, "queries": 0}


def _recent_documents(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        from app import run_query

        rows = run_query(
            """SELECT id, filename, pages, uploaded_at
            FROM documents WHERE uploader_id = ?
            ORDER BY uploaded_at DESC LIMIT ?""",
            (user_id, limit),
            fetch=True,
        ) or []
        return [
            {
                "id": str(r[0]),
                "filename": r[1],
                "pages": r[2],
                "uploaded_at": r[3],
            }
            for r in rows
        ]
    except Exception:
        return []


def _llm_online() -> bool:
    try:
        from llms import generator_status

        gen = generator_status() or {}
        return bool(gen.get("online") or gen.get("available"))
    except Exception:
        return False


def _embedding_status() -> Dict[str, Any]:
    try:
        from backend.app.core.embedding_manager import get_manager

        mgr = get_manager()
        st = mgr.get_status()
        return {
            "state": st.get("state") or "unknown",
            "ready": st.get("state") == "READY",
            "model": st.get("model") or st.get("model_name") or "",
            "device": st.get("device") or "cpu",
        }
    except Exception:
        return {"state": "unknown", "ready": False, "model": "", "device": "cpu"}


def get_dashboard_full(
    user_id: str,
    *,
    username: str = "",
    membership: str = "",
) -> Dict[str, Any]:
    uid = str(user_id)
    ensure_chat_schema()
    counts = _user_counts(uid)
    kb = get_knowledge_base_status(uid) or {}
    practice = practice_overview(uid)

    learning_summary: Dict[str, Any] = {}
    try:
        ensure_learning_schema()
        learn = learning_stats(uid)
        learning_summary = learn.get("summary") or {}
        learning_summary["modes_count"] = len(learn.get("modes") or [])
    except Exception:
        pass

    recent_threads: List[Dict[str, Any]] = []
    for row in list_chat_threads(uid, limit=8):
        tid, question, answer, mode, language, created_at = row[:6]
        matter_id = str(row[6] or "") if len(row) > 6 else ""
        recent_threads.append(
            {
                "thread_id": str(tid),
                "question": (question or "")[:200],
                "preview": (answer or "")[:280],
                "mode": mode or "knowledge_base",
                "language": language or "English",
                "created_at": created_at,
                "matter_id": matter_id,
            }
        )

    return {
        "username": username,
        "membership": membership,
        "documents": counts["documents"],
        "queries": counts["queries"],
        "kb_status": kb.get("status", "empty"),
        "kb_chunks": kb.get("total_chunks", 0),
        "kb_documents": kb.get("total_documents", 0),
        "kb_last_updated": kb.get("last_updated"),
        "llm_online": _llm_online(),
        "embedding": _embedding_status(),
        "recent_queries": recent_threads,
        "recent_documents": _recent_documents(uid),
        "practice": practice,
        "learning": learning_summary,
    }
