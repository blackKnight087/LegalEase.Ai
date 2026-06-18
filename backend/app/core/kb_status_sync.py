"""Keep knowledge_base_status aligned with on-disk FAISS vector counts."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def count_user_faiss_vectors(user_id: str) -> int:
    from backend.app.core.kb_observability import _scope_report

    scopes = _scope_report(str(user_id))
    return sum(int(s.get("faiss_chunks") or 0) for s in scopes)


def sync_kb_status_from_faiss(user_id: str) -> Dict[str, Any]:
    """
    Update knowledge_base_status.total_chunks and status from FAISS on disk.
    Fixes UI showing 0 DB chunks while hundreds of vectors exist, and clears false 'stale'.
    """
    from backend.app.core.document_db import (
        get_kb_status_id,
        get_knowledge_base_status,
        get_user_document_count,
    )
    from backend.app.core.database import connect_data_db
    from backend.app.core.sql_compat import upsert_knowledge_base_status

    uid = str(user_id)
    total_vectors = count_user_faiss_vectors(uid)
    doc_count = get_user_document_count(uid)
    kb = get_knowledge_base_status(uid) or {}
    prev_chunks = int(kb.get("total_chunks") or 0)
    prev_status = str(kb.get("status") or "empty")

    if doc_count == 0 and total_vectors == 0:
        status = "empty"
    elif total_vectors > 0:
        status = "active"
    elif doc_count > 0:
        status = "stale"
    else:
        status = prev_status

    status_id = get_kb_status_id(uid)
    now = _utc_iso()
    conn = connect_data_db()
    try:
        upsert_knowledge_base_status(
            conn,
            status_id=status_id,
            status=status,
            total_documents=doc_count,
            total_chunks=total_vectors,
            last_updated=now,
            created_at=now,
        )
        conn.commit()
    finally:
        conn.close()

    fixed = prev_chunks != total_vectors or (
        prev_status in ("stale", "empty", "error") and status == "active" and total_vectors > 0
    )
    if fixed:
        logger.info(
            "[KB SYNC] user=%s chunks %s→%s status %s→%s",
            uid[:8],
            prev_chunks,
            total_vectors,
            prev_status,
            status,
        )

    return {
        "ok": True,
        "fixed": fixed,
        "total_chunks": total_vectors,
        "total_documents": doc_count,
        "status": status,
        "prev_chunks": prev_chunks,
        "prev_status": prev_status,
    }
