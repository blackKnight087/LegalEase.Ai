"""Feedback learning queue — low-confidence and thumbs-down answers for human review."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import execute_script

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feedback_learning_queue (
    queue_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    org_id TEXT DEFAULT '',
    interaction_id TEXT DEFAULT '',
    chat_id TEXT DEFAULT '',
    mode TEXT DEFAULT '',
    query_text TEXT DEFAULT '',
    answer_text TEXT DEFAULT '',
    signal TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_id TEXT DEFAULT '',
    review_notes TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    reviewed_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_feedback_learning_status ON feedback_learning_queue(status, created_at);
"""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_feedback_learning_schema() -> None:
    conn = connect_data_db()
    execute_script(conn, _SCHEMA_SQL)
    conn.commit()
    conn.close()


def enqueue_feedback(
    user_id: str,
    *,
    signal: str,
    query_text: str = "",
    answer_text: str = "",
    interaction_id: str = "",
    chat_id: str = "",
    mode: str = "",
    confidence: float = 0.0,
    org_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Queue thumbs-down or low-confidence answers for review."""
    ensure_feedback_learning_schema()
    sig = (signal or "").strip().lower()
    if sig not in ("thumbs_down", "low_confidence", "verbal_negative"):
        return {"ok": False, "error": f"signal not queued: {sig}"}

    qid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO feedback_learning_queue
        (queue_id, user_id, org_id, interaction_id, chat_id, mode, query_text,
         answer_text, signal, confidence, status, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (
            qid,
            str(user_id),
            org_id,
            interaction_id,
            chat_id,
            mode,
            (query_text or "")[:8000],
            (answer_text or "")[:16000],
            sig,
            float(confidence or 0),
            json.dumps(metadata or {}),
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "queue_id": qid, "status": "pending"}


def list_review_queue(
    *,
    status: str = "pending",
    limit: int = 50,
    user_id: str = "",
) -> List[Dict[str, Any]]:
    ensure_feedback_learning_schema()
    limit = max(1, min(limit, 200))
    conn = connect_data_db()
    if user_id:
        rows = conn.execute(
            """
            SELECT queue_id, user_id, mode, query_text, answer_text, signal, confidence,
                   status, created_at, interaction_id
            FROM feedback_learning_queue
            WHERE user_id = ? AND status = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT queue_id, user_id, mode, query_text, answer_text, signal, confidence,
                   status, created_at, interaction_id
            FROM feedback_learning_queue
            WHERE status = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (status, limit),
        ).fetchall()
    conn.close()
    return [
        {
            "queue_id": r[0],
            "user_id": r[1],
            "mode": r[2],
            "query_text": (r[3] or "")[:500],
            "answer_text": (r[4] or "")[:800],
            "signal": r[5],
            "confidence": r[6],
            "status": r[7],
            "created_at": r[8],
            "interaction_id": r[9],
        }
        for r in rows
    ]


def review_item(
    queue_id: str,
    reviewer_id: str,
    *,
    action: str,
    notes: str = "",
) -> Dict[str, Any]:
    ensure_feedback_learning_schema()
    action = (action or "").strip().lower()
    if action not in ("approve", "reject"):
        return {"ok": False, "error": "action must be approve or reject"}
    status = "approved" if action == "approve" else "rejected"
    now = _utc()
    conn = connect_data_db()
    cur = conn.execute(
        """
        UPDATE feedback_learning_queue
        SET status = ?, reviewer_id = ?, review_notes = ?, reviewed_at = ?
        WHERE queue_id = ? AND status = 'pending'
        """,
        (status, reviewer_id, (notes or "")[:2000], now, queue_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return {"ok": False, "error": "item not found or already reviewed"}
    return {"ok": True, "queue_id": queue_id, "status": status}
