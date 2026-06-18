"""P2 SaaS schema: password reset tokens, onboarding flags."""
from __future__ import annotations

import sqlite3

from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import use_postgres_legacy
from backend.app.core.p0_saas_schema import ensure_p0_saas_schema


def ensure_p2_saas_schema() -> None:
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema
        from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

        ensure_pg_core_schema()
        ensure_pg_rest_schema()
        return
    ensure_p0_saas_schema()
    conn = connect_data_db()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reset_user ON password_reset_tokens(user_id);

        CREATE TABLE IF NOT EXISTS user_onboarding (
            user_id TEXT PRIMARY KEY,
            dismissed INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """
    )
    _migrate_users_terms(c)
    conn.commit()
    conn.close()


def _migrate_users_terms(c: sqlite3.Cursor) -> None:
    if not c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users' LIMIT 1"
    ).fetchone():
        return
    cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "accepted_terms_at" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN accepted_terms_at TEXT DEFAULT ''")
