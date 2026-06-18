"""Route legalease_auth SQL through legacy_db (SQLite or PostgreSQL)."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("legalease.auth_db")


def install_auth_db_bridge() -> None:
    """Monkey-patch legalease_auth to use connect_app_db when Postgres legacy is enabled."""
    try:
        import legalease_auth as la
    except ImportError:
        return

    from backend.app.core.legacy_db import LegacyConnection, connect_app_db, use_postgres_legacy

    if getattr(la.run_query, "__name__", "") == "_bridged_run_query":
        return

    _orig_ensure = la.ensure_db

    def _bridged_run_query(
        query: str,
        params=(),
        fetch: bool = False,
        *,
        critical: bool = True,
    ):
        conn = connect_app_db(foreign_keys=True)
        try:
            if isinstance(conn, LegacyConnection):
                cur = conn.execute(query, params if params else ())
                if fetch:
                    rows = cur.fetchall()
                    conn.close()
                    return rows
                conn.commit()
                conn.close()
                return None

            cur = conn.cursor()
            cur.execute(query, params)
            if fetch:
                rows = cur.fetchall()
                conn.close()
                return rows
            conn.commit()
            conn.close()
            return None
        except Exception:
            logger.exception("DB query failed (critical=%s): %s", critical, query[:200])
            try:
                conn.close()
            except Exception:
                pass
            if critical:
                raise
            return [] if fetch else None

    def _ensure_db_wrapper() -> None:
        if use_postgres_legacy():
            from backend.app.core.pg_core_schema import ensure_pg_core_schema

            ensure_pg_core_schema()
            try:
                from backend.app.core.p0_saas_schema import ensure_p0_saas_schema

                ensure_p0_saas_schema()
            except Exception:
                pass
            return
        _orig_ensure()

    la.run_query = _bridged_run_query
    la.run_query.__name__ = "_bridged_run_query"
    la.ensure_db = _ensure_db_wrapper
    logger.info(
        "Auth DB bridge installed (postgres_legacy=%s)",
        use_postgres_legacy(),
    )
