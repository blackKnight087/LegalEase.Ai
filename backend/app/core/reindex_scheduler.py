"""
Automatic re-index detection and scheduling for stale/empty KB indexes.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AUTO_REINDEX = os.getenv("REINDEX_AUTO_ON_STALE", "1").lower() in {"1", "true", "yes"}
AUTO_REINDEX_ON_STARTUP = os.getenv("REINDEX_AUTO_STARTUP", "0").lower() in {"1", "true", "yes"}


def detect_stale_indexes(user_id: str) -> List[Dict[str, Any]]:
    """Find scopes where documents exist but FAISS has 0 vectors."""
    from backend.app.core.kb_observability import _scope_report
    from app import get_user_document_count, run_query

    stale: List[Dict[str, Any]] = []
    doc_count = get_user_document_count(user_id)
    if doc_count == 0:
        return stale

    scopes = _scope_report(user_id)
    for s in scopes:
        if s.get("index_exists") and int(s.get("faiss_chunks") or 0) == 0:
            stale.append({**s, "reason": "index_exists_zero_vectors"})
        elif not s.get("index_exists") and s.get("scope") in ("unlinked", "legacy"):
            # Check if unlinked docs exist for this scope
            if s.get("scope") == "unlinked":
                row = run_query(
                    "SELECT COUNT(*) FROM documents WHERE uploader_id=? AND COALESCE(matter_id,'')=''",
                    (user_id,),
                    fetch=True,
                )
                n = int(row[0][0]) if row else 0
                if n > 0:
                    stale.append({**s, "reason": "docs_without_index", "doc_count": n})

    if doc_count > 0 and sum(int(s.get("faiss_chunks") or 0) for s in scopes) == 0:
        stale.append({
            "scope": "all",
            "reason": "zero_vectors_global",
            "label": "All scopes empty",
            "doc_count": doc_count,
        })

    return stale


def run_auto_reindex(user_id: str, *, use_ocr: bool = False) -> Dict[str, Any]:
    """Re-index all matters + unlinked for a user."""
    from app import build_faiss_index, get_knowledge_base_status
    from backend.app.core.kb_observability import get_kb_observability

    before = get_kb_observability(user_id)
    ok, msg = build_faiss_index(
        user_id,
        use_ocr=use_ocr,
        enrich_metadata=True,
        incremental=False,
        rebuild_all=True,
    )
    after = get_kb_observability(user_id, probe_embeddings=False)
    kb = get_knowledge_base_status(user_id) or {}
    return {
        "ok": bool(ok),
        "message": str(msg),
        "chunks_before": before.get("faiss_chunks_total", 0),
        "chunks_after": after.get("faiss_chunks_total", 0),
        "db_chunks": kb.get("total_chunks", 0),
    }


def maybe_auto_reindex_on_startup() -> None:
    """Background check: log and optionally re-index users with stale KB."""
    if not AUTO_REINDEX:
        return

    def _worker():
        try:
            from app import run_query

            rows = run_query(
                "SELECT DISTINCT uploader_id FROM documents LIMIT 50",
                fetch=True,
            ) or []
            for row in rows:
                uid = str(row[0])
                stale = detect_stale_indexes(uid)
                if not stale:
                    continue
                logger.warning(
                    "[KB AUTO] User %s has stale index: %s",
                    uid[:8],
                    [s.get("reason") for s in stale],
                )
                if AUTO_REINDEX_ON_STARTUP:
                    result = run_auto_reindex(uid, use_ocr=False)
                    logger.info("[KB AUTO] Re-index user %s: %s", uid[:8], result)
        except Exception as exc:
            logger.warning("[KB AUTO] Startup check failed: %s", exc)

    threading.Thread(target=_worker, daemon=True, name="kb-auto-reindex").start()
