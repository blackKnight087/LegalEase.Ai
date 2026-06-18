"""
KB / RAG observability — SaaS health, SLA signals, and actionable diagnostics.

Used by /health/ready, /documents/kb/health, upload responses, and monitoring hooks.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Tuple

# SLA targets (configurable via env)
SLA_EMBEDDING_LOAD_SEC = float(os.getenv("SLA_EMBEDDING_LOAD_SEC", "60"))
SLA_UPLOAD_SEC = float(os.getenv("SLA_UPLOAD_SEC", "900"))
SLA_INDEX_MIN_VECTORS = int(os.getenv("SLA_INDEX_MIN_VECTORS", "1"))
SLA_QUERY_P95_SEC = float(os.getenv("SLA_QUERY_P95_SEC", "30"))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _probe_embeddings(*, block: bool = False) -> Dict[str, Any]:
    from llms import ensure_embeddings_background, get_embeddings_status, warmup_embeddings

    ensure_embeddings_background()
    status = get_embeddings_status()
    if status.get("ready"):
        return {
            "embeddings_ok": True,
            "embeddings_error": "",
            "embeddings_model": status.get("model", ""),
            "embeddings_device": status.get("device", "cpu"),
        }

    if not block:
        err = status.get("error") or ""
        if status.get("loading"):
            err = err or "Loading embedding model (usually 10–40s on CPU)…"
        return {
            "embeddings_ok": False,
            "embeddings_error": err,
            "embeddings_model": status.get("model", ""),
            "embeddings_device": status.get("device", "cpu"),
        }

    t0 = time.perf_counter()
    ok = warmup_embeddings()
    elapsed = round(time.perf_counter() - t0, 2)
    status = get_embeddings_status()
    return {
        "embeddings_ok": bool(ok),
        "embeddings_error": status.get("error", "") if not ok else "",
        "embeddings_model": status.get("model", ""),
        "embeddings_device": status.get("device", "cpu"),
        "embeddings_load_sec": elapsed,
        "embeddings_sla_ok": elapsed <= SLA_EMBEDDING_LOAD_SEC if ok else False,
    }


def _embeddings_status_fast() -> Dict[str, Any]:
    """Non-blocking embedding status for KB health UI."""
    from backend.app.core.embedding_manager import get_manager

    get_manager().start_background_load()
    st = get_manager().get_status()
    loading = st["state"] in ("LOADING_MODEL", "RECOVERING", "INDEXING", "EMBEDDING_DOCS")
    if st["state"] == "LOADING_MODEL" and not st.get("error"):
        err = "Loading embedding model (usually 15–90s on CPU)…"
    elif st["state"] == "FAILED":
        err = st.get("error") or "Embedding model unavailable — retrying in background"
    else:
        err = st.get("error") or ""
    return {
        "embeddings_ok": bool(st["ready"]),
        "embeddings_error": err,
        "embeddings_model": st.get("model", ""),
        "embeddings_device": st.get("device", "cpu"),
        "embedding_state": st.get("state", "IDLE"),
    }


def _scope_report(user_id: str) -> List[Dict[str, Any]]:
    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
    from backend.app.core.matter_index import (
        get_global_kb_index_dir,
        get_user_index_dir,
        list_matters_with_documents,
    )

    scopes: List[Dict[str, Any]] = []
    uid = str(user_id)

    unlinked = get_global_kb_index_dir(uid)
    u_vectors = count_index_vectors(unlinked) if index_exists(unlinked) else 0
    scopes.append({
        "scope": "global_kb",
        "label": "Global KB (legal statutes, constitution, case law)",
        "index_path": str(unlinked),
        "index_exists": index_exists(unlinked),
        "faiss_chunks": u_vectors,
    })

    legacy = get_user_index_dir(uid)
    if legacy != unlinked and (index_exists(legacy) or legacy.exists()):
        l_vectors = count_index_vectors(legacy) if index_exists(legacy) else 0
        scopes.append({
            "scope": "legacy",
            "label": "Legacy user index",
            "index_path": str(legacy),
            "index_exists": index_exists(legacy),
            "faiss_chunks": l_vectors,
        })

    for mid in list_matters_with_documents(uid):
        from backend.app.core.matter_index import get_matter_index_dir

        mdir = get_matter_index_dir(uid, mid)
        m_vectors = count_index_vectors(mdir) if index_exists(mdir) else 0
        scopes.append({
            "scope": "matter",
            "matter_id": mid,
            "label": f"Matter {mid[:8]}…",
            "index_path": str(mdir),
            "index_exists": index_exists(mdir),
            "faiss_chunks": m_vectors,
        })

    return scopes


def resolve_active_index_scope(user_id: str, matter_id: Optional[str] = None) -> Dict[str, Any]:
    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
    from backend.app.core.matter_index import get_global_kb_index_dir, resolve_rag_index_dir

    mid = (matter_id or "").strip()
    # Health/diagnostics: always report global KB as primary active scope for KB mode.
    index_dir = get_global_kb_index_dir(user_id)
    scope = "global_kb"
    label = "Global KB"

    vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
    return {
        "index_scope": scope,
        "index_scope_label": label,
        "index_path": str(index_dir),
        "index_exists": index_exists(index_dir),
        "faiss_chunks": vectors,
        "matter_id": mid or None,
    }


def _lightweight_kb_diagnosis(
    *,
    index_path: str,
    document_count: int,
    db_chunk_count: int,
    db_status: str,
    index_exists_on_disk: bool,
    total_faiss_chunks: int = 0,
) -> Dict[str, Any]:
    """Fast health snapshot — avoids importing rag.py (loads embeddings)."""
    issues: List[Dict[str, str]] = []
    if document_count > 0 and not index_exists_on_disk:
        issues.append({
            "severity": "error",
            "message": f"{document_count} document(s) in DB but no FAISS index on disk.",
            "fix": "Click Re-index all on Documents page.",
        })
    if document_count == 0:
        issues.append({
            "severity": "warning",
            "message": "No documents uploaded.",
            "fix": "Upload PDFs under Documents, then click Re-index all.",
        })
    if db_status == "stale" and not (total_faiss_chunks > 0 and db_chunk_count >= total_faiss_chunks):
        issues.append({
            "severity": "warning",
            "message": "Knowledge base status is stale — re-index recommended.",
            "fix": "Click Re-index all on Documents page.",
        })
    healthy = not any(i.get("severity") == "error" for i in issues)
    return {
        "healthy": healthy,
        "issues": issues,
        "index_path": index_path,
        "index_exists": index_exists_on_disk,
        "document_count": document_count,
        "db_chunk_count": db_chunk_count,
        "db_status": db_status,
    }


_KB_OBS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_KB_OBS_CACHE_TTL = float(os.getenv("KB_HEALTH_CACHE_SEC", "8"))
_kb_obs_lock = threading.Lock()


def get_kb_observability(
    user_id: str,
    *,
    matter_id: Optional[str] = None,
    probe_embeddings: bool = False,
) -> Dict[str, Any]:
    """
    Full KB observability snapshot for UI and monitoring.
    """
    cache_key = f"{user_id}:{matter_id or ''}:{int(probe_embeddings)}"
    now = time.perf_counter()
    if not probe_embeddings:
        with _kb_obs_lock:
            hit = _KB_OBS_CACHE.get(cache_key)
            if hit and (now - hit[0]) < _KB_OBS_CACHE_TTL:
                return dict(hit[1])

    from backend.app.core.document_db import get_knowledge_base_status, get_user_document_count

    uid = str(user_id)
    kb = get_knowledge_base_status(uid) or {}
    doc_count = get_user_document_count(uid)
    active = resolve_active_index_scope(uid, matter_id)
    scopes = _scope_report(uid)
    total_faiss = sum(int(s.get("faiss_chunks") or 0) for s in scopes)

    scoped_doc_count = doc_count
    if (matter_id or "").strip():
        try:
            from app import get_scoped_document_count

            scoped_doc_count = get_scoped_document_count(uid, matter_id)
        except Exception:
            pass
        # region agent log
        try:
            from backend.app.core.debug_matter_index_log import matter_index_log

            matter_index_log(
                "H1",
                "kb_observability.py:get_kb_observability",
                "matter_scope_health",
                {
                    "matter_id": str(matter_id)[:36],
                    "matter_documents": scoped_doc_count,
                    "matter_vectors": int(active.get("faiss_chunks") or 0),
                    "index_path": str(active.get("index_path") or ""),
                    "index_exists": bool(active.get("index_exists")),
                    "global_vectors": total_faiss,
                },
            )
        except Exception:
            pass
        # endregion

    db_status = kb.get("status", "unknown")
    if isinstance(db_status, tuple):
        db_status = db_status[0] if db_status else "unknown"
    db_chunks = int(kb.get("total_chunks", 0) or 0)
    # Sync DB row from FAISS only when vectors exist (fast path). Skip when 0 vectors — re-index needed.
    if total_faiss > 0 and (db_chunks == 0 or str(db_status) == "stale"):
        try:
            from backend.app.core.kb_status_sync import sync_kb_status_from_faiss

            sync_kb_status_from_faiss(uid)
            kb = get_knowledge_base_status(uid) or {}
            db_chunks = int(kb.get("total_chunks", 0) or 0)
            db_status = kb.get("status", db_status)
            if isinstance(db_status, tuple):
                db_status = db_status[0] if db_status else "unknown"
            with _kb_obs_lock:
                _KB_OBS_CACHE.pop(cache_key, None)
        except Exception:
            pass

    emb = _probe_embeddings(block=probe_embeddings) if probe_embeddings else _embeddings_status_fast()

    report = _lightweight_kb_diagnosis(
        index_path=active["index_path"],
        document_count=doc_count,
        db_chunk_count=db_chunks,
        db_status=str(db_status),
        index_exists_on_disk=bool(active.get("index_exists")),
        total_faiss_chunks=total_faiss,
    )

    issues: List[Dict[str, str]] = list(report.get("issues") or [])
    recommended: List[str] = []

    if doc_count > 0 and total_faiss == 0:
        issues.append({
            "severity": "error",
            "code": "ZERO_FAISS_CHUNKS",
            "message": f"{doc_count} document(s) uploaded but FAISS has 0 vectors — KB search will fail.",
            "fix": "Click Re-index all on Documents page, or POST /api/v1/documents/index",
        })
        recommended.append("Re-index all documents immediately")

    if not emb.get("embeddings_ok"):
        try:
            from llms import get_embeddings_status

            still_loading = bool(get_embeddings_status().get("loading"))
        except Exception:
            still_loading = "loading" in str(emb.get("embeddings_error", "")).lower()
        if still_loading:
            issues.append({
                "severity": "info",
                "code": "EMBEDDINGS_LOADING",
                "message": emb.get("embeddings_error") or "Embedding model loading…",
                "fix": "Wait ~30s after backend start — no action needed if status turns green.",
            })
        else:
            issues.append({
                "severity": "error",
                "code": "EMBEDDINGS_OFFLINE",
                "message": f"Embedding model not loaded: {emb.get('embeddings_error', 'unknown')}",
                "fix": "Restart backend; ensure sentence-transformers installed; check HF_EMBEDDING_MODEL in .env",
            })
            recommended.append("Restart backend and verify embedding warmup in logs")

    if doc_count > 0 and active["faiss_chunks"] == 0 and total_faiss > 0:
        issues.append({
            "severity": "warning",
            "code": "ACTIVE_SCOPE_EMPTY",
            "message": f"Active scope '{active['index_scope']}' has 0 chunks but other scopes have vectors.",
            "fix": "Upload to correct scope or re-index the active matter/unlinked index",
        })

    cross_enc = os.getenv("RAG_ENABLE_CROSS_ENCODER", "0").lower() in ("1", "true", "yes")
    query_ready = (
        emb.get("embeddings_ok")
        and not any(i.get("severity") == "error" for i in issues)
        and (doc_count == 0 or total_faiss >= SLA_INDEX_MIN_VECTORS)
    )
    healthy = query_ready or (
        emb.get("embedding_state") in ("LOADING_MODEL", "EMBEDDING_DOCS", "INDEXING")
        and doc_count > 0
        and total_faiss >= SLA_INDEX_MIN_VECTORS
    )

    payload = {
        "checked_at": _utc(),
        "healthy": healthy,
        "ready_for_kb_query": query_ready and (active["faiss_chunks"] > 0 or total_faiss > 0),
        "embeddings_ok": emb.get("embeddings_ok", False),
        "embeddings_error": emb.get("embeddings_error", ""),
        "embeddings_model": emb.get("embeddings_model", ""),
        "embeddings_device": emb.get("embeddings_device", "cpu"),
        "embeddings_load_sec": emb.get("embeddings_load_sec"),
        "faiss_chunks": active["faiss_chunks"],
        "faiss_chunks_total": total_faiss,
        "index_scope": active["index_scope"],
        "index_scope_label": active["index_scope_label"],
        "index_path": active["index_path"],
        "index_exists": active["index_exists"],
        "index_scopes": scopes,
        "documents": doc_count,
        "db_chunks": db_chunks,
        "db_status": str(db_status),
        "cross_encoder_enabled": cross_enc,
        "issues": issues,
        "recommended_actions": recommended,
        "sla": {
            "embedding_load_max_sec": SLA_EMBEDDING_LOAD_SEC,
            "upload_max_sec": SLA_UPLOAD_SEC,
            "index_min_vectors": SLA_INDEX_MIN_VECTORS,
            "query_p95_max_sec": SLA_QUERY_P95_SEC,
            "embeddings_within_sla": emb.get("embeddings_sla_ok", True),
        },
        "health": report,
    }
    try:
        from backend.app.core.kb_retrieval_router import get_dual_kb_stats

        payload["dual_kb"] = get_dual_kb_stats(uid, matter_id)
    except Exception:
        pass
    if not probe_embeddings:
        with _kb_obs_lock:
            _KB_OBS_CACHE[cache_key] = (now, dict(payload))
    return payload


def format_upload_index_result(
    *,
    ok: bool,
    index_msg: str,
    index_dir: Path,
    was_dup: bool,
    user_id: str,
    async_pending: bool = False,
) -> Dict[str, Any]:
    """Structured upload/index outcome for API + UI."""
    from rag import count_index_vectors, index_exists

    active = resolve_active_index_scope(user_id)
    vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
    from llms import get_embeddings_status

    emb = get_embeddings_status()
    indexing_ok = bool(ok) and vectors >= SLA_INDEX_MIN_VECTORS

    if was_dup and indexing_ok:
        code = "DUPLICATE_INDEXED"
        severity = "success"
    elif was_dup:
        code = "DUPLICATE"
        severity = "info"
        indexing_ok = False
    elif async_pending:
        code = "INDEXING"
        severity = "info"
        indexing_ok = False
    elif vectors == 0 and not was_dup:
        code = "ZERO_CHUNKS"
        severity = "error"
        indexing_ok = False
    elif not ok:
        code = "INDEX_FAILED"
        severity = "error"
    else:
        code = "OK"
        severity = "success"

    return {
        "indexing_ok": indexing_ok,
        "index_vectors": vectors,
        "index_scope": active["index_scope"],
        "index_scope_label": active["index_scope_label"],
        "index_path": str(index_dir),
        "embeddings_ok": bool(emb.get("ready")),
        "index_message": index_msg,
        "error_code": code,
        "severity": severity,
        "user_action": (
            "No action needed — duplicate skipped."
            if was_dup
            else "Indexing in background — wait on Documents page, then query in chat."
            if async_pending
            else "Click Re-index all with OCR enabled."
            if vectors == 0
            else "Ready for Knowledge Base queries."
            if indexing_ok
            else str(index_msg)
        ),
    }
