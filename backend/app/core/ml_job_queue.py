"""Redis-backed ML improvement jobs (off API hot path)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.saas_ops_schema import ensure_saas_ops_schema

ML_QUEUE_KEY = "legalease:ml:queue"
ML_USER_LOCK_PREFIX = "legalease:ml:lock:"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redis():
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis

        c = redis.from_url(url, decode_responses=True)
        c.ping()
        return c
    except Exception:
        return None


def ml_queue_available() -> bool:
    return _redis() is not None


def should_use_ml_queue() -> bool:
    """Prefer queue over in-process threads when Redis is set or ML_USE_QUEUE=1."""
    if os.getenv("ML_USE_QUEUE", "").lower() in {"1", "true", "yes"}:
        return True
    if os.getenv("ML_USE_QUEUE", "").lower() in {"0", "false", "no"}:
        return False
    return bool(os.getenv("REDIS_URL", "").strip()) or ml_queue_available()


def _try_acquire_user_lock(user_id: str, job_id: str) -> bool:
    r = _redis()
    if not r:
        return True
    key = f"{ML_USER_LOCK_PREFIX}{user_id}"
    return bool(r.set(key, job_id, nx=True, ex=7200))


def _release_user_lock(user_id: str) -> None:
    r = _redis()
    if r:
        r.delete(f"{ML_USER_LOCK_PREFIX}{user_id}")


def user_has_active_ml_job(user_id: str) -> bool:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT 1 FROM ml_jobs
        WHERE user_id = ? AND status IN ('QUEUED', 'RUNNING')
        LIMIT 1
        """,
        (str(user_id),),
    ).fetchone()
    conn.close()
    return bool(row)


def enqueue_ml_job(
    user_id: str,
    job_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_saas_ops_schema()
    uid = str(user_id)
    if user_has_active_ml_job(uid):
        return {"ok": False, "error": "ML job already queued or running", "deduped": True}
    jid = str(uuid.uuid4())
    if not _try_acquire_user_lock(uid, jid):
        return {"ok": False, "error": "ML job already queued or running", "deduped": True}
    now = _utc()
    body = json.dumps(payload or {})
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ml_jobs
        (job_id, user_id, job_type, payload_json, status, progress, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'QUEUED', 0, ?, ?)
        """,
        (jid, uid, job_type, body, now, now),
    )
    conn.commit()
    conn.close()
    r = _redis()
    if r:
        r.lpush(ML_QUEUE_KEY, jid)
        return {"ok": True, "job_id": jid, "status": "QUEUED", "worker": "redis"}
    return {
        "ok": True,
        "job_id": jid,
        "status": "QUEUED",
        "worker": "sqlite_poll",
        "note": "Start: py scripts/ml_worker.py",
    }


def get_ml_job(job_id: str) -> Optional[Dict[str, Any]]:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT job_id, user_id, job_type, status, progress, result_json, error_message, created_at, updated_at
        FROM ml_jobs WHERE job_id = ?
        """,
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    result = {}
    try:
        result = json.loads(row[5] or "{}")
    except json.JSONDecodeError:
        pass
    return {
        "job_id": row[0],
        "user_id": row[1],
        "job_type": row[2],
        "status": row[3],
        "progress": row[4],
        "result": result,
        "error_message": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }


def list_user_ml_jobs(user_id: str, limit: int = 10) -> list:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT job_id, job_type, status, progress, created_at, updated_at
        FROM ml_jobs WHERE user_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (str(user_id), int(limit)),
    ).fetchall()
    conn.close()
    return [
        {
            "job_id": r[0],
            "job_type": r[1],
            "status": r[2],
            "progress": r[3],
            "created_at": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]


def _update_ml_job(job_id: str, **fields: Any) -> None:
    ensure_saas_ops_schema()
    allowed = {"status", "progress", "result_json", "error_message"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _utc()
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn = connect_data_db()
    conn.execute(f"UPDATE ml_jobs SET {sets} WHERE job_id = ?", (*updates.values(), job_id))
    conn.commit()
    conn.close()


def pop_ml_job_id(block_seconds: int = 3) -> Optional[str]:
    r = _redis()
    if not r:
        return None
    item = r.brpop(ML_QUEUE_KEY, timeout=block_seconds)
    if item:
        return item[1]
    return None


def poll_ml_job_sqlite() -> Optional[str]:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT job_id FROM ml_jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1"
    ).fetchone()
    conn.close()
    return str(row[0]) if row else None


def process_ml_job(job_id: str) -> Dict[str, Any]:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT user_id, job_type, payload_json FROM ml_jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {"error": "Job not found"}
    user_id, job_type, payload_raw = row
    uid = str(user_id)
    _update_ml_job(job_id, status="RUNNING", progress=5)
    try:
        payload = json.loads(payload_raw or "{}")
        if job_type == "improvement_pipeline":
            from backend.app.core.improvement_automation import run_full_improvement_pipeline

            result = run_full_improvement_pipeline(
                uid,
                trigger=str(payload.get("trigger") or "feedback"),
                membership=str(payload.get("membership") or "Free"),
                force_export=bool(payload.get("force_export")),
            )
        elif job_type == "neural_train":
            from backend.app.core.neural_finetuning import train_embedding_model

            result = train_embedding_model(uid) or {"ok": True}
        elif job_type == "kb_reindex":
            from app import build_faiss_index

            build_faiss_index(uid)
            result = {"ok": True, "action": "reindex"}
        elif job_type == "ollama_create":
            from backend.app.core.improvement_automation import auto_export_and_create_ollama

            result = auto_export_and_create_ollama(
                uid, force=bool(payload.get("force_export"))
            )
        elif job_type == "coach_cycle":
            from backend.app.core.gemini_ollama_coach import run_coaching_cycle

            result = run_coaching_cycle(
                uid,
                membership=str(payload.get("membership") or "Free"),
                auto_train=bool(payload.get("auto_train", True)),
            )
        elif job_type == "matter_intelligence":
            from backend.app.core.matter_intel_pipeline import run_matter_intelligence_pipeline

            result = run_matter_intelligence_pipeline(
                uid,
                str(payload.get("matter_id") or ""),
                document_id=str(payload.get("document_id") or ""),
                skip_if_running=bool(payload.get("skip_if_running", True)),
            )
        elif job_type in {
            "drafting_agent",
            "discovery_agent",
            "crm_agent",
            "matter_agent",
        }:
            from backend.app.core.ai_agents import run_agent

            result = run_agent(job_type, uid, payload)
        else:
            result = {"error": f"Unknown job type: {job_type}"}
        _update_ml_job(
            job_id,
            status="COMPLETED",
            progress=100,
            result_json=json.dumps(result, default=str),
        )
        _release_user_lock(uid)
        return result
    except Exception as exc:
        _update_ml_job(job_id, status="FAILED", error_message=str(exc)[:500], progress=0)
        _release_user_lock(uid)
        return {"error": str(exc)}
