"""Lightweight auth/DB helpers for FastAPI (no Streamlit import)."""
from __future__ import annotations

import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import bcrypt

# Same database as Streamlit app.py (project root, not legacy_saas/)
ROOT = Path(__file__).resolve().parent.parent


def get_db_path() -> Path:
    return Path(os.getenv("LEGALEASE_DB_PATH", str(ROOT / "legalease.db")))


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_query(query: str, params=(), fetch: bool = False, *, critical: bool = True):
    import logging

    log = logging.getLogger("legalease.db")
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if fetch:
            rows = cur.fetchall()
            conn.close()
            return rows
        conn.commit()
        conn.close()
        return None
    except sqlite3.Error:
        log.exception("SQLite query failed (critical=%s): %s", critical, query[:200])
        conn.close()
        if critical:
            raise
        return [] if fetch else None


def ensure_db() -> None:
    """Create core tables if missing (fast; no ML imports)."""
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash BLOB NOT NULL,
        membership TEXT NOT NULL DEFAULT 'Free',
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT NOT NULL
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS logs (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        action TEXT NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL
    )"""
    )
    conn.commit()
    conn.close()
    try:
        from backend.app.core.schema_migrations import apply_migrations

        apply_migrations(tables=["users"])
    except Exception:
        pass


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def _password_hash_bytes(pw_hash) -> bytes:
    """Normalize SQLite BLOB / PostgreSQL BYTEA (memoryview) for bcrypt."""
    if isinstance(pw_hash, bytes):
        return pw_hash
    if isinstance(pw_hash, memoryview):
        return pw_hash.tobytes()
    if isinstance(pw_hash, bytearray):
        return bytes(pw_hash)
    return bytes(pw_hash)


def verify_password(password: str, pw_hash: bytes) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), _password_hash_bytes(pw_hash))
    except Exception:
        return False


def log_action(user_id: Optional[str], action: str, detail: str = "") -> None:
    run_query(
        "INSERT INTO logs (id, user_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id or "system", action, detail, _utc_iso()),
    )


def create_user(username: str, password: str, membership: str = "Free", role: str = "user") -> bool:
    username = (username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,64}", username):
        return False
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(password)
    try:
        run_query(
            "INSERT INTO users (id, username, password_hash, membership, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, pw_hash, membership, role, _utc_iso()),
        )
        log_action(user_id, "create_user", f"membership={membership}")
        return True
    except Exception as exc:
        if isinstance(exc, sqlite3.IntegrityError):
            return False
        name = type(exc).__name__
        if name == "IntegrityError" or "unique" in str(exc).lower():
            return False
        raise


def authenticate_user(username: str, password: str) -> Optional[Dict]:
    res = run_query(
        "SELECT id, username, password_hash, membership, role FROM users WHERE username = ?",
        (username.strip(),),
        fetch=True,
    )
    if not res:
        return None
    user_id, uname, pw_hash, membership, role = res[0]
    if verify_password(password, pw_hash):
        log_action(user_id, "login", "User logged in")
        return {"id": user_id, "username": uname, "membership": membership, "role": role}
    return None


def get_user_by_id(user_id: str) -> Optional[Dict]:
    res = run_query(
        "SELECT id, username, membership, role FROM users WHERE id = ?",
        (str(user_id),),
        fetch=True,
    )
    if not res:
        return None
    uid, uname, membership, role = res[0]
    return {"id": uid, "username": uname, "membership": membership, "role": role}


def get_membership(user_id: str, fallback: str = "Free") -> str:
    row = get_user_by_id(str(user_id))
    if row and row.get("membership"):
        return str(row["membership"])
    return fallback


def upgrade_user_membership(user_id: str, new_membership: str) -> bool:
    """Update plan tier in DB (used by Stripe webhooks and dev mock upgrade)."""
    valid = {"Free", "Pro", "Legal Pro"}
    plan = (new_membership or "Free").strip()
    if plan not in valid:
        return False
    run_query(
        "UPDATE users SET membership = ? WHERE id = ?",
        (plan, str(user_id)),
    )
    log_action(str(user_id), "upgrade_membership", f"plan={plan}")
    return True
