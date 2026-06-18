"""
Per-conversation attachments — PDF/image text scoped to one chat thread only.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_thread_attachment_schema() -> None:
    conn = connect_data_db(foreign_keys=True)
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS thread_attachments (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                file_kind TEXT NOT NULL DEFAULT 'file',
                created_at TEXT NOT NULL,
                UNIQUE(user_id, thread_id)
            )"""
        )
        conn.commit()
    finally:
        conn.close()


def save_thread_attachment(
    user_id: str,
    thread_id: str,
    filename: str,
    content: str,
    *,
    file_kind: str = "file",
) -> Dict[str, str]:
    ensure_thread_attachment_schema()
    tid = (thread_id or "").strip()
    if not tid:
        raise ValueError("thread_id is required")
    text = (content or "").strip()
    if len(text) < 20:
        raise ValueError("No readable text extracted from file")
    att_id = str(uuid.uuid4())
    conn = connect_data_db(foreign_keys=True)
    try:
        conn.execute(
            "DELETE FROM thread_attachments WHERE user_id = ? AND thread_id = ?",
            (user_id, tid),
        )
        conn.execute(
            """INSERT INTO thread_attachments
               (id, user_id, thread_id, filename, content, file_kind, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (att_id, user_id, tid, filename, text[:500_000], file_kind, _utc_iso()),
        )
        conn.commit()
        logger.info("[THREAD_ATTACH] user=%s thread=%s file=%s chars=%s", user_id, tid, filename, len(text))
        return {"id": att_id, "thread_id": tid, "filename": filename}
    finally:
        conn.close()


def load_thread_attachment(user_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
    ensure_thread_attachment_schema()
    tid = (thread_id or "").strip()
    if not tid:
        return None
    conn = connect_data_db(foreign_keys=True)
    try:
        row = conn.execute(
            """SELECT id, filename, content, file_kind, created_at
               FROM thread_attachments WHERE user_id = ? AND thread_id = ?""",
            (user_id, tid),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "filename": row[1],
        "content": row[2],
        "file_kind": row[3],
        "created_at": row[4],
    }


def delete_thread_attachment(user_id: str, thread_id: str) -> bool:
    ensure_thread_attachment_schema()
    tid = (thread_id or "").strip()
    if not tid:
        return False
    conn = connect_data_db(foreign_keys=True)
    try:
        cur = conn.execute(
            "DELETE FROM thread_attachments WHERE user_id = ? AND thread_id = ?",
            (user_id, tid),
        )
        conn.commit()
        return int(cur.rowcount or 0) > 0
    finally:
        conn.close()


def thread_attachment_chunks(user_id: str, thread_id: str) -> List[Dict[str, Any]]:
    att = load_thread_attachment(user_id, thread_id)
    if not att:
        return []
    text = (att.get("content") or "").strip()
    if not text:
        return []
    return [
        {
            "content": text[:120_000],
            "metadata": {
                "filename": att.get("filename", "attachment"),
                "source": "thread_attachment",
                "chunk_index": 0,
            },
            "score": 0.0,
        }
    ]
