"""Legal watchlist — hearings, gazettes, sections to monitor."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import LegacyConnection, use_postgres_legacy


def _connect():
    conn = connect_data_db(timeout=15)
    if not isinstance(conn, LegacyConnection) and use_postgres_legacy() is False:
        conn.row_factory = sqlite3.Row
    return conn


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_watchlist_schema() -> None:
    if use_postgres_legacy():
        from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

        ensure_pg_rest_schema()
        return
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS legal_watchlist (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT DEFAULT '',
            watch_type TEXT NOT NULL,
            label TEXT NOT NULL,
            query TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            last_checked TEXT,
            last_result TEXT,
            created_at TEXT
        )"""
        )
        conn.commit()
    finally:
        conn.close()


def add_watch(
    user_id: str,
    *,
    watch_type: str,
    label: str,
    query: str,
    matter_id: str = "",
) -> Dict[str, Any]:
    ensure_watchlist_schema()
    wid = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO legal_watchlist
            (id, user_id, matter_id, watch_type, label, query, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (wid, str(user_id), matter_id, watch_type, label, query, _utc()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "id": wid}


def list_watches(user_id: str, matter_id: str = "") -> List[Dict[str, Any]]:
    ensure_watchlist_schema()
    conn = _connect()
    try:
        if matter_id:
            rows = conn.execute(
                """SELECT id, watch_type, label, query, matter_id, active, last_checked, last_result
                FROM legal_watchlist WHERE user_id=? AND matter_id=? ORDER BY created_at DESC""",
                (str(user_id), matter_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, watch_type, label, query, matter_id, active, last_checked, last_result
                FROM legal_watchlist WHERE user_id=? ORDER BY created_at DESC LIMIT 50""",
                (str(user_id),),
            ).fetchall()
        cols = [
            "id",
            "watch_type",
            "label",
            "query",
            "matter_id",
            "active",
            "last_checked",
            "last_result",
        ]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def remove_watch(user_id: str, watch_id: str) -> Dict[str, Any]:
    ensure_watchlist_schema()
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM legal_watchlist WHERE user_id=? AND id=?",
            (str(user_id), watch_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def check_watch(user_id: str, watch_id: str) -> Dict[str, Any]:
    """Run Gemini grounded check for one watch item."""
    ensure_watchlist_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT query, label FROM legal_watchlist WHERE user_id=? AND id=?",
            (str(user_id), watch_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": "not found"}

    try:
        from backend.app.core.web_intelligence import run_grounded_legal_research

        query_text = row[1] if isinstance(row, (tuple, list)) else row["query"]
        answer, sources, _ = run_grounded_legal_research(query_text, user_id=user_id)
        snippet = answer[:800]
        conn = _connect()
        try:
            conn.execute(
                "UPDATE legal_watchlist SET last_checked=?, last_result=? WHERE id=?",
                (_utc(), snippet, watch_id),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "result": snippet, "sources": sources[:5]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
