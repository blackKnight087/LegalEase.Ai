"""SQLite / PostgreSQL SQL compatibility helpers."""
from __future__ import annotations

from typing import Any, Sequence, Set, Tuple

from backend.app.core.legacy_db import LegacyConnection, use_postgres_legacy


def is_postgres_conn(conn: Any) -> bool:
    return use_postgres_legacy() or isinstance(conn, LegacyConnection)


def table_exists(conn: Any, name: str) -> bool:
    if is_postgres_conn(conn):
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ?
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        return bool(row)
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def table_columns(conn: Any, table: str) -> list[str]:
    if is_postgres_conn(conn):
        try:
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                ORDER BY ordinal_position
                """,
                (table,),
            ).fetchall()
            return [str(r[0]) for r in rows]
        except Exception:
            return []
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [str(r[1]) for r in rows]
    except Exception:
        return []


def table_columns_set(conn: Any, table: str) -> Set[str]:
    return set(table_columns(conn, table))


def list_tables(conn: Any) -> Set[str]:
    if is_postgres_conn(conn):
        rows = conn.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        ).fetchall()
        return {str(r[0]) for r in rows}
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        return {str(r[0]) for r in rows}
    except Exception:
        return set()


def execute_script(conn: Any, script: str) -> None:
    """Run multi-statement DDL on SQLite or PostgreSQL."""
    statements = [s.strip() + ";" for s in script.split(";") if s.strip()]
    if is_postgres_conn(conn):
        for stmt in statements:
            try:
                conn.execute(stmt)
            except Exception:
                pass
        return
    if hasattr(conn, "executescript"):
        conn.executescript(script)
        return
    for stmt in statements:
        conn.execute(stmt)


def ensure_columns(
    conn: Any,
    table: str,
    columns: Sequence[Tuple[str, str, str]],
) -> None:
    """
    Add columns when missing.

    Each item is (column_name, postgres_type_def, sqlite_alter_ddl).
    """
    if is_postgres_conn(conn):
        for col, pg_def, _ in columns:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {pg_def}")
            except Exception:
                pass
        return
    if not table_exists(conn, table):
        return
    present = table_columns_set(conn, table)
    for col, _, sqlite_ddl in columns:
        if col not in present:
            try:
                conn.execute(sqlite_ddl)
            except Exception:
                pass


def upsert_user_onboarding(conn: Any, user_id: str, dismissed: int, updated_at: str) -> None:
    uid = str(user_id)
    if is_postgres_conn(conn):
        conn.execute(
            """
            INSERT INTO user_onboarding (user_id, dismissed, completed_at, updated_at)
            VALUES (?, ?, '', ?)
            ON CONFLICT (user_id) DO UPDATE SET
                dismissed = EXCLUDED.dismissed,
                updated_at = EXCLUDED.updated_at
            """,
            (uid, dismissed, updated_at),
        )
    else:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_onboarding (user_id, dismissed, updated_at)
            VALUES (?, ?, ?)
            """,
            (uid, dismissed, updated_at),
        )


def upsert_knowledge_base_status(
    conn: Any,
    *,
    status_id: str,
    status: str,
    total_documents: int,
    total_chunks: int,
    last_updated: str,
    created_at: str,
) -> None:
    params = (status_id, status, total_documents, total_chunks, last_updated, created_at)
    if is_postgres_conn(conn):
        conn.execute(
            """
            INSERT INTO knowledge_base_status
            (id, status, total_documents, total_chunks, last_updated, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                total_documents = EXCLUDED.total_documents,
                total_chunks = EXCLUDED.total_chunks,
                last_updated = EXCLUDED.last_updated
            """,
            params,
        )
    else:
        conn.execute(
            """
            INSERT OR REPLACE INTO knowledge_base_status
            (id, status, total_documents, total_chunks, last_updated, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            params,
        )


def upsert_matter_member(
    conn: Any,
    *,
    member_id: str,
    matter_id: str,
    user_id: str,
    role: str,
    created_at: str,
) -> None:
    params = (member_id, matter_id, user_id, role, created_at)
    if is_postgres_conn(conn):
        conn.execute(
            """
            INSERT INTO matter_members (member_id, matter_id, user_id, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (matter_id, user_id) DO UPDATE SET
                role = EXCLUDED.role
            """,
            params,
        )
    else:
        conn.execute(
            """
            INSERT OR REPLACE INTO matter_members
            (member_id, matter_id, user_id, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            params,
        )


def insert_or_ignore(
    conn: Any, sql_sqlite: str, sql_pg: str, params: Sequence[Any]
) -> None:
    conn.execute(sql_pg if is_postgres_conn(conn) else sql_sqlite, params)


def insert_or_replace(
    conn: Any, sql_sqlite: str, sql_pg: str, params: Sequence[Any]
) -> None:
    conn.execute(sql_pg if is_postgres_conn(conn) else sql_sqlite, params)
