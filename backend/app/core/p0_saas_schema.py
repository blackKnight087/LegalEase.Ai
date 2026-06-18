"""P0 SaaS schema: organizations, subscriptions, org-scoped matters."""
from __future__ import annotations

import sqlite3

from backend.app.core.database import connect_data_db
from backend.app.core.practice_schema import ensure_practice_schema


def ensure_p0_saas_schema() -> None:
    from backend.app.core.legacy_db import use_postgres_legacy

    ensure_practice_schema()
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema

        ensure_pg_core_schema()
        return
    conn = connect_data_db()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            org_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'Free',
            seat_limit INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS org_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            created_at TEXT NOT NULL,
            UNIQUE(org_id, user_id),
            FOREIGN KEY(org_id) REFERENCES organizations(org_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_org_members_user ON org_members(user_id);
        CREATE INDEX IF NOT EXISTS idx_org_members_org ON org_members(org_id);

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            stripe_customer_id TEXT DEFAULT '',
            stripe_subscription_id TEXT DEFAULT '',
            plan TEXT NOT NULL DEFAULT 'Free',
            status TEXT NOT NULL DEFAULT 'inactive',
            updated_at TEXT NOT NULL,
            UNIQUE(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe ON subscriptions(stripe_subscription_id);

        CREATE TABLE IF NOT EXISTS org_invites (
            invite_id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        """
    )
    _migrate_matters_org_id(c)
    _migrate_org_branding(c)
    _backfill_matters_org_id(c)
    conn.commit()
    conn.close()


def _backfill_matters_org_id(c: sqlite3.Cursor) -> None:
    """Attach legacy matters to owner's primary org when org_id is empty."""
    rows = c.execute(
        "SELECT matter_id, user_id FROM matters WHERE COALESCE(org_id, '') = ''"
    ).fetchall()
    for matter_id, user_id in rows:
        row = c.execute(
            """
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = ? ORDER BY CASE om.role WHEN 'owner' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (str(user_id),),
        ).fetchone()
        if row:
            c.execute(
                "UPDATE matters SET org_id = ? WHERE matter_id = ?",
                (str(row[0]), str(matter_id)),
            )


def _migrate_matters_org_id(c: sqlite3.Cursor) -> None:
    exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='matters' LIMIT 1"
    ).fetchone()
    if not exists:
        return
    cols = {row[1] for row in c.execute("PRAGMA table_info(matters)").fetchall()}
    if "org_id" not in cols:
        c.execute("ALTER TABLE matters ADD COLUMN org_id TEXT DEFAULT ''")
    c.execute("CREATE INDEX IF NOT EXISTS idx_matters_org ON matters(org_id)")


def _migrate_org_branding(c: sqlite3.Cursor) -> None:
    exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='organizations' LIMIT 1"
    ).fetchone()
    if not exists:
        return
    cols = {row[1] for row in c.execute("PRAGMA table_info(organizations)").fetchall()}
    for col, typ in (
        ("custom_domain", "TEXT DEFAULT ''"),
        ("logo_url", "TEXT DEFAULT ''"),
        ("primary_color", "TEXT DEFAULT '#1e3a5f'"),
        ("support_email", "TEXT DEFAULT ''"),
    ):
        if col not in cols:
            c.execute(f"ALTER TABLE organizations ADD COLUMN {col} {typ}")
