"""Unified SQLite / PostgreSQL access for legacy app tables (chat, auth, orgs)."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Sequence, Tuple, Union

from backend.app.core.database import adapt_sql, connect_sqlite, get_database_url, get_sqlite_path, is_postgres


def use_postgres_legacy() -> bool:
    if not is_postgres():
        return False
    explicit = os.getenv("SAAS_USE_POSTGRES_LEGACY", "").strip().lower()
    if explicit in {"1", "true", "yes"}:
        return True
    if explicit in {"0", "false", "no"}:
        return False
    if os.getenv("SAAS_AUTO_POSTGRES_LEGACY", "1").lower() in {"1", "true", "yes"}:
        from backend.app.core.production_config import production_mode

        if production_mode():
            return True
    return False


class LegacyCursor:
    def __init__(self, cur: Any) -> None:
        self._cur = cur

    def fetchone(self) -> Optional[Tuple]:
        return self._cur.fetchone()

    def fetchall(self) -> List[Tuple]:
        return self._cur.fetchall()

    @property
    def rowcount(self) -> int:
        return int(self._cur.rowcount or 0)


class LegacyCursorWrapper:
    """psycopg2 cursor with ? → %s placeholder adaptation."""

    def __init__(self, cur: Any) -> None:
        self._cur = cur

    def execute(self, sql: str, params: Sequence[Any] = ()) -> "LegacyCursorWrapper":
        self._cur.execute(adapt_sql(sql), tuple(params))
        return self

    def fetchone(self) -> Optional[Tuple]:
        return self._cur.fetchone()

    def fetchall(self) -> List[Tuple]:
        return self._cur.fetchall()

    @property
    def rowcount(self) -> int:
        return int(self._cur.rowcount or 0)


class LegacyConnection:
    def __init__(self, raw: Any, *, is_pg: bool) -> None:
        self._raw = raw
        self._is_pg = is_pg

    def execute(self, sql: str, params: Sequence[Any] = ()) -> LegacyCursor:
        cur = self._raw.cursor()
        cur.execute(adapt_sql(sql), tuple(params))
        return LegacyCursor(cur)

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()

    def cursor(self) -> LegacyCursorWrapper:
        return LegacyCursorWrapper(self._raw.cursor())


def connect_app_db(*, foreign_keys: bool = False) -> Union[sqlite3.Connection, LegacyConnection]:
    if use_postgres_legacy():
        import psycopg2

        conn = psycopg2.connect(get_database_url())
        return LegacyConnection(conn, is_pg=True)
    return connect_sqlite(foreign_keys=foreign_keys)


@contextmanager
def app_db(*, foreign_keys: bool = False) -> Iterator[Union[sqlite3.Connection, LegacyConnection]]:
    conn = connect_app_db(foreign_keys=foreign_keys)
    try:
        yield conn
        if isinstance(conn, LegacyConnection):
            conn.commit()
        else:
            conn.commit()
    finally:
        conn.close()


def check_legacy_db_split_brain() -> Optional[str]:
    """Return warning if Postgres URL is set but legacy tables stay on SQLite."""
    if not is_postgres():
        return None
    if use_postgres_legacy():
        return None
    return (
        "DATABASE_URL is PostgreSQL but SAAS_USE_POSTGRES_LEGACY is off — "
        "SaaS ORM tables may use Postgres while chat/auth/collab use SQLite at "
        f"{get_sqlite_path()}. Set SAAS_USE_POSTGRES_LEGACY=1."
    )
