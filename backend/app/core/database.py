"""
Central database configuration — SQLite (default) or PostgreSQL via DATABASE_URL.

- SQLAlchemy ORM (enterprise tables): uses DATABASE_URL from db.py
- Raw sqlite3 modules (chat, memory, learning, auth): use get_sqlite_path() / connect_data_db()
  When DATABASE_URL is postgresql://..., set LEGALEASE_DB_PATH for legacy tables on a shared
  SQLite volume, or migrate tables to Postgres (see DEPLOY.md).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Union

ROOT = Path(__file__).resolve().parents[3]


def get_database_url() -> str:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit
    path = get_sqlite_path()
    return f"sqlite:///{path.as_posix()}"


def is_postgres() -> bool:
    return get_database_url().startswith("postgresql")


def is_sqlite() -> bool:
    url = get_database_url()
    return url.startswith("sqlite") or not url.startswith("postgresql")


def get_sqlite_path() -> Path:
    """Filesystem path for legacy sqlite3 tables (chat, auth, memory, learning)."""
    legalease = os.getenv("LEGALEASE_DB_PATH", "").strip()
    if legalease:
        return Path(legalease)
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("sqlite:///"):
        raw = url.replace("sqlite:///", "", 1)
        # Windows: sqlite:///C:/path → C:/path
        if len(raw) >= 3 and raw[1] == ":":
            return Path(raw)
        return ROOT / raw
    return ROOT / "legalease.db"


def connect_sqlite(timeout: float = 30, *, foreign_keys: bool = False) -> sqlite3.Connection:
    path = get_sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=timeout)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA busy_timeout={int(max(1, timeout) * 1000)}")
    except Exception:
        pass
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_data_db(timeout: float = 30, *, foreign_keys: bool = False):
    """SQLite or PostgreSQL for all app tables when SAAS_USE_POSTGRES_LEGACY=1."""
    from backend.app.core.legacy_db import connect_app_db, use_postgres_legacy

    if use_postgres_legacy():
        return connect_app_db(foreign_keys=foreign_keys)
    return connect_sqlite(timeout=timeout, foreign_keys=foreign_keys)


def adapt_sql(sql: str) -> str:
    """Convert ? placeholders to %s for psycopg2 when using PostgreSQL raw connections."""
    if is_postgres():
        return sql.replace("?", "%s")
    return sql


def safe_sqlite_call(
    label: str,
    fn,
    *,
    default=None,
    reraise: bool = False,
):
    """Delegate to schema_migrations.safe_sqlite — avoids import cycles at module load."""
    from backend.app.core.schema_migrations import safe_sqlite

    return safe_sqlite(label, fn, default=default, reraise=reraise)


def connect_raw() -> Union[sqlite3.Connection, Any]:
    """
    Raw DB connection for modules that may use Postgres in future.
    Today: always sqlite3 for legacy SQL (PRAGMA, etc.).
    """
    if is_postgres():
        try:
            import psycopg2  # type: ignore

            return psycopg2.connect(get_database_url())
        except ImportError as e:
            raise RuntimeError(
                "DATABASE_URL is PostgreSQL but psycopg2-binary is not installed. "
                "pip install psycopg2-binary or use sqlite:/// for legacy tables."
            ) from e
    return connect_data_db()
