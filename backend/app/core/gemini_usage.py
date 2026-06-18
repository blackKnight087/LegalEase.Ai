"""Gemini API usage tracking and plan-based daily caps."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.database import connect_data_db, is_postgres
from backend.app.core.legacy_db import LegacyConnection, connect_app_db, use_postgres_legacy

_PLAN_LIMITS = {
    "Free": int(os.getenv("GEMINI_DAILY_FREE", "15")),
    "Pro": int(os.getenv("GEMINI_DAILY_PRO", "200")),
    "Legal Pro": int(os.getenv("GEMINI_DAILY_LEGAL_PRO", "1000")),
}

# Google limits are per API key — reserve headroom for Open Law / Hybrid (not coach).
_GEMINI_DAILY_KEY_MAX = int(os.getenv("GEMINI_DAILY_KEY_MAX", "18"))
_GEMINI_RESERVE_USER = int(os.getenv("GEMINI_RESERVE_USER", "10"))


def _connect():
    if use_postgres_legacy():
        return connect_app_db()
    conn = connect_data_db(timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _execute(conn, sql: str, params=()) -> Any:
    if isinstance(conn, LegacyConnection):
        return conn.execute(sql, params)
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def ensure_usage_schema() -> None:
    if is_postgres() and use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema

        ensure_pg_core_schema()
        return
    conn = _connect()
    try:
        if isinstance(conn, LegacyConnection):
            conn.execute(
                """CREATE TABLE IF NOT EXISTS gemini_usage_daily (
                user_id TEXT NOT NULL,
                day TEXT NOT NULL,
                call_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, day)
            )"""
            )
            conn.commit()
        else:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS gemini_usage_daily (
                user_id TEXT NOT NULL,
                day TEXT NOT NULL,
                call_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, day)
            )"""
            )
            conn.commit()
    finally:
        conn.close()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def record_gemini_call(user_id: str, *, count: int = 1) -> None:
    ensure_usage_schema()
    uid = str(user_id)
    day = _today()
    sql = (
        """INSERT INTO gemini_usage_daily (user_id, day, call_count)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET call_count = call_count + ?"""
    )
    conn = _connect()
    try:
        if isinstance(conn, LegacyConnection):
            conn.execute(sql, (uid, day, count, count))
            conn.commit()
        else:
            conn.execute(sql, (uid, day, count, count))
            conn.commit()
    finally:
        conn.close()


def get_key_daily_total() -> int:
    """Total Gemini calls today across all users (one API key)."""
    ensure_usage_schema()
    conn = _connect()
    try:
        if isinstance(conn, LegacyConnection):
            row = conn.execute(
                "SELECT COALESCE(SUM(call_count), 0) FROM gemini_usage_daily WHERE day=?",
                (_today(),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(call_count), 0) FROM gemini_usage_daily WHERE day=?",
                (_today(),),
            ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def get_daily_count(user_id: str) -> int:
    ensure_usage_schema()
    conn = _connect()
    try:
        if isinstance(conn, LegacyConnection):
            row = conn.execute(
                "SELECT call_count FROM gemini_usage_daily WHERE user_id=? AND day=?",
                (str(user_id), _today()),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT call_count FROM gemini_usage_daily WHERE user_id=? AND day=?",
                (str(user_id), _today()),
            ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def plan_limit(membership: str) -> int:
    return _PLAN_LIMITS.get(membership or "Free", _PLAN_LIMITS["Free"])


def check_gemini_allowed(user_id: str, membership: str = "Free") -> Dict[str, Any]:
    try:
        from backend.app.core.plan_enforcement import all_features_free

        if all_features_free():
            used = get_daily_count(user_id)
            return {
                "allowed": True,
                "used": used,
                "limit": 999_999,
                "remaining": 999_999,
                "membership": membership,
            }
    except Exception:
        pass
    used = get_daily_count(user_id)
    limit = plan_limit(membership)
    return {
        "allowed": used < limit,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "membership": membership,
    }


def usage_summary(user_id: str, membership: str = "Free") -> Dict[str, Any]:
    chk = check_gemini_allowed(user_id, membership)
    return {
        "gemini_calls_today": chk["used"],
        "gemini_limit": chk["limit"],
        "gemini_remaining": chk["remaining"],
        "allowed": chk["allowed"],
    }


def assert_gemini_allowed(user_id: str, membership: str = "Free") -> None:
    chk = check_gemini_allowed(user_id, membership)
    if not chk["allowed"]:
        raise RuntimeError(
            f"Daily Gemini limit reached ({chk['limit']} calls). "
            "Upgrade plan or try again tomorrow."
        )
