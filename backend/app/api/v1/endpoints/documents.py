from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)



from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from fastapi.concurrency import run_in_threadpool



from ....core.auth import get_current_user
from ....core.observability import emit_event

from ....models.response_models import DocumentUploadResponse



router = APIRouter(tags=["documents"])





def _parse_ocr_flag(ocr: str) -> bool | None:
    """True = force OCR, False = skip OCR, None = auto (native text only unless sparse)."""
    v = (ocr or "0").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return None


_ALLOWED_EXT = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
)
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _detect_upload_kind(filename: str, content_type: str, data: bytes) -> tuple[str, str]:
    """
    Returns (kind, normalized_filename) where kind is 'pdf' or 'image'.
    Uses extension, MIME type, and magic bytes (for drag-drop blobs).
    """
    from backend.app.core.document_db import sanitize_filename

    fname = (filename or "").strip()
    lower = fname.lower()
    ctype = (content_type or "").lower().split(";")[0].strip()

    if data[:4] == b"%PDF":
        ext = ".pdf"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        ext = ".png"
    elif data[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        ext = ".gif"
    elif data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        ext = ".webp"
    elif lower.endswith(".pdf") or ctype == "application/pdf":
        ext = ".pdf"
    elif ctype.startswith("image/"):
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/tiff": ".tiff",
        }.get(ctype, ".png")
    else:
        for e in _ALLOWED_EXT:
            if lower.endswith(e):
                ext = e
                break
        else:
            ext = ".pdf"

    if ext == ".pdf":
        kind = "pdf"
    elif ext in _IMAGE_EXT:
        kind = "image"
    else:
        raise ValueError("Supported: PDF, PNG, JPG, WEBP, GIF, BMP, TIFF")

    if not fname or Path(fname).suffix.lower() not in _ALLOWED_EXT:
        fname = f"upload{ext}"
    safe = sanitize_filename(fname, default_ext=ext)
    return kind, safe





@router.post("/kb/sync-status")
async def kb_sync_status(user: Dict[str, Any] = Depends(get_current_user)):
    """Align DB chunk count with on-disk FAISS (fixes 0 DB chunks / stale warning)."""
    from backend.app.core.kb_status_sync import sync_kb_status_from_faiss

    return await run_in_threadpool(sync_kb_status_from_faiss, str(user["id"]))


@router.get("/kb/health")
async def kb_health(
    user: Dict[str, Any] = Depends(get_current_user),
    matter_id: str = Query("", description="Scope health to a specific matter"),
):
    """Knowledge base status — embeddings, FAISS chunks, index scope, SLA signals."""
    from backend.app.core.kb_observability import get_kb_observability

    obs = await run_in_threadpool(
        get_kb_observability,
        str(user["id"]),
        matter_id=matter_id.strip() or None,
        probe_embeddings=False,
    )

    # Optional extras — skip when embeddings still loading to keep /kb/health fast under RAM pressure.
    neural: Dict[str, Any] = {}
    learning: Dict[str, Any] = {}
    if obs.get("embeddings_ok"):
        try:
            from backend.app.core.neural_finetuning import tuning_status

            neural = tuning_status(str(user["id"]))
        except Exception:
            neural = {"enabled": False, "error": "unavailable"}
        try:
            from backend.app.core.learning_engine import get_learning_engine_status

            learning = get_learning_engine_status(str(user["id"]))
        except Exception:
            pass

    emb_ui: Dict[str, Any] = {
        "ready": obs.get("embeddings_ok", False),
        "error": obs.get("embeddings_error", ""),
        "model": obs.get("embeddings_model", ""),
        "device": obs.get("embeddings_device", "cpu"),
        "loading": False,
    }
    queue_snap: Dict[str, Any] = {}
    emb_diag: Dict[str, Any] = {}
    try:
        from backend.app.core.embedding_manager import get_manager

        emb_diag = get_manager().get_status()
        loading_states = ("LOADING_MODEL", "RECOVERING", "EMBEDDING_DOCS", "INDEXING")
        emb_ui["loading"] = bool(emb_diag.get("loading")) or emb_diag.get("state") in loading_states
        emb_ui["state"] = emb_diag.get("state", "IDLE")
        if emb_diag.get("model"):
            emb_ui["model"] = emb_diag.get("model", "")
        if emb_diag.get("ready"):
            emb_ui["ready"] = True
        if emb_diag.get("error"):
            emb_ui["error"] = str(emb_diag.get("error") or "")[:500]
    except Exception as exc:
        emb_diag = {"error": str(exc)[:200], "ready": False, "state": "FAILED"}

    vector_count = int(obs.get("faiss_chunks_total") or obs.get("faiss_chunks") or 0)
    query_ready = bool(
        obs.get("ready_for_kb_query")
        and emb_diag.get("ready")
        and (vector_count > 0 or int(obs.get("documents") or 0) == 0)
    )

    return {
        **obs,
        "embedding_state": emb_ui.get("state", "IDLE"),
        "embedding_model": "ready" if obs.get("embeddings_ok") else emb_ui.get("state", "loading"),
        "queue_size": queue_snap.get("queue_size", 0),
        "failed_docs": queue_snap.get("failed", 0),
        "status": obs.get("db_status", "unknown"),
        "documents": obs.get("documents", 0),
        "chunks": obs.get("db_chunks", 0),
        "index_exists": obs.get("index_exists", False),
        "index_vectors": obs.get("faiss_chunks", 0),
        "embeddings": emb_ui,
        "cross_encoder_enabled": obs.get("cross_encoder_enabled", False),
        "neural_finetuning": neural,
        "learning_engine": learning,
        "embedding_diagnostics": {
            "model_name": emb_diag.get("model_name") or emb_diag.get("model") or "",
            "loaded": bool(emb_diag.get("loaded") or emb_diag.get("ready")),
            "retry_count": int(emb_diag.get("retry_count") or emb_diag.get("load_attempts") or 0),
            "last_error": str(emb_diag.get("last_error") or emb_diag.get("error") or ""),
            "vector_count": vector_count,
            "query_ready": query_ready,
            "state": emb_diag.get("state", "IDLE"),
            "low_resource_mode": bool(emb_diag.get("low_resource_mode")),
        },
    }


@router.post("/kb/reindex-auto")
async def kb_auto_reindex(user: Dict[str, Any] = Depends(get_current_user)):
    """Queue background re-index — never blocks the API (fixes disconnect during Auto-fix)."""
    from fastapi.concurrency import run_in_threadpool

    from backend.app.core.index_jobs import IndexJobParams, submit_index_job
    from backend.app.core.reindex_scheduler import detect_stale_indexes

    uid = str(user["id"])

    from llms import ensure_embeddings_background, get_embeddings_status

    ensure_embeddings_background()
    emb_st = get_embeddings_status()
    emb_ok = bool(emb_st.get("ready"))

    try:
        from backend.app.core.kb_status_sync import sync_kb_status_from_faiss

        await run_in_threadpool(lambda: sync_kb_status_from_faiss(uid))
    except Exception:
        pass

    stale = await run_in_threadpool(lambda: detect_stale_indexes(uid))
    needs_reindex = bool(stale)
    if not needs_reindex:
        try:
            from backend.app.core.document_db import get_knowledge_base_status
            from legalease_auth import run_query

            row = await run_in_threadpool(
                lambda: run_query(
                    "SELECT COALESCE(SUM(pages), 0), COUNT(*) FROM documents WHERE uploader_id = ?",
                    (uid,),
                    fetch=True,
                )
            )
            total_pages = int(row[0][0] or 0) if row else 0
            doc_count = int(row[0][1] or 0) if row else 0
            kb = await run_in_threadpool(lambda: get_knowledge_base_status(uid) or {})
            chunks = int(kb.get("total_chunks") or 0)
            if doc_count > 0 and total_pages >= 40 and chunks < max(80, total_pages // 2):
                needs_reindex = True
                stale = [
                    {
                        "scope": "all",
                        "reason": "underindexed_large_pdf",
                        "pages": total_pages,
                        "chunks": chunks,
                        "doc_count": doc_count,
                    }
                ]
        except Exception:
            pass

    if needs_reindex:
        try:
            from backend.app.core.faiss_recovery import repair_if_corrupt
            from backend.app.core.matter_index import resolve_rag_index_dir

            index_dir = resolve_rag_index_dir(uid, None)
            repair_if_corrupt(uid, index_dir, use_ocr=False)
        except Exception:
            pass

    if not needs_reindex:
        if not emb_ok and emb_st.get("state") not in ("LOADING_MODEL", "RECOVERING", "EMBEDDING_DOCS", "INDEXING"):
            return {
                "ok": False,
                "reindexed": False,
                "message": (
                    f"Embeddings not ready: {emb_st.get('error') or 'restart backend and wait ~60s'}. "
                    "Then retry Auto-fix."
                ),
                "embeddings": emb_st,
                "stale": [],
            }
        msg = (
            "Embeddings loaded. KB index looks healthy."
            if emb_ok
            else "KB index looks healthy. Embeddings still loading in background."
        )
        return {
            "ok": True,
            "reindexed": False,
            "message": msg,
            "stale": [],
            "embeddings": emb_st,
        }

    if not emb_ok and not emb_st.get("loading"):
        return {
            "ok": False,
            "reindexed": False,
            "message": (
                f"Cannot re-index until embeddings load: {emb_st.get('error') or 'unknown'}. "
                "Wait for Embeddings → Loaded on Documents page, then retry."
            ),
            "embeddings": emb_st,
            "stale": stale,
        }

    job_id = submit_index_job(
        IndexJobParams(
            user_id=uid,
            use_ocr=False,
            enrich_metadata=False,
            incremental=False,
            rebuild_all=True,
        )
    )
    return {
        "ok": True,
        "reindexed": True,
        "index_job_id": job_id,
        "message": "Re-index started in background — API stays online.",
        "stale": stale,
        "embeddings": emb_st,
        "chunks_added": 0,
    }


@router.post("/kb/smoke-test")
async def kb_smoke_test(
    user: Dict[str, Any] = Depends(get_current_user),
    matter_id: str = Query("", description="Scope smoke test to matter or unlinked"),
):
    """Run live KB queries against the active index — use after re-index."""
    from fastapi.concurrency import run_in_threadpool

    from backend.app.core.kb_smoke_test import run_kb_smoke_test

    return await run_in_threadpool(
        lambda: run_kb_smoke_test(
            str(user["id"]),
            matter_id=matter_id.strip() or None,
        )
    )





class _UploadAdapter:

    """Mimics Streamlit UploadedFile for save_uploaded_pdf (expects bytes from getbuffer)."""



    def __init__(self, name: str, data: bytes):

        self.name = name

        self._data = bytes(data)



    def getbuffer(self):

        return self._data





@router.get("")

def list_documents(user: Dict[str, Any] = Depends(get_current_user)):

    from backend.app.core.document_db import (
        MAX_UPLOAD_MB,
        get_org_visible_document_count,
        get_user_document_count,
    )
    from backend.app.core.plan_enforcement import document_limit
    from backend.app.core.practice_schema import ensure_practice_schema
    from legalease_auth import run_query

    ensure_practice_schema()

    from backend.app.core.document_db import list_visible_documents

    rows = list_visible_documents(user["id"])

    docs = []

    for r in rows:

        if not r or len(r) < 3:

            continue

        docs.append({

            "id": str(r[0]),

            "filename": str(r[1]) if r[1] is not None else "document.pdf",

            "pages": int(r[2]) if r[2] is not None else 0,

            "uploaded_at": r[3] if len(r) > 3 else None,

            "matter_id": str(r[4]) if len(r) > 4 else "",

        })

    return {

        "documents": docs,

        "count": get_org_visible_document_count(user["id"]),

        "max_upload_mb": MAX_UPLOAD_MB,

        "membership": user["membership"],

        "document_limit": document_limit(user.get("membership", "Free")),

        "free_limit": document_limit("Free"),

    }





@router.post("/upload", response_model=DocumentUploadResponse)

async def upload_document(
    file: UploadFile = File(...),
    ocr: str = Query("0", description="1=force OCR for scanned PDFs, 0=fast native text"),
    matter_id: str = Query("", description="Optional matter to link this document"),
    user: Dict[str, Any] = Depends(get_current_user),
):

    from backend.app.core.document_db import MAX_UPLOAD_MB
    from backend.app.core.plan_enforcement import can_upload_document
    from backend.app.core.document_schema import ensure_document_tables_schema
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_document_tables_schema()
    ensure_practice_schema()
    use_ocr = _parse_ocr_flag(ocr)

    ok_upload, upload_msg = can_upload_document(
        str(user["id"]), str(user.get("membership") or "Free")
    )
    if not ok_upload:
        raise HTTPException(403, upload_msg)

    linked_mid = (matter_id or "").strip()
    if linked_mid:
        from backend.app.core.matter_repo import get_matter_access_context

        ctx = get_matter_access_context(str(user["id"]), linked_mid)
        if not ctx:
            raise HTTPException(404, "Matter not found or access denied")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_UPLOAD_MB} MB limit")

    try:
        kind, safe_name = _detect_upload_kind(
            file.filename or "",
            file.content_type or "",
            data,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    adapter = _UploadAdapter(safe_name, data)
    upload_kind = kind

    def _save_only():
        from app import save_uploaded_pdf

        file_id, _, pages, was_dup = save_uploaded_pdf(
            adapter, user["id"], matter_id=linked_mid
        )
        if linked_mid:
            from backend.app.core.matter_repo import link_document_to_matter

            link_document_to_matter(user["id"], file_id, linked_mid, rebuild_index=False)
        # #region agent log
        try:
            import json
            import time
            from pathlib import Path

            log_path = Path(__file__).resolve().parents[5] / "debug-cf6ca9.log"
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(
                    json.dumps(
                        {
                            "sessionId": "cf6ca9",
                            "runId": "upload-debug",
                            "hypothesisId": "H2",
                            "location": "documents.py:_save_only",
                            "message": "matter_link_after_save",
                            "data": {
                                "file_id": str(file_id)[:12],
                                "matter_id": linked_mid,
                                "was_dup": was_dup,
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        return file_id, pages, was_dup

    try:
        save_timeout = float(os.getenv("PDF_SAVE_TIMEOUT_SEC", "300"))
        file_id, pages, was_dup = await asyncio.wait_for(
            run_in_threadpool(_save_only),
            timeout=save_timeout,
        )
        try:
            from app import run_query

            run_query(
                "UPDATE documents SET index_status = ? WHERE id = ? AND uploader_id = ?",
                ("processing", str(file_id), str(user["id"])),
            )
            emit_event(
                "index_status_transition",
                user_id=str(user["id"]),
                matter_id=linked_mid,
                doc_id=str(file_id),
                from_status="saved",
                to_status="processing",
            )
        except Exception:
            pass
        ok = True
        index_msg = "Already in library — duplicate upload skipped."
        index_job_id = ""
        if was_dup and linked_mid:
            index_msg = f"Existing file linked to this matter — indexing {safe_name}…"
            index_ocr = True if upload_kind == "image" else use_ocr

            def _dup_matter_index():
                from app import build_faiss_index

                return build_faiss_index(
                    str(user["id"]),
                    only_doc_ids=[file_id],
                    use_ocr=index_ocr,
                    incremental=True,
                    matter_id=linked_mid,
                )

            try:
                idx_ok, idx_msg = await asyncio.wait_for(
                    run_in_threadpool(_dup_matter_index),
                    timeout=float(os.getenv("KB_SYNC_INDEX_TIMEOUT_SEC", "120")),
                )
                if idx_ok:
                    ok = True
                    index_msg = f"Linked and indexed in this matter — {safe_name}"
                    try:
                        from app import run_query

                        run_query(
                            "UPDATE documents SET index_status = ? WHERE id = ? AND uploader_id = ?",
                            ("ready", str(file_id), str(user["id"])),
                        )
                    except Exception:
                        pass
                    try:
                        from backend.app.core.matter_enhancements import post_index_matter_hooks

                        post_index_matter_hooks(
                            str(user["id"]), linked_mid, str(file_id), safe_name
                        )
                    except Exception:
                        pass
                    try:
                        from backend.app.core.kb_status_sync import sync_kb_status_from_faiss
                        from backend.app.core.matter_index import resolve_rag_index_dir
                        from backend.app.core.kb_cache import invalidate_index_cache
                        from rag import _invalidate_faiss_vs_cache

                        sync_kb_status_from_faiss(str(user["id"]))
                        _idir = resolve_rag_index_dir(str(user["id"]), linked_mid)
                        invalidate_index_cache(_idir)
                        _invalidate_faiss_vs_cache(_idir)
                    except Exception:
                        pass
                else:
                    from backend.app.core.index_jobs import IndexJobParams, submit_index_job

                    index_job_id = submit_index_job(
                        IndexJobParams(
                            user_id=str(user["id"]),
                            only_doc_ids=[file_id],
                            matter_id=linked_mid,
                            use_ocr=index_ocr,
                            incremental=True,
                            filename=safe_name,
                            doc_id=file_id,
                        )
                    )
                    index_msg = (
                        f"Linked to matter; background indexing started "
                        f"({str(idx_msg)[:60]})."
                    )
                    ok = False
            except asyncio.TimeoutError:
                from backend.app.core.index_jobs import IndexJobParams, submit_index_job

                index_job_id = submit_index_job(
                    IndexJobParams(
                        user_id=str(user["id"]),
                        only_doc_ids=[file_id],
                        matter_id=linked_mid,
                        use_ocr=index_ocr,
                        incremental=True,
                        filename=safe_name,
                        doc_id=file_id,
                    )
                )
                index_msg = f"Linked to matter; indexing in background — {safe_name}"
                ok = False
        elif was_dup:
            index_msg = "Already in library (link this file from Documents → link to matter)."
        if not was_dup:
            from backend.app.core.index_jobs import IndexJobParams, submit_index_job

            index_ocr = True if upload_kind == "image" else use_ocr
            sync_max = int(os.getenv("KB_SYNC_INDEX_MAX_PAGES", "30"))
            page_count = int(pages or 0)
            if page_count > 0 and page_count <= sync_max:

                def _sync_index_now():
                    from app import build_faiss_index

                    return build_faiss_index(
                        str(user["id"]),
                        only_doc_ids=[file_id],
                        use_ocr=index_ocr,
                        incremental=True,
                        matter_id=linked_mid or None,
                    )

                try:
                    idx_ok, idx_msg = await asyncio.wait_for(
                        run_in_threadpool(_sync_index_now),
                        timeout=float(os.getenv("KB_SYNC_INDEX_TIMEOUT_SEC", "120")),
                    )
                    if idx_ok:
                        index_msg = f"Saved and indexed {safe_name} — ready for questions now."
                        ok = True
                        try:
                            from app import run_query

                            run_query(
                                "UPDATE documents SET index_status = ? WHERE id = ? AND uploader_id = ?",
                                ("ready", str(file_id), str(user["id"])),
                            )
                            emit_event(
                                "index_status_transition",
                                user_id=str(user["id"]),
                                matter_id=linked_mid,
                                doc_id=str(file_id),
                                from_status="processing",
                                to_status="ready",
                            )
                        except Exception:
                            pass
                        if linked_mid:
                            try:
                                from backend.app.core.matter_enhancements import (
                                    post_index_matter_hooks,
                                )

                                post_index_matter_hooks(
                                    str(user["id"]),
                                    linked_mid,
                                    str(file_id),
                                    safe_name,
                                )
                            except Exception:
                                pass
                        try:
                            from backend.app.core.kb_status_sync import sync_kb_status_from_faiss
                            from backend.app.core.matter_index import resolve_rag_index_dir
                            from backend.app.core.kb_cache import invalidate_index_cache
                            from rag import _invalidate_faiss_vs_cache

                            sync_kb_status_from_faiss(str(user["id"]))
                            _idir = resolve_rag_index_dir(str(user["id"]), linked_mid or None)
                            invalidate_index_cache(_idir)
                            _invalidate_faiss_vs_cache(_idir)
                        except Exception:
                            pass
                        # region agent log
                        try:
                            from backend.app.core.debug_session_log import debug_log
                            from backend.app.core.faiss_index_stats import count_index_vectors
                            from rag import index_exists

                            _idir = resolve_rag_index_dir(str(user["id"]), linked_mid or None)
                            debug_log(
                                "B",
                                "documents.py:upload_document",
                                "sync_index_complete",
                                {
                                    "doc_id": str(file_id)[:12],
                                    "pages": page_count,
                                    "vectors": count_index_vectors(_idir)
                                    if index_exists(_idir)
                                    else 0,
                                },
                            )
                        except Exception:
                            pass
                        # endregion
                    else:
                        try:
                            from app import run_query

                            run_query(
                                "UPDATE documents SET index_status = ? WHERE id = ? AND uploader_id = ?",
                                ("queued", str(file_id), str(user["id"])),
                            )
                            emit_event(
                                "index_status_transition",
                                user_id=str(user["id"]),
                                matter_id=linked_mid,
                                doc_id=str(file_id),
                                from_status="processing",
                                to_status="queued",
                            )
                        except Exception:
                            pass
                        index_job_id = submit_index_job(
                            IndexJobParams(
                                user_id=str(user["id"]),
                                only_doc_ids=[file_id],
                                matter_id=linked_mid,
                                use_ocr=index_ocr,
                                incremental=True,
                                filename=safe_name,
                                doc_id=file_id,
                            )
                        )
                        index_msg = (
                            f"Saved {safe_name}. Quick index failed ({idx_msg[:80]}); "
                            "background indexing started."
                        )
                        ok = False
                except asyncio.TimeoutError:
                    try:
                        from app import run_query

                        run_query(
                            "UPDATE documents SET index_status = ? WHERE id = ? AND uploader_id = ?",
                            ("queued", str(file_id), str(user["id"])),
                        )
                        emit_event(
                            "index_status_transition",
                            user_id=str(user["id"]),
                            matter_id=linked_mid,
                            doc_id=str(file_id),
                            from_status="processing",
                            to_status="queued",
                        )
                    except Exception:
                        pass
                    index_job_id = submit_index_job(
                        IndexJobParams(
                            user_id=str(user["id"]),
                            only_doc_ids=[file_id],
                            matter_id=linked_mid,
                            use_ocr=index_ocr,
                            incremental=True,
                            filename=safe_name,
                            doc_id=file_id,
                        )
                    )
                    index_msg = (
                        f"Saved {safe_name}. Indexing in background ({page_count} pages) — "
                        "large file; ask again in a minute."
                    )
                    ok = False
            else:
                try:
                    from app import run_query

                    run_query(
                        "UPDATE documents SET index_status = ? WHERE id = ? AND uploader_id = ?",
                        ("queued", str(file_id), str(user["id"])),
                    )
                    emit_event(
                        "index_status_transition",
                        user_id=str(user["id"]),
                        matter_id=linked_mid,
                        doc_id=str(file_id),
                        from_status="processing",
                        to_status="queued",
                    )
                except Exception:
                    pass
                index_job_id = submit_index_job(
                    IndexJobParams(
                        user_id=str(user["id"]),
                        only_doc_ids=[file_id],
                        matter_id=linked_mid,
                        use_ocr=index_ocr,
                        incremental=True,
                        filename=safe_name,
                        doc_id=file_id,
                    )
                )
                index_msg = (
                    f"Saved {safe_name}. Indexing in background "
                    f"({pages or '?'} pages) — you can keep using the app."
                )
                ok = False
        from app import get_knowledge_base_status

        kb = get_knowledge_base_status(user["id"]) or {}
    except asyncio.TimeoutError:
        raise HTTPException(
            504,
            "Upload timed out. For images, ensure OCR_ENABLED=1; for large PDFs try OCR off.",
        ) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("Document upload failed for %s", safe_name)
        try:
            from app import run_query

            if "file_id" in locals() and file_id:
                run_query(
                    "UPDATE documents SET index_status = ? WHERE id = ? AND uploader_id = ?",
                    ("failed", str(file_id), str(user["id"])),
                )
                emit_event(
                    "index_status_transition",
                    user_id=str(user["id"]),
                    matter_id=linked_mid,
                    doc_id=str(file_id),
                    from_status="processing",
                    to_status="failed",
                )
        except Exception:
            pass
        # #region agent log
        try:
            import json
            import traceback
            import time
            from pathlib import Path

            log_path = Path(__file__).resolve().parents[5] / "debug-cf6ca9.log"
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(
                    json.dumps(
                        {
                            "sessionId": "cf6ca9",
                            "hypothesisId": "H-upload",
                            "location": "documents.py:upload_document",
                            "message": "upload_exception",
                            "data": {
                                "file": safe_name,
                                "matter_id": linked_mid,
                                "err": str(e),
                                "trace": traceback.format_exc()[-1200:],
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        detail = str(e)
        if "tuple" in detail.lower() or "unpack" in detail.lower():
            detail = (
                "Indexing failed due to a server error. The file may be saved — "
                "try Re-index all, or restart the backend."
            )
        raise HTTPException(500, detail) from e

    linked_matter = linked_mid if linked_mid else ""

    from backend.app.core.matter_index import resolve_rag_index_dir
    from backend.app.core.kb_observability import format_upload_index_result

    index_dir = resolve_rag_index_dir(user["id"], linked_mid or None)
    async_index = bool(index_job_id)
    index_result = format_upload_index_result(
        ok=bool(ok),
        index_msg=str(index_msg or ""),
        index_dir=index_dir,
        was_dup=was_dup,
        user_id=str(user["id"]),
        async_pending=async_index,
    )
    try:
        from backend.app.core.audit_service import log_audit

        log_audit(
            "document.upload",
            user_id=str(user["id"]),
            detail=f"{safe_name} id={file_id} matter={linked_matter or '-'}",
        )
    except Exception:
        pass
    return DocumentUploadResponse(
        status="success" if was_dup or index_result.get("indexing_ok") else ("processing" if async_index else "warning"),
        document_name=safe_name,
        document_id=file_id,
        matter_id=linked_matter or None,
        pages=pages or 0,
        chunks_added=int(index_result.get("index_vectors") or kb.get("total_chunks", 0)),
        indexed=bool(index_result.get("indexing_ok")),
        index_message=str(index_msg or ""),
        indexing_ok=bool(index_result.get("indexing_ok")),
        index_vectors=int(index_result.get("index_vectors") or 0),
        index_scope=str(index_result.get("index_scope") or "unlinked"),
        index_scope_label=str(index_result.get("index_scope_label") or ""),
        embeddings_ok=bool(index_result.get("embeddings_ok")),
        error_code=str(index_result.get("error_code") or "OK"),
        severity=str(index_result.get("severity") or "success"),
        user_action=str(index_result.get("user_action") or ""),
        index_job_id=index_job_id or None,
        indexing_async=async_index,
    )





@router.get("/jobs/{job_id}")
def get_index_job_status(
    job_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from backend.app.core.index_jobs import get_index_job

    row = get_index_job(job_id, str(user["id"]))
    if not row:
        raise HTTPException(404, "Index job not found")
    return row


@router.get("/jobs")
def list_index_jobs(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.index_jobs import list_active_jobs

    return {"jobs": list_active_jobs(str(user["id"]))}


@router.post("/index")
async def reindex_documents(
    ocr: str = Query("0", description="1=run OCR on sparse PDFs during full re-index"),
    matter_id: str = Query("", description="Re-index only this matter; empty = all matters"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from backend.app.core.index_jobs import IndexJobParams, submit_index_job

    use_ocr = _parse_ocr_flag(ocr)
    mid = (matter_id or "").strip()
    job_id = submit_index_job(
        IndexJobParams(
            user_id=str(user["id"]),
            matter_id=mid,
            use_ocr=use_ocr,
            enrich_metadata=False,
            incremental=False,
            rebuild_all=not mid,
        )
    )
    return {
        "status": "processing",
        "indexed": False,
        "index_job_id": job_id,
        "message": "Re-index started in background — API stays online.",
        "chunks_added": 0,
    }





@router.get("/{doc_id}/timeline")

def document_timeline(doc_id: str, user: Dict[str, Any] = Depends(get_current_user)):

    from app import run_query

    owned = run_query(

        "SELECT id FROM documents WHERE id = ? AND uploader_id = ?",

        (doc_id, user["id"]),

        fetch=True,

    )

    if not owned:

        raise HTTPException(404, "Document not found")

    events = run_query(

        "SELECT event_date, mention_text, page FROM document_timeline WHERE document_id = ? ORDER BY event_date",

        (doc_id,),

        fetch=True,

    ) or []

    return {"events": [{"date": e[0], "text": e[1], "page": e[2]} for e in events]}





@router.get("/{doc_id}/entities")

def document_entities(doc_id: str, user: Dict[str, Any] = Depends(get_current_user)):

    from app import run_query

    owned = run_query(

        "SELECT id FROM documents WHERE id = ? AND uploader_id = ?",

        (doc_id, user["id"]),

        fetch=True,

    )

    if not owned:

        raise HTTPException(404, "Document not found")

    rows = run_query(

        "SELECT plaintiff, defendant, judge, court, case_number, sections FROM case_entities WHERE document_id = ? LIMIT 1",

        (doc_id,),

        fetch=True,

    )

    if not rows:

        return {"entities": None}

    r = rows[0]

    return {

        "entities": {

            "plaintiff": r[0],

            "defendant": r[1],

            "judge": r[2],

            "court": r[3],

            "case_number": r[4],

            "sections": r[5],

        }

    }





@router.delete("/{doc_id}")

def delete_document(doc_id: str, user: Dict[str, Any] = Depends(get_current_user)):

    from app import delete_user_document, build_faiss_index, run_query

    row = run_query(
        "SELECT matter_id FROM documents WHERE id = ? AND uploader_id = ?",
        (doc_id, user["id"]),
        fetch=True,
    )
    scoped_matter = str(row[0][0] or "").strip() if row else ""

    if not delete_user_document(doc_id, user["id"]):
        raise HTTPException(404, "Document not found")

    try:
        from backend.app.core.audit_service import log_audit

        log_audit(
            "document.delete",
            user_id=str(user["id"]),
            detail=f"doc_id={doc_id} matter={scoped_matter or '-'}",
        )
    except Exception:
        pass

    from backend.app.core.index_jobs import IndexJobParams, submit_index_job

    job_id = submit_index_job(
        IndexJobParams(
            user_id=str(user["id"]),
            matter_id=scoped_matter,
            incremental=False,
        )
    )
    return {"status": "deleted", "index_job_id": job_id}
