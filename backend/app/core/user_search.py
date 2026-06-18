"""Search registered users — same database(s) as login (legalease_auth / Postgres legacy)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("legalease.user_search")


def normalize_user_search_query(query: str) -> str:
    return (query or "").strip().lstrip("@").strip()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def candidate_db_paths() -> List[Path]:
    """Every SQLite file that may hold users (auth + legacy copies)."""
    paths: List[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve())
        if key in seen or not p.is_file():
            return
        seen.add(key)
        paths.append(p)

    try:
        from legalease_auth import get_db_path

        add(Path(get_db_path()))
    except Exception:
        pass

    try:
        from backend.app.core.database import get_sqlite_path

        add(get_sqlite_path())
    except Exception:
        pass

    root = _project_root()
    add(root / "legalease.db")
    add(root / "legacy_saas" / "legalease.db")

    if (root / ".env").exists():
        import os

        raw = os.getenv("LEGALEASE_DB_PATH", "").strip()
        if raw:
            add(Path(raw))

    return paths


def _users_columns_sqlite(conn: sqlite3.Connection) -> Set[str]:
    try:
        return {str(r[1]).lower() for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    except sqlite3.Error:
        return set()


def _users_columns_via_auth_db() -> Set[str]:
    """Column set for the live auth DB (SQLite file or Postgres legacy bridge)."""
    try:
        from backend.app.core.legacy_db import use_postgres_legacy

        if use_postgres_legacy():
            from backend.app.core.database import connect_data_db

            conn = connect_data_db()
            try:
                rows = conn.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'users'
                    """
                ).fetchall()
                return {str(r[0]).lower() for r in rows}
            finally:
                conn.close()

        from legalease_auth import ensure_db, run_query

        ensure_db()
        rows = run_query("PRAGMA table_info(users)", fetch=True) or []
        return {str(r[1]).lower() for r in rows}
    except Exception:
        logger.debug("users column detection failed", exc_info=True)
        return {"id", "username"}


def _user_search_sql(cols: Set[str]) -> Tuple[str, bool]:
    """Return (SQL, extended_row) where extended_row includes display_name + email."""
    has_email = "email" in cols
    has_display = "display_name" in cols
    if has_email and has_display:
        sql = """
            SELECT id, COALESCE(NULLIF(username, ''), id),
                   COALESCE(display_name, ''), COALESCE(email, '')
            FROM users
            WHERE (
                LOWER(COALESCE(username, '')) = ?
                OR LOWER(COALESCE(username, '')) LIKE ?
                OR LOWER(COALESCE(email, '')) LIKE ?
                OR LOWER(COALESCE(display_name, '')) LIKE ?
                OR LOWER(COALESCE(id, '')) LIKE ?
            )
            ORDER BY
                CASE WHEN LOWER(COALESCE(username, '')) = ? THEN 0 ELSE 1 END,
                username ASC
            LIMIT ?
        """
        return sql, True
    sql = """
        SELECT id, COALESCE(NULLIF(username, ''), id), '', ''
        FROM users
        WHERE LOWER(COALESCE(username, '')) = ?
           OR LOWER(COALESCE(username, '')) LIKE ?
           OR LOWER(COALESCE(id, '')) LIKE ?
        ORDER BY
            CASE WHEN LOWER(COALESCE(username, '')) = ? THEN 0 ELSE 1 END,
            username ASC
        LIMIT ?
    """
    return sql, False


def _search_params(like: str, exact: str, limit: int, *, extended: bool) -> tuple:
    if extended:
        return (exact, like, like, like, like, exact, limit)
    return (exact, like, like, exact, limit)


def _search_one_sqlite_db(
    db_path: Path,
    user_id: str,
    like: str,
    exact: str,
    *,
    limit: int,
) -> List[tuple]:
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        try:
            n = conn.execute("SELECT COUNT(*) FROM users").fetchone()
            if not n or int(n[0]) == 0:
                return []
        except sqlite3.Error:
            return []

        cols = _users_columns_sqlite(conn)
        sql, extended = _user_search_sql(cols)
        return conn.execute(sql, _search_params(like, exact, limit, extended=extended)).fetchall()
    except sqlite3.Error:
        logger.exception("SQLite user search failed on %s", db_path)
        return []
    finally:
        conn.close()


def _search_via_run_query(user_id: str, like: str, exact: str, *, limit: int) -> List[tuple]:
    """Primary path: legalease_auth.run_query (SQLite file or Postgres legacy bridge)."""
    try:
        from legalease_auth import ensure_db, run_query

        ensure_db()
        cols = _users_columns_via_auth_db()
        sql, extended = _user_search_sql(cols)
        params = _search_params(like, exact, limit, extended=extended)
        return list(run_query(sql, params, fetch=True) or [])
    except Exception:
        logger.exception("run_query user search failed")
        return []


def _search_postgres_users(user_id: str, like: str, exact: str, *, limit: int) -> List[tuple]:
    try:
        from backend.app.core.database import connect_data_db
        from backend.app.core.legacy_db import use_postgres_legacy

        if not use_postgres_legacy():
            return []
        cols = _users_columns_via_auth_db()
        sql, extended = _user_search_sql(cols)
        params = _search_params(like, exact, limit, extended=extended)
        conn = connect_data_db()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except Exception:
        logger.exception("Postgres user search failed")
        return []


def _lookup_row_exact(username: str) -> Optional[tuple]:
    """Single user row (id, username, display_name, email) by exact username."""
    q = normalize_user_search_query(username)
    if not q:
        return None
    exact = q.lower()
    like = f"%{exact}%"

    row = _search_via_run_query("", like, exact, limit=1)
    if row:
        return row[0]

    for path in candidate_db_paths():
        hits = _search_one_sqlite_db(path, "", like, exact, limit=1)
        if hits:
            return hits[0]

    pg = _search_postgres_users("", like, exact, limit=1)
    if pg:
        return pg[0]
    return None


def iter_user_search_rows(
    user_id: str,
    query: str,
    *,
    limit: int = 20,
    include_self: bool = False,
) -> List[tuple]:
    """Rows: (id, username, display_name, email)."""
    q = normalize_user_search_query(query)
    if len(q) < 1:
        return []
    like = f"%{q.lower()}%"
    exact = q.lower()
    cap = min(limit, 50)
    seen: Dict[str, tuple] = {}

    def merge(rows: List[tuple]) -> None:
        for row in rows:
            uid = str(row[0])
            if uid in seen:
                continue
            if uid == str(user_id) and not include_self:
                continue
            seen[uid] = row

    merge(_search_via_run_query(user_id, like, exact, limit=cap))
    merge(_search_postgres_users(user_id, like, exact, limit=cap))
    for path in candidate_db_paths():
        merge(_search_one_sqlite_db(path, user_id, like, exact, limit=cap))

    out = list(seen.values())[:cap]
    if out:
        return out

    # Exact username exists in auth DB but broad search missed (schema / split-brain edge case).
    if len(q) >= 2:
        hit = _lookup_row_exact(q)
        if hit:
            uid = str(hit[0])
            if uid != str(user_id) or include_self:
                return [hit]
    return []


def lookup_username_exact(username: str) -> Optional[Dict[str, str]]:
    """Find user by exact login username (case-insensitive)."""
    row = _lookup_row_exact(username)
    if row:
        return {"user_id": str(row[0]), "username": str(row[1])}
    return None


def search_hint_for_query(
    user_id: str,
    query: str,
    result_count: int,
    *,
    your_username: str = "",
) -> str:
    q = normalize_user_search_query(query)
    if not q:
        return ""
    if result_count > 0:
        return ""
    un = (your_username or "").strip().lower()
    if un and q.lower() == un:
        return (
            "That is your own login username. Search for someone else's username "
            "(the name they use to sign in, not yours)."
        )
    if len(q) < 2:
        return "Type at least 2 characters."
    hit = lookup_username_exact(q)
    if hit and str(hit["user_id"]) == str(user_id):
        return (
            "That account is you. Use a second browser or incognito window with another "
            "registered account to test chat requests."
        )
    if hit:
        return (
            f"User @{hit['username']} was found but could not be listed. "
            "Try searching their full username again, or contact support if this persists."
        )
    return (
        f'No user matching "{q}". Use their exact sign-in username '
        "(shown at login), not a display nickname."
    )
