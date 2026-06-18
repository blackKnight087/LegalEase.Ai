"""
Central SQLite schema verification and safe migrations for legalease.db.

Runs at backend startup before chat/KB/learning paths touch the database.
Adds missing columns with ALTER TABLE — never patches around schema errors in queries.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from backend.app.core.database import connect_data_db, get_sqlite_path, is_sqlite

logger = logging.getLogger("legalease.schema")

T = TypeVar("T")

# table -> list of (column_name, SQL type fragment for ADD COLUMN)
REQUIRED_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "users": [
        ("email", "TEXT DEFAULT ''"),
        ("display_name", "TEXT DEFAULT ''"),
        ("last_login_at", "TEXT DEFAULT ''"),
    ],
    "documents": [
        ("matter_id", "TEXT DEFAULT ''"),
        ("content_hash", "TEXT DEFAULT ''"),
    ],
    "chat_history": [
        ("thread_id", "TEXT"),
    ],
    "adaptive_feedback": [
        ("tags_json", "TEXT DEFAULT '[]'"),
        ("metadata_json", "TEXT DEFAULT '{}'"),
    ],
    "human_labels": [
        ("tags_json", "TEXT DEFAULT '[]'"),
        ("metadata_json", "TEXT DEFAULT '{}'"),
    ],
    "organizations": [
        ("custom_domain", "TEXT DEFAULT ''"),
        ("logo_url", "TEXT DEFAULT ''"),
        ("primary_color", "TEXT DEFAULT '#1e3a5f'"),
        ("support_email", "TEXT DEFAULT ''"),
    ],
    "crm_leads": [
        ("org_id", "TEXT DEFAULT ''"),
        ("address", "TEXT DEFAULT ''"),
        ("city", "TEXT DEFAULT ''"),
        ("state", "TEXT DEFAULT ''"),
        ("preferred_contact", "TEXT DEFAULT ''"),
        ("preferred_language", "TEXT DEFAULT ''"),
        ("referral_source", "TEXT DEFAULT ''"),
        ("lead_score", "INTEGER DEFAULT 0"),
        ("lead_score_band", "TEXT DEFAULT ''"),
        ("case_strength", "TEXT DEFAULT ''"),
        ("assigned_lawyer_id", "TEXT DEFAULT ''"),
        ("rejection_reason", "TEXT DEFAULT ''"),
        ("analysis_json", "TEXT DEFAULT '{}'"),
        ("analysis_version", "INTEGER DEFAULT 1"),
        ("last_analyzed_at", "TEXT DEFAULT ''"),
        ("matter_id", "TEXT DEFAULT ''"),
        ("archived_at", "TEXT DEFAULT ''"),
    ],
}


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return []
    return [str(r[1]) for r in rows]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def verify_schema(*, tables: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Return schema health report. Does not mutate the database.

    Example missing entry:
      {"table": "users", "column": "email", "status": "missing"}
    """
    if not is_sqlite():
        return {"ok": True, "skipped": "non-sqlite", "missing": [], "tables": {}}

    target_tables = tables or list(REQUIRED_COLUMNS.keys())
    missing: List[Dict[str, str]] = []
    tables_report: Dict[str, List[str]] = {}
    conn = connect_data_db()
    try:
        for table in target_tables:
            if not _table_exists(conn, table):
                for col, _ in REQUIRED_COLUMNS.get(table, []):
                    missing.append({"table": table, "column": col, "status": "table_missing"})
                tables_report[table] = []
                continue
            cols = _table_columns(conn, table)
            tables_report[table] = cols
            present = set(cols)
            for col, _ in REQUIRED_COLUMNS.get(table, []):
                if col not in present:
                    missing.append({"table": table, "column": col, "status": "missing"})
    finally:
        conn.close()

    return {
        "ok": len(missing) == 0,
        "db_path": str(get_sqlite_path()),
        "missing": missing,
        "tables": tables_report,
    }


def apply_migrations(*, tables: Optional[List[str]] = None) -> Dict[str, Any]:
    """Add any missing columns from REQUIRED_COLUMNS. Idempotent."""
    if not is_sqlite():
        return {"applied": [], "skipped": "non-sqlite"}

    applied: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []
    target_tables = tables or list(REQUIRED_COLUMNS.keys())

    conn = connect_data_db()
    try:
        for table in target_tables:
            if not _table_exists(conn, table):
                skipped.append(f"{table} (table does not exist yet)")
                continue
            present = set(_table_columns(conn, table))
            for col, col_def in REQUIRED_COLUMNS.get(table, []):
                if col in present:
                    continue
                stmt = f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"
                try:
                    conn.execute(stmt)
                    applied.append(f"{table}.{col}")
                    logger.info("Schema migration applied: %s.%s", table, col)
                except sqlite3.Error as exc:
                    msg = f"{table}.{col}: {exc}"
                    errors.append(msg)
                    logger.exception("Schema migration failed: %s", msg)
        if applied:
            conn.commit()
        # chat_history thread_id backfill (matches chat_persistence)
        if _table_exists(conn, "chat_history") and "thread_id" in set(_table_columns(conn, "chat_history")):
            needs = conn.execute(
                "SELECT 1 FROM chat_history WHERE thread_id IS NULL OR thread_id = '' LIMIT 1"
            ).fetchone()
            if needs:
                conn.execute(
                    "UPDATE chat_history SET thread_id = id WHERE thread_id IS NULL OR thread_id = ''"
                )
                conn.commit()
                applied.append("chat_history.thread_id_backfill")
    finally:
        conn.close()

    report = verify_schema(tables=target_tables)
    return {
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
        "ok": report.get("ok", False) and not errors,
        "remaining_missing": report.get("missing", []),
    }


def ensure_schema_at_startup() -> Dict[str, Any]:
    """
    Create core auth tables if needed, then verify + migrate.
    Called from FastAPI startup and legalease_auth.ensure_db().
    """
    try:
        from legalease_auth import ensure_db

        ensure_db()
    except Exception as exc:
        logger.warning("ensure_db before migrations: %s", exc)

    result = apply_migrations()
    report = verify_schema()
    if not report.get("ok"):
        logger.error(
            "Schema verification failed after migrations — missing: %s",
            report.get("missing"),
        )
    else:
        logger.info(
            "Schema OK (%s) — migrations applied: %s",
            report.get("db_path"),
            result.get("applied") or "none",
        )
    result["verify"] = report
    return result


def format_schema_report() -> str:
    """Human-readable PRAGMA summary for logs and diagnostics."""
    report = verify_schema()
    lines = [f"Database: {report.get('db_path', '?')}", f"Schema OK: {report.get('ok')}"]
    for table, cols in sorted((report.get("tables") or {}).items()):
        lines.append(f"  {table}: {', '.join(cols) if cols else '(missing table)'}")
    for m in report.get("missing") or []:
        lines.append(f"  MISSING: {m['table']}.{m['column']} ({m['status']})")
    return "\n".join(lines)


def safe_sqlite(
    label: str,
    fn: Callable[[], T],
    *,
    default: Optional[T] = None,
    reraise: bool = False,
) -> Optional[T]:
    """
    Run a DB operation without breaking KB/chat when SQLite fails.
    Logs full traceback on sqlite3.Error.
    """
    try:
        return fn()
    except sqlite3.Error:
        logger.exception("SQLite error [%s]", label)
        if reraise:
            raise
        return default
