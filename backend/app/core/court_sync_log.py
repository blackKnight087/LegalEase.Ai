"""Court sync history — append-only log for cause list imports."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import execute_script
from backend.app.core.practice_schema import ensure_practice_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_log_table(conn) -> None:
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS court_sync_log (
            log_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            source TEXT DEFAULT 'paste',
            status TEXT DEFAULT 'ok',
            parsed_count INTEGER DEFAULT 0,
            matched_count INTEGER DEFAULT 0,
            inserted_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            errors TEXT DEFAULT '[]',
            confidence TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_court_sync_log_user ON court_sync_log(user_id, created_at);
        """
    )


def append_court_sync_log(
    user_id: str,
    *,
    source: str = "paste",
    status: str = "ok",
    parsed_count: int = 0,
    matched_count: int = 0,
    inserted_count: int = 0,
    skipped_count: int = 0,
    errors: Optional[List[str]] = None,
    confidence: str = "",
    detail: str = "",
) -> Dict[str, Any]:
    ensure_practice_schema()
    conn = connect_data_db()
    _ensure_log_table(conn)
    lid = str(uuid.uuid4())
    now = _utc()
    conn.execute(
        """
        INSERT INTO court_sync_log
        (log_id, user_id, source, status, parsed_count, matched_count, inserted_count,
         skipped_count, errors, confidence, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lid,
            str(user_id),
            source,
            status,
            parsed_count,
            matched_count,
            inserted_count,
            skipped_count,
            json.dumps(errors or []),
            confidence,
            detail[:2000],
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {"log_id": lid, "created_at": now}


def list_court_sync_history(user_id: str, *, limit: int = 10) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    _ensure_log_table(conn)
    rows = conn.execute(
        """
        SELECT log_id, source, status, parsed_count, matched_count, inserted_count,
               skipped_count, errors, confidence, detail, created_at
        FROM court_sync_log WHERE user_id=?
        ORDER BY created_at DESC LIMIT ?
        """,
        (str(user_id), max(1, min(limit, 50))),
    ).fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            errs = json.loads(r[7] or "[]")
        except Exception:
            errs = []
        out.append(
            {
                "log_id": r[0],
                "source": r[1],
                "status": r[2],
                "parsed_count": r[3],
                "matched_count": r[4],
                "inserted_count": r[5],
                "skipped_count": r[6],
                "errors": errs,
                "confidence": r[8],
                "detail": r[9],
                "created_at": r[10],
            }
        )
    return out


def get_last_court_sync(user_id: str) -> Optional[Dict[str, Any]]:
    items = list_court_sync_history(user_id, limit=1)
    return items[0] if items else None
