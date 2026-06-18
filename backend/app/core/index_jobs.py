"""
Background document indexing — separate process so API health/login never freeze.

Large PDF re-index runs in a child process (Windows spawn); the FastAPI event loop stays responsive.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import threading
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

def _default_use_process() -> bool:
    """Thread-only by default — subprocess duplicates embeddings and hangs under RAM pressure."""
    if os.getenv("INDEX_JOB_FORCE_PROCESS", "0").lower() not in ("1", "true", "yes"):
        return False
    try:
        from backend.app.core.memory_efficiency import prefer_thread_indexing

        if prefer_thread_indexing():
            return False
    except Exception:
        pass
    return os.getenv("INDEX_JOB_USE_PROCESS", "0").lower() in {"1", "true", "yes"}


_INDEX_WORKERS = 1
_thread_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kb-index-thread")
_process_pool: Optional[ProcessPoolExecutor] = None
_process_pool_lock = threading.Lock()
_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


def _get_process_pool() -> ProcessPoolExecutor:
    global _process_pool
    with _process_pool_lock:
        if _process_pool is None:
            ctx = multiprocessing.get_context("spawn")
            _process_pool = ProcessPoolExecutor(
                max_workers=_INDEX_WORKERS,
                mp_context=ctx,
            )
        return _process_pool


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IndexJobParams:
    user_id: str
    only_doc_ids: Optional[List[str]] = None
    matter_id: str = ""
    use_ocr: Optional[bool] = None
    incremental: bool = True
    rebuild_all: bool = False
    enrich_metadata: bool = False
    filename: str = ""
    doc_id: str = ""


def _params_to_dict(params: IndexJobParams) -> Dict[str, Any]:
    return asdict(params)


def _params_from_dict(data: Dict[str, Any]) -> IndexJobParams:
    return IndexJobParams(**data)


def _update_job(job_id: str, **fields: Any) -> None:
    with _lock:
        row = _jobs.get(job_id)
        if not row:
            return
        row.update(fields)
        row["updated_at"] = _utc()


def _progress_callback(job_id: str) -> Callable[[str], None]:
    def _cb(msg: str) -> None:
        _update_job(job_id, message=str(msg)[:500], status="running")

    return _cb


def _execute_index_build(params: IndexJobParams) -> Dict[str, Any]:
    """
    Heavy indexing — intended to run in a child process (no GIL contention with uvicorn).
    Progress callbacks are not available cross-process; message is set at completion.
    """
    from app import build_faiss_index, get_knowledge_base_status
    from backend.app.core.memory_efficiency import efficient_indexing_mode

    mid = (params.matter_id or "").strip() or None

    with efficient_indexing_mode() as mem_mode:
        if params.rebuild_all and not params.only_doc_ids:
            ok, msg = build_faiss_index(
                params.user_id,
                use_ocr=params.use_ocr,
                enrich_metadata=params.enrich_metadata,
                incremental=False,
                rebuild_all=True,
            )
        elif params.only_doc_ids:
            ok, msg = build_faiss_index(
                params.user_id,
                only_doc_ids=params.only_doc_ids,
                use_ocr=params.use_ocr,
                incremental=params.incremental,
                matter_id=mid,
            )
            if ok:
                from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
                from backend.app.core.matter_index import resolve_rag_index_dir

                index_dir = resolve_rag_index_dir(params.user_id, mid)
                vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
                if vectors == 0:
                    ok, msg = build_faiss_index(
                        params.user_id,
                        only_doc_ids=params.only_doc_ids,
                        use_ocr=params.use_ocr,
                        incremental=False,
                        matter_id=mid,
                    )
                    vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
                if vectors == 0:
                    ok = False
                    msg = (
                        f"{msg} No searchable chunks were created. "
                        "Try Re-index with OCR on, or check PDF text extraction."
                    )
        else:
            ok, msg = build_faiss_index(
                params.user_id,
                use_ocr=params.use_ocr,
                enrich_metadata=params.enrich_metadata,
                incremental=False,
                matter_id=mid,
            )
        if mem_mode.get("level") in ("high", "critical") and ok:
            msg = f"{msg} (efficient mode: batch={mem_mode.get('batch')}, RAM tuned)"

    try:
        from backend.app.core.kb_status_sync import sync_kb_status_from_faiss

        synced = sync_kb_status_from_faiss(params.user_id)
        chunks = int(synced.get("total_chunks") or 0)
    except Exception:
        kb = get_knowledge_base_status(params.user_id) or {}
        chunks = int(kb.get("total_chunks") or 0)
    return {
        "status": "completed" if ok else "failed",
        "ok": bool(ok),
        "message": str(msg or "")[:2000],
        "chunks_added": chunks,
        "indexing_ok": bool(ok),
    }


def _run_index_process(params_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Top-level entry for ProcessPoolExecutor (must be picklable)."""
    # Child process: fast base embeddings, no cross-encoder (keeps API parent responsive).
    os.environ.setdefault("RAG_PREFER_BASE_EMBEDDINGS", "1")
    os.environ.setdefault("RAG_ENABLE_CROSS_ENCODER", "0")
    os.environ.setdefault("LEGALEEASE_SKIP_RAG_WARMUP", "1")
    try:
        params = _params_from_dict(params_dict)
        return _execute_index_build(params)
    except Exception as exc:
        logger.exception("[INDEX_JOB] child process failed")
        return {
            "status": "failed",
            "ok": False,
            "indexing_ok": False,
            "message": str(exc)[:2000],
            "chunks_added": 0,
        }


def _run_index_thread(params: IndexJobParams, job_id: str) -> None:
    from backend.app.core.embedding_manager import EmbeddingManager
    from backend.app.core.faiss_recovery import repair_if_corrupt
    from backend.app.core.matter_index import resolve_rag_index_dir

    mgr = EmbeddingManager.instance()
    mgr.set_index_jobs(1)
    _update_job(job_id, status="running", message="Waiting for embedding model…")
    try:
        if not mgr.wait_until_ready(timeout_sec=120):
            st = mgr.get_status()
            _update_job(
                job_id,
                status="failed",
                ok=False,
                message=f"Embeddings not ready: {st.get('error', 'timeout')}",
            )
            return

        mid = (params.matter_id or "").strip() or None
        index_dir = resolve_rag_index_dir(params.user_id, mid)
        _update_job(job_id, message="Validating FAISS index…")
        repair_if_corrupt(params.user_id, index_dir, matter_id=params.matter_id or "", use_ocr=params.use_ocr)

        cb = _progress_callback(job_id)
        from app import build_faiss_index, get_knowledge_base_status
        from backend.app.core.memory_efficiency import efficient_indexing_mode

        with efficient_indexing_mode():
            if params.rebuild_all and not params.only_doc_ids:
                ok, msg = build_faiss_index(
                    params.user_id,
                    progress_callback=cb,
                    use_ocr=params.use_ocr,
                    enrich_metadata=params.enrich_metadata,
                    incremental=False,
                    rebuild_all=True,
                )
            elif params.only_doc_ids:
                ok, msg = build_faiss_index(
                    params.user_id,
                    progress_callback=cb,
                    only_doc_ids=params.only_doc_ids,
                    use_ocr=params.use_ocr,
                    incremental=params.incremental,
                    matter_id=mid,
                )
                if ok:
                    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
                    from backend.app.core.matter_index import resolve_rag_index_dir

                    index_dir = resolve_rag_index_dir(params.user_id, mid)
                    vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
                    if vectors == 0:
                        cb("Retrying index (no vectors yet)…")
                        ok, msg = build_faiss_index(
                            params.user_id,
                            progress_callback=cb,
                            only_doc_ids=params.only_doc_ids,
                            use_ocr=params.use_ocr,
                            incremental=False,
                            matter_id=mid,
                        )
                        vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
                    if vectors == 0:
                        ok = False
                        msg = (
                            f"{msg} No searchable chunks were created. "
                            "Try Re-index with OCR on, or check PDF text extraction."
                        )
            else:
                ok, msg = build_faiss_index(
                    params.user_id,
                    progress_callback=cb,
                    use_ocr=params.use_ocr,
                    enrich_metadata=params.enrich_metadata,
                    incremental=False,
                    matter_id=mid,
                )

        try:
            from backend.app.core.kb_status_sync import sync_kb_status_from_faiss

            synced = sync_kb_status_from_faiss(params.user_id)
            chunks = int(synced.get("total_chunks") or 0)
        except Exception:
            kb = get_knowledge_base_status(params.user_id) or {}
            chunks = int(kb.get("total_chunks") or 0)
        _update_job(
            job_id,
            status="completed" if ok else "failed",
            ok=bool(ok),
            message=str(msg or "")[:2000],
            chunks_added=chunks,
            indexing_ok=bool(ok),
        )
        logger.info("[INDEX_JOB] %s finished ok=%s chunks=%s", job_id, ok, chunks)
        if ok and params.matter_id and params.doc_id:
            try:
                from backend.app.core.matter_enhancements import post_index_matter_hooks

                post_index_matter_hooks(
                    params.user_id,
                    params.matter_id.strip(),
                    params.doc_id,
                    params.filename or "document",
                )
            except Exception:
                pass
    except Exception as exc:
        logger.exception("[INDEX_JOB] %s failed", job_id)
        _update_job(
            job_id,
            status="failed",
            ok=False,
            indexing_ok=False,
            message=str(exc)[:2000],
        )
    finally:
        mgr.set_index_jobs(-1)


def _invalidate_caches_for_user(user_id: str) -> None:
    try:
        from backend.app.core.kb_cache import invalidate_index_cache
        from backend.app.core.matter_index import resolve_rag_index_dir

        invalidate_index_cache(resolve_rag_index_dir(user_id, None))
    except Exception:
        pass
    try:
        from rag import _invalidate_faiss_vs_cache
        from backend.app.core.matter_index import resolve_rag_index_dir

        _invalidate_faiss_vs_cache(resolve_rag_index_dir(user_id, None))
    except Exception:
        pass


def _finalize_process_job(future: Any, job_id: str, user_id: str) -> None:
    timeout_sec = int(os.getenv("INDEX_JOB_TIMEOUT_SEC", "3600"))
    try:
        result = future.result(timeout=timeout_sec)
        _update_job(job_id, status="running", message="Indexing in background process…")
        _update_job(job_id, **result)
        logger.info("[INDEX_JOB] %s process done status=%s", job_id, result.get("status"))
    except Exception as exc:
        logger.exception("[INDEX_JOB] %s process monitor failed", job_id)
        msg = str(exc)[:2000]
        if "TimeoutError" in type(exc).__name__ or "timed out" in msg.lower():
            msg = (
                f"Indexing timed out after {timeout_sec}s. "
                "Restart backend and use Re-index all (thread mode, no separate process)."
            )
        _update_job(
            job_id,
            status="failed",
            ok=False,
            indexing_ok=False,
            message=msg,
        )
    finally:
        try:
            from backend.app.core.kb_status_sync import sync_kb_status_from_faiss

            sync_kb_status_from_faiss(user_id)
        except Exception:
            pass
        _invalidate_caches_for_user(user_id)


def submit_index_job(params: IndexJobParams) -> str:
    """Queue indexing; returns job_id immediately without blocking the API."""
    use_process = _default_use_process()

    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "user_id": params.user_id,
            "status": "queued",
            "message": "Queued for indexing…",
            "filename": params.filename,
            "doc_id": params.doc_id,
            "matter_id": params.matter_id,
            "ok": False,
            "indexing_ok": False,
            "chunks_added": 0,
            "created_at": _utc(),
            "updated_at": _utc(),
        }

    try:
        from backend.app.core.embedding_queue import enqueue_document

        enqueue_document(
            params.user_id,
            params.doc_id or "",
            filename=params.filename,
            matter_id=params.matter_id,
            use_ocr=params.use_ocr,
            index_job_id=job_id,
        )
    except Exception:
        pass

    if use_process:
        _update_job(job_id, status="running", message="Indexing in separate process (API stays online)…")
        pool = _get_process_pool()
        fut = pool.submit(_run_index_process, _params_to_dict(params))
        threading.Thread(
            target=_finalize_process_job,
            args=(fut, job_id, params.user_id),
            daemon=True,
            name=f"index-finalize-{job_id[:8]}",
        ).start()
    else:
        _update_job(job_id, status="running", message="Indexing in background (shared embedding model)…")
        _thread_executor.submit(_run_index_thread, params, job_id)

    return job_id


def _expire_stale_running_job(row: Dict[str, Any]) -> None:
    if row.get("status") not in ("queued", "running"):
        return
    max_sec = int(os.getenv("INDEX_JOB_MAX_RUNNING_SEC", "5400"))
    try:
        ts = row.get("updated_at") or row.get("created_at")
        if not ts:
            return
        started = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - started).total_seconds()
        if age > max_sec:
            row.update(
                status="failed",
                ok=False,
                indexing_ok=False,
                message=(
                    f"Indexing timed out after {int(age // 60)} minutes. "
                    "Stop and restart backend, then click Re-index all."
                ),
                updated_at=_utc(),
            )
    except Exception:
        pass


def get_index_job(job_id: str, user_id: str = "") -> Optional[Dict[str, Any]]:
    with _lock:
        row = _jobs.get(job_id)
        if not row:
            return None
        if user_id and row.get("user_id") != user_id:
            return None
        _expire_stale_running_job(row)
        return dict(row)


def list_active_jobs(user_id: str) -> List[Dict[str, Any]]:
    with _lock:
        return [
            dict(r)
            for r in _jobs.values()
            if r.get("user_id") == user_id
            and r.get("status") in ("queued", "running")
        ]


def run_in_index_executor(fn: Callable[..., Any], *args: Any, **kwargs: Any):
    """Run a callable on the indexing thread pool (for save-only steps if needed)."""
    return _thread_executor.submit(fn, *args, **kwargs)
