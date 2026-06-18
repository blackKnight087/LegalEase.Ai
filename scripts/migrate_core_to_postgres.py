#!/usr/bin/env python3
"""
One-time migration: copy legacy SQLite tables to PostgreSQL when DATABASE_URL is set.

Usage:
  set DATABASE_URL=postgresql://user:pass@host:5432/legalease
  set LEGALEASE_DB_PATH=legalease.db
  py scripts/migrate_core_to_postgres.py

Then enable runtime reads (optional):
  set SAAS_USE_POSTGRES_LEGACY=1

Tables: users, orgs, chat, matters, memory, adaptive learning, kb memory, gemini usage.
See docs/DAY4_POSTGRES.md.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _table_exists(sq: sqlite3.Connection, name: str) -> bool:
    row = sq.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return bool(row)


def _sqlite_columns(sq: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in sq.execute(f"PRAGMA table_info({table})").fetchall()]


def _copy_table(
    sq: sqlite3.Connection,
    cur: Any,
    table: str,
    columns: Sequence[str],
    *,
    conflict: str = "DO NOTHING",
) -> int:
    if not _table_exists(sq, table):
        print(f"  skip {table} (not in SQLite)")
        return 0
    avail = set(_sqlite_columns(sq, table))
    cols = [c for c in columns if c in avail]
    if not cols:
        print(f"  skip {table} (no matching columns)")
        return 0
    col_sql = ", ".join(cols)
    ph = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({ph}) ON CONFLICT {conflict}"
    n = 0
    for row in sq.execute(f"SELECT {col_sql} FROM {table}"):
        cur.execute(sql, row)
        n += 1
    print(f"  {table}: {n} rows")
    return n


def main() -> int:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url.startswith("postgresql"):
        print("Set DATABASE_URL=postgresql://...")
        return 1
    try:
        import psycopg2
    except ImportError:
        print("pip install psycopg2-binary")
        return 1

    db_path = os.getenv("LEGALEASE_DB_PATH", str(ROOT / "legalease.db"))
    if not Path(db_path).exists():
        print(f"SQLite not found: {db_path}")
        return 1

    from backend.app.core.p0_saas_schema import ensure_p0_saas_schema
    from backend.app.core.pg_core_schema import PG_CORE_DDL

    ensure_p0_saas_schema()

    sq = sqlite3.connect(db_path)
    pg = psycopg2.connect(url)
    pg.autocommit = False
    cur = pg.cursor()

    for ddl in PG_CORE_DDL:
        cur.execute(ddl)

    _copy_table(
        sq,
        cur,
        "users",
        ["id", "username", "password_hash", "membership", "role", "created_at"],
        conflict="(id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "organizations",
        ["org_id", "name", "plan", "seat_limit", "created_at", "updated_at"],
        conflict="(org_id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "org_members",
        ["org_id", "user_id", "role", "created_at"],
        conflict="(org_id, user_id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "org_invites",
        [
            "invite_id",
            "org_id",
            "email",
            "role",
            "token",
            "status",
            "created_at",
            "expires_at",
        ],
        conflict="(invite_id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "subscriptions",
        [
            "user_id",
            "stripe_customer_id",
            "stripe_subscription_id",
            "plan",
            "status",
            "updated_at",
        ],
        conflict="(user_id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "chat_history",
        [
            "id",
            "user_id",
            "question",
            "answer",
            "language",
            "mode",
            "created_at",
            "thread_id",
            "matter_id",
        ],
        conflict="(id) DO NOTHING",
    )
    matter_cols = [
        "matter_id",
        "user_id",
        "org_id",
        "matter_name",
        "case_number",
        "practice_area",
        "status_tier",
        "client_name",
        "opposing_party",
        "venue",
        "created_at",
        "updated_at",
        "matter_type",
        "police_station",
        "fir_number",
        "filing_date",
        "next_hearing_date",
        "priority",
        "description",
        "is_archived",
        "archived_at",
    ]
    _copy_table(sq, cur, "matters", matter_cols, conflict="(matter_id) DO NOTHING")
    _copy_table(
        sq,
        cur,
        "user_profiles",
        [
            "user_id",
            "persona",
            "practice_area",
            "preferred_language",
            "communication_notes",
            "memory_enabled",
            "updated_at",
        ],
        conflict="(user_id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "user_facts",
        ["id", "user_id", "fact_key", "fact_value", "source", "confidence", "created_at"],
        conflict="(id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "adaptive_interactions",
        [
            "id",
            "user_id",
            "mode",
            "query",
            "query_norm",
            "answer_preview",
            "intent",
            "found_in_kb",
            "best_score",
            "chunk_keys",
            "chat_id",
            "thread_id",
            "implicit_signal",
            "scope_key",
            "created_at",
        ],
        conflict="(id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "adaptive_feedback",
        [
            "id",
            "interaction_id",
            "user_id",
            "signal",
            "value",
            "comment",
            "scope_key",
            "created_at",
        ],
        conflict="(id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "thread_summaries",
        [
            "thread_id",
            "user_id",
            "summary",
            "topics",
            "last_query",
            "turn_count",
            "updated_at",
        ],
        conflict="(thread_id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "kb_answer_memory",
        [
            "id",
            "user_id",
            "query_norm",
            "query",
            "answer",
            "source",
            "confidence",
            "hit_count",
            "chunk_keys",
            "topics",
            "created_at",
            "updated_at",
        ],
        conflict="(id) DO NOTHING",
    )
    _copy_table(
        sq,
        cur,
        "gemini_usage_daily",
        ["user_id", "day", "call_count"],
        conflict="(user_id, day) DO NOTHING",
    )

    pg.commit()
    sq.close()
    pg.close()
    print("Migration complete. Set SAAS_USE_POSTGRES_LEGACY=1 to read chat from Postgres.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
