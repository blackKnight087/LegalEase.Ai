"""
SQLite chat persistence — shared by FastAPI (no Streamlit import on hot path).
"""
from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from backend.app.core.database import connect_data_db, get_sqlite_path
from backend.app.core.legacy_db import connect_app_db, use_postgres_legacy

DB_PATH = get_sqlite_path()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    return connect_app_db()


def ensure_chat_schema() -> None:
    """Create chat_history + thread_id column if missing."""
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema

        ensure_pg_core_schema()
        return
    conn = connect_data_db(foreign_keys=True)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS chat_history (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT 'English',
        mode TEXT NOT NULL DEFAULT 'knowledge_base',
        created_at TEXT NOT NULL,
        thread_id TEXT
    )"""
    )
    cols = {row[1] for row in c.execute("PRAGMA table_info(chat_history)").fetchall()}
    if "thread_id" not in cols:
        c.execute("ALTER TABLE chat_history ADD COLUMN thread_id TEXT")
    if "matter_id" not in cols:
        c.execute("ALTER TABLE chat_history ADD COLUMN matter_id TEXT DEFAULT ''")
    needs_thread_backfill = c.execute(
        "SELECT 1 FROM chat_history WHERE thread_id IS NULL OR thread_id = '' LIMIT 1"
    ).fetchone()
    if needs_thread_backfill:
        c.execute(
            "UPDATE chat_history SET thread_id = id WHERE thread_id IS NULL OR thread_id = ''"
        )
    conn.commit()
    conn.close()


def save_chat_turn(
    user_id: str,
    question: str,
    answer: str,
    *,
    language: str = "English",
    mode: str = "knowledge_base",
    thread_id: Optional[str] = None,
    matter_id: Optional[str] = None,
) -> Dict[str, str]:
    """Persist one user/assistant exchange. Retries on SQLite lock."""
    ensure_chat_schema()
    chat_id = str(uuid.uuid4())
    tid = (thread_id or "").strip() or str(uuid.uuid4())
    q = (question or "").strip()
    a = (answer or "").strip()
    if not q:
        q = "(empty question)"
    if not a:
        a = "(no response generated)"

    last_exc: Exception | None = None
    for attempt in range(4):
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO chat_history
                (id, user_id, question, answer, language, mode, created_at, thread_id, matter_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    user_id,
                    q,
                    a,
                    language,
                    mode,
                    _utc_iso(),
                    tid,
                    (matter_id or "").strip(),
                ),
            )
            conn.commit()
            logger.info("[CHAT SAVE] user=%s thread=%s chat=%s", user_id, tid, chat_id)
            return {"chat_id": chat_id, "thread_id": tid}
        except Exception as exc:
            last_exc = exc
            locked = "locked" in str(exc).lower()
            if locked and attempt < 3 and not use_postgres_legacy():
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
        finally:
            conn.close()
    raise last_exc or RuntimeError("Failed to save chat turn")


def list_chat_threads(
    user_id: str, limit: int = 50, matter_id: Optional[str] = None
) -> List[Tuple]:
    ensure_chat_schema()
    conn = _connect()
    try:
        cur = conn.cursor()
        mid = (matter_id or "").strip()
        if mid:
            cur.execute(
                """
                SELECT COALESCE(h.thread_id, h.id), h.question, h.answer, h.mode,
                       h.language, h.created_at, COALESCE(h.matter_id, '')
                FROM chat_history h
                INNER JOIN (
                    SELECT COALESCE(thread_id, id) AS tid, MAX(created_at) AS max_created
                    FROM chat_history
                    WHERE user_id = ? AND COALESCE(matter_id, '') = ?
                    GROUP BY tid
                ) latest
                ON COALESCE(h.thread_id, h.id) = latest.tid AND h.created_at = latest.max_created
                WHERE h.user_id = ? AND COALESCE(h.matter_id, '') = ?
                ORDER BY h.created_at DESC
                LIMIT ?
                """,
                (user_id, mid, user_id, mid, limit),
            )
        else:
            cur.execute(
                """
                SELECT COALESCE(h.thread_id, h.id), h.question, h.answer, h.mode, h.language, h.created_at,
                       COALESCE(h.matter_id, '')
                FROM chat_history h
                INNER JOIN (
                    SELECT COALESCE(thread_id, id) AS tid, MAX(created_at) AS max_created
                    FROM chat_history
                    WHERE user_id = ?
                    GROUP BY tid
                ) latest
                ON COALESCE(h.thread_id, h.id) = latest.tid AND h.created_at = latest.max_created
                WHERE h.user_id = ?
                ORDER BY h.created_at DESC
                LIMIT ?
                """,
                (user_id, user_id, limit),
            )
        return cur.fetchall()
    finally:
        conn.close()


def load_chat_thread(user_id: str, thread_id: str) -> List[Tuple]:
    ensure_chat_schema()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, question, answer, mode, language, created_at, COALESCE(matter_id, '')
            FROM chat_history
            WHERE user_id = ? AND (thread_id = ? OR id = ?)
            ORDER BY created_at ASC
            """,
            (user_id, thread_id, thread_id),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_thread_matter_id(user_id: str, thread_id: str) -> str:
    """Return matter_id bound to a thread (from latest turn)."""
    ensure_chat_schema()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT COALESCE(matter_id, '') FROM chat_history
            WHERE user_id = ? AND (thread_id = ? OR id = ?)
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id, thread_id, thread_id),
        ).fetchone()
        return str(row[0] or "") if row else ""
    finally:
        conn.close()


def _delete_thread_auxiliary(user_id: str, thread_id: str) -> None:
    """Remove thread summaries and learning rows tied to this chat."""
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM thread_summaries WHERE user_id = ? AND thread_id = ?",
            (user_id, thread_id),
        )
        try:
            conn.execute(
                "DELETE FROM adaptive_interactions WHERE user_id = ? AND thread_id = ?",
                (user_id, thread_id),
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def delete_chat_thread(user_id: str, thread_id: str) -> int:
    """Delete all turns for a saved thread. Returns number of rows removed."""
    tid = (thread_id or "").strip()
    if not tid:
        return 0
    ensure_chat_schema()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            DELETE FROM chat_history
            WHERE user_id = ? AND (thread_id = ? OR id = ?)
            """,
            (user_id, tid, tid),
        )
        conn.commit()
        deleted = int(cur.rowcount or 0)
    finally:
        conn.close()
    if deleted:
        _delete_thread_auxiliary(user_id, tid)
        try:
            from backend.app.core.thread_attachments import delete_thread_attachment

            delete_thread_attachment(user_id, tid)
        except Exception:
            pass
        logger.info("[CHAT DELETE] user=%s thread=%s rows=%s", user_id, tid, deleted)
    return deleted


def delete_chat_history_for_matter(user_id: str, matter_id: str) -> int:
    """Delete all chat threads bound to a matter. Returns total rows removed."""
    mid = (matter_id or "").strip()
    if not mid:
        return 0
    ensure_chat_schema()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT COALESCE(thread_id, id) AS tid
            FROM chat_history
            WHERE user_id = ? AND COALESCE(matter_id, '') = ?
            """,
            (str(user_id), mid),
        ).fetchall()
    finally:
        conn.close()
    total = 0
    for (tid,) in rows:
        t = str(tid or "").strip()
        if t:
            total += delete_chat_thread(str(user_id), t)
    if total:
        logger.info("[CHAT DELETE] user=%s matter=%s rows=%s", user_id, mid, total)
    return total
