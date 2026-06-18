"""Route app.py run_query through connect_app_db when Postgres legacy is enabled."""
from __future__ import annotations

import logging

logger = logging.getLogger("legalease.app_db")
_saved_run_query = None


def uninstall_app_db_bridge() -> None:
    """Restore app.run_query after tests or when leaving Postgres legacy mode."""
    global _saved_run_query
    try:
        import app as app_module
    except ImportError:
        _saved_run_query = None
        return
    if _saved_run_query is not None:
        app_module.run_query = _saved_run_query
        _saved_run_query = None


def install_app_db_bridge() -> None:
    """Patch app.run_query so document upload/index uses the same DB as the API."""
    try:
        import app as app_module
    except ImportError:
        return

    from backend.app.core.legacy_db import LegacyConnection, connect_app_db, use_postgres_legacy

    if not use_postgres_legacy():
        uninstall_app_db_bridge()
        return

    if getattr(app_module.run_query, "__name__", "") == "_bridged_app_run_query":
        return

    global _saved_run_query
    if _saved_run_query is None:
        _saved_run_query = app_module.run_query

    def _bridged_run_query(query, params=(), fetch=False):
        conn = connect_app_db(foreign_keys=True)
        try:
            if isinstance(conn, LegacyConnection):
                cur = conn.execute(query, params if params else ())
                if fetch:
                    rows = cur.fetchall()
                    return rows
                conn.commit()
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
            logger.exception("app.run_query failed: %s", str(query)[:200])
            try:
                conn.close()
            except Exception:
                pass
            raise

    _bridged_run_query.__name__ = "_bridged_app_run_query"
    app_module.run_query = _bridged_run_query
    logger.info("app.run_query bridge installed (postgres_legacy=True)")
