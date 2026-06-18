#!/usr/bin/env python3
"""
Full SQLite → PostgreSQL migration (Day 5): core + practice + CRM + ops tables.

Usage:
  set DATABASE_URL=postgresql://user:pass@host:5432/legalease
  set LEGALEASE_DB_PATH=legalease.db
  py scripts/migrate_sqlite_to_pg.py

Then: SAAS_USE_POSTGRES_LEGACY=1
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


REST_TABLES: list[tuple[str, list[str], str]] = [
    ("documents", ["id", "uploader_id", "filename", "saved_path", "pages", "uploaded_at", "matter_id", "content_hash", "org_id"], "(id) DO NOTHING"),
    ("password_reset_tokens", ["token_id", "user_id", "token_hash", "expires_at", "used_at", "created_at"], "(token_id) DO NOTHING"),
    ("user_onboarding", ["user_id", "dismissed", "completed_at", "updated_at"], "(user_id) DO NOTHING"),
    ("audit_events", ["id", "user_id", "action", "detail", "ip_address", "created_at"], "(id) DO NOTHING"),
    ("ml_jobs", ["job_id", "user_id", "job_type", "payload_json", "status", "progress", "result_json", "error_message", "created_at", "updated_at"], "(job_id) DO NOTHING"),
    ("matter_notes", ["note_id", "matter_id", "author_id", "raw_content", "anonymized_content", "timestamp"], "(note_id) DO NOTHING"),
    ("document_templates", ["template_id", "user_id", "template_name", "practice_area", "raw_markdown_structure", "variable_json_map", "created_at", "updated_at"], "(template_id) DO NOTHING"),
    ("clause_library", ["clause_id", "user_id", "clause_tag", "practice_area", "clause_text_content", "confidence_weight", "created_at", "updated_at"], "(clause_id) DO NOTHING"),
    ("matter_timeline", ["event_id", "matter_id", "event_date", "title", "description", "event_type", "created_at"], "(event_id) DO NOTHING"),
    ("matter_hearings", ["hearing_id", "matter_id", "hearing_date", "court_name", "purpose", "notes", "status", "created_at"], "(hearing_id) DO NOTHING"),
    ("matter_tasks", ["task_id", "matter_id", "title", "due_date", "status", "assignee", "created_at", "updated_at"], "(task_id) DO NOTHING"),
    ("matter_deadlines", ["deadline_id", "matter_id", "title", "due_date", "deadline_type", "status", "notes", "created_at"], "(deadline_id) DO NOTHING"),
    ("financial_records", ["record_id", "matter_id", "lawyer_id", "billing_type", "units_logged", "rate_per_unit", "narrative_description", "raw_activity", "invoice_status", "currency", "created_at", "updated_at"], "(record_id) DO NOTHING"),
    ("invoices", ["invoice_id", "matter_id", "lawyer_id", "client_name", "line_items_json", "subtotal", "tax_rate", "tax_amount", "total", "status", "created_at"], "(invoice_id) DO NOTHING"),
    ("crm_leads", ["lead_id", "user_id", "prospect_name", "contact_email", "contact_phone", "raw_intake_query", "calculated_intent", "extracted_params_json", "pipeline_stage", "assigned_attorney_id", "follow_up_draft", "created_at", "updated_at"], "(lead_id) DO NOTHING"),
    ("ediscovery_batches", ["batch_id", "matter_id", "user_id", "batch_title", "total_documents_count", "created_at"], "(batch_id) DO NOTHING"),
    ("discovery_items", ["item_id", "batch_id", "source_identifier", "content_payload", "assigned_tags", "relevance_score", "classification", "rationale", "reviewed_status", "created_at"], "(item_id) DO NOTHING"),
    ("research_queries", ["query_id", "user_id", "matter_id", "raw_search_term", "expanded_search_terms", "selected_mode", "retrieval_confidence", "feedback_signal", "created_at"], "(query_id) DO NOTHING"),
    ("ediscovery_jobs", ["job_id", "batch_id", "user_id", "matter_id", "batch_title", "payload_json", "status", "progress", "result_json", "error_message", "created_at", "updated_at"], "(job_id) DO NOTHING"),
]


def main() -> int:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url.startswith("postgresql"):
        print("Set DATABASE_URL=postgresql://...")
        return 1
    db_path = os.getenv("LEGALEASE_DB_PATH", str(ROOT / "legalease.db"))
    if not Path(db_path).exists():
        print(f"SQLite not found: {db_path}")
        return 1

    print("Step 1: core tables (users, chat, orgs, learning)...")
    import importlib.util

    core_path = ROOT / "scripts" / "migrate_core_to_postgres.py"
    spec = importlib.util.spec_from_file_location("migrate_core", core_path)
    core_mig = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(core_mig)
    rc = core_mig.main()
    if rc != 0:
        return rc

    try:
        import psycopg2
    except ImportError:
        print("pip install psycopg2-binary")
        return 1

    from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

    ensure_pg_rest_schema()
    sq = sqlite3.connect(db_path)
    pg = psycopg2.connect(url)
    pg.autocommit = False
    cur = pg.cursor()

    print("Step 2: practice + CRM + ops tables...")
    for table, cols, conflict in REST_TABLES:
        _copy_table(sq, cur, table, cols, conflict=conflict)

    pg.commit()
    sq.close()
    pg.close()
    print("Full migration complete. Set SAAS_USE_POSTGRES_LEGACY=1 and restart API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
