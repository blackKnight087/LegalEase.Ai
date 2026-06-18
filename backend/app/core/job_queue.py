"""Redis-backed job queue for heavy e-discovery batches."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.saas_schema import ensure_saas_schema

QUEUE_KEY = "legalease:ediscovery:queue"


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


def enqueue_ediscovery_job(
    user_id: str,
    matter_id: str,
    batch_title: str,
    documents: List[Dict[str, str]],
) -> Dict[str, Any]:
    ensure_saas_schema()
    jid = str(uuid.uuid4())
    now = _utc()
    payload = {"documents": documents}
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ediscovery_jobs
        (job_id, user_id, matter_id, batch_title, payload_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'QUEUED', ?, ?)
        """,
        (jid, str(user_id), matter_id, batch_title, json.dumps(payload), now, now),
    )
    conn.commit()
    conn.close()
    r = _redis()
    if r:
        r.lpush(QUEUE_KEY, jid)
        return {"job_id": jid, "status": "QUEUED", "worker": "redis"}
    return {"job_id": jid, "status": "QUEUED", "worker": "inline", "note": "Run: py scripts/ediscovery_worker.py"}


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT job_id, batch_id, matter_id, batch_title, status, progress,
               result_json, error_message, created_at, updated_at
        FROM ediscovery_jobs WHERE job_id=?
        """,
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    result = {}
    try:
        result = json.loads(row[6] or "{}")
    except json.JSONDecodeError:
        pass
    return {
        "job_id": row[0],
        "batch_id": row[1],
        "matter_id": row[2],
        "batch_title": row[3],
        "status": row[4],
        "progress": row[5],
        "result": result,
        "error_message": row[7],
        "created_at": row[8],
        "updated_at": row[9],
    }


def update_job(job_id: str, **fields: Any) -> None:
    ensure_saas_schema()
    allowed = {"status", "progress", "result_json", "error_message", "batch_id"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _utc()
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn = connect_data_db()
    conn.execute(
        f"UPDATE ediscovery_jobs SET {sets} WHERE job_id = ?",
        (*updates.values(), job_id),
    )
    conn.commit()
    conn.close()


def pop_job_id(block_seconds: int = 5) -> Optional[str]:
    r = _redis()
    if not r:
        return None
    item = r.brpop(QUEUE_KEY, timeout=block_seconds)
    if item:
        return item[1]
    return None


def process_job(job_id: str) -> Dict[str, Any]:
    from backend.app.core.ediscovery_service import create_evidence_batch

    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT user_id, matter_id, batch_title, payload_json FROM ediscovery_jobs WHERE job_id=?",
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {"error": "Job not found"}
    user_id, matter_id, title, payload_raw = row
    update_job(job_id, status="RUNNING", progress=10)
    try:
        payload = json.loads(payload_raw or "{}")
        docs = payload.get("documents") or []
        update_job(job_id, progress=40)
        result = create_evidence_batch(user_id, matter_id, title, docs)
        update_job(
            job_id,
            status="COMPLETED",
            progress=100,
            result_json=json.dumps(result),
            batch_id=result.get("batch_id", ""),
        )
        return result
    except Exception as exc:
        update_job(job_id, status="FAILED", error_message=str(exc)[:500])
        return {"error": str(exc)}
