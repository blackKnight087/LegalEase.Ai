"""P1 ops schema: audit log, ML jobs, user suspension."""
from __future__ import annotations

import sqlite3

from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import use_postgres_legacy
from backend.app.core.p2_saas_schema import ensure_p2_saas_schema


def ensure_saas_ops_schema() -> None:
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema
        from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

        ensure_pg_core_schema()
        ensure_pg_rest_schema()
        return
    try:
        from legalease_auth import ensure_db

        ensure_db()
    except Exception:
        pass
    ensure_p2_saas_schema()
    conn = connect_data_db()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT '',
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user_id);

        CREATE TABLE IF NOT EXISTS ml_jobs (
            job_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            job_type TEXT NOT NULL,
            payload_json TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'QUEUED',
            progress INTEGER DEFAULT 0,
            result_json TEXT DEFAULT '',
            error_message TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ml_jobs_status ON ml_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_ml_jobs_user ON ml_jobs(user_id);
        """
    )
    cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "suspended" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()
