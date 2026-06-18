"""
Block or defer KB chat while document indexing is still running.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def list_pending_index_jobs(user_id: str) -> List[Dict[str, Any]]:
    try:
        from backend.app.core.index_jobs import list_active_jobs

        return list_active_jobs(str(user_id))
    except Exception:
        return []


def kb_indexing_block_message(user_id: str) -> Optional[str]:
    """
    Return a user-facing message when KB queries would run against a stale or empty index.
    None means safe to proceed.
    """
    jobs = list_pending_index_jobs(user_id)
    if not jobs:
        return None

    names = [str(j.get("filename") or "document") for j in jobs[:3]]
    label = ", ".join(names)
    if len(jobs) > 3:
        label += f" (+{len(jobs) - 3} more)"

    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "A",
            "kb_index_gate.py:kb_indexing_block_message",
            "indexing_in_progress",
            {"job_count": len(jobs), "filenames": names[:3]},
        )
    except Exception:
        pass
    # endregion

    return (
        "### Indexing in progress\n\n"
        f"Your upload **{label}** is still being indexed. "
        "Answers use only documents that are already in the search index — "
        "waiting avoids wrong or generic replies from older files.\n\n"
        "1. Open **Documents** and wait until indexing shows **complete**.\n"
        "2. Ask your question again in **Knowledge Base** mode.\n\n"
        "_Small PDFs (≤30 pages) are usually indexed immediately on upload._"
    )


def check_kb_ready_for_query(
    user_id: str,
    *,
    matter_id: Optional[str] = None,
    retrieval_scope: str = "global",
) -> Tuple[bool, Optional[str]]:
    """(ready, block_message) — ready=True when chat may query the KB."""
    blocked = kb_indexing_block_message(user_id)
    if blocked:
        return False, blocked

    scope = (retrieval_scope or "global").strip().lower()
    strict_matter = scope == "matter"

    try:
        from app import resolve_rag_index_dir, get_scoped_document_count
        from rag import index_exists
        from backend.app.core.faiss_index_stats import count_index_vectors

        index_dir = resolve_rag_index_dir(
            user_id,
            matter_id if strict_matter else None,
            require_matter_scope=strict_matter,
            retrieval_scope=scope,
        )
        doc_count = get_scoped_document_count(
            user_id, matter_id if strict_matter else None
        )
        if doc_count == 0 and not strict_matter:
            return True, None
        if doc_count == 0 and strict_matter:
            return (
                False,
                "### Matter not indexed\n\n"
                "This matter has no documents yet. Upload case files in the "
                "**Matter workspace → Knowledge** tab, then re-index.",
            )
        vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
        if vectors > 0:
            return True, None
        # Documents exist but index empty — likely mid-rebuild; soft block
        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "B",
                "kb_index_gate.py:check_kb_ready_for_query",
                "index_empty_with_docs",
                {"doc_count": doc_count, "matter_id": matter_id or ""},
            )
        except Exception:
            pass
        # endregion
        return (
            False,
            "### Knowledge Base not ready\n\n"
            "Documents are saved but not searchable yet. "
            "Wait for indexing on the **Documents** page, or use **Re-index all**, then try again.",
        )
    except Exception:
        return True, None
