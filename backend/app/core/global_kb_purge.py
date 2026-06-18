"""Purge matter documents from Global KB when a matter is deleted."""
from __future__ import annotations

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


def list_matter_document_ids(user_id: str, matter_id: str) -> List[str]:
    """Document row ids still linked to a matter before delete."""
    try:
        from backend.app.core.database import connect_data_db

        conn = connect_data_db()
        rows = conn.execute(
            """
            SELECT id FROM documents
            WHERE uploader_id = ? AND matter_id = ?
            """,
            (str(user_id), str(matter_id)),
        ).fetchall()
        conn.close()
        return [str(r[0]) for r in rows if r and r[0]]
    except Exception as exc:
        logger.warning("list_matter_document_ids failed: %s", exc)
        return []


def purge_matter_documents_on_delete(user_id: str, matter_id: str) -> Tuple[int, str]:
    """
    Delete all documents for a matter and rebuild the Global KB index so stale
    FAISS vectors from former matter PDFs cannot appear in Knowledge Base answers.
    """
    doc_ids = list_matter_document_ids(user_id, matter_id)
    deleted = 0
    if doc_ids:
        from app import delete_user_document

        for doc_id in doc_ids:
            try:
                if delete_user_document(doc_id, str(user_id)):
                    deleted += 1
            except Exception as exc:
                logger.warning("delete_user_document %s failed: %s", doc_id, exc)

    try:
        from backend.app.core.faiss_recovery import rebuild_index
        from backend.app.core.kb_cache import invalidate_index_cache
        from backend.app.core.matter_index import get_global_kb_index_dir
        from rag import _invalidate_faiss_vs_cache

        index_dir = get_global_kb_index_dir(str(user_id))
        ok, msg = rebuild_index(str(user_id), matter_id="", use_ocr=None)
        try:
            invalidate_index_cache(index_dir)
            _invalidate_faiss_vs_cache(index_dir)
        except Exception:
            pass
        logger.info(
            "[GLOBAL_KB_PURGE] matter=%s deleted_docs=%s rebuild_ok=%s msg=%s",
            matter_id[:8],
            deleted,
            ok,
            (msg or "")[:120],
        )
        return deleted, str(msg or "")
    except Exception as exc:
        logger.exception("[GLOBAL_KB_PURGE] rebuild failed for matter %s", matter_id)
        return deleted, str(exc)[:200]
