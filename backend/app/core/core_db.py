"""
App DB — SQLite or PostgreSQL for all SaaS tables.

Set DATABASE_URL=postgresql://... and SAAS_USE_POSTGRES_LEGACY=1 (or SAAS_AUTO_POSTGRES_LEGACY=1 in production).
"""
from __future__ import annotations

import logging

from backend.app.core.legacy_db import LegacyConnection, app_db, connect_app_db, use_postgres_legacy

logger = logging.getLogger("legalease.core_db")


def connect_core():
    """SQLite or PostgreSQL connection for app tables."""
    return connect_app_db(foreign_keys=True)


def core_db_backend() -> str:
    return "postgresql" if use_postgres_legacy() else "sqlite"


def ensure_app_schemas() -> None:
    """Ensure all app tables (core + practice + CRM + ops) exist."""
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema
        from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

        ensure_pg_core_schema()
        ensure_pg_rest_schema()
        try:
            from backend.app.core.auth_db_bridge import install_auth_db_bridge

            install_auth_db_bridge()
        except Exception:
            pass
        try:
            from backend.app.core.app_db_bridge import install_app_db_bridge

            install_app_db_bridge()
        except Exception:
            pass
        logger.info("App schemas on PostgreSQL (legacy mode)")
        return

    try:
        from legalease_auth import ensure_db

        ensure_db()
    except Exception:
        pass
    for fn_name in (
        "ensure_document_tables_schema",
        "ensure_chat_schema",
        "ensure_user_memory_schema",
        "ensure_p0_saas_schema",
        "ensure_practice_schema",
        "ensure_saas_schema",
        "ensure_saas_ops_schema",
        "ensure_p2_saas_schema",
    ):
        try:
            if fn_name == "ensure_document_tables_schema":
                from backend.app.core.document_schema import ensure_document_tables_schema

                ensure_document_tables_schema()
            elif fn_name == "ensure_chat_schema":
                from backend.app.core.chat_persistence import ensure_chat_schema

                ensure_chat_schema()
            elif fn_name == "ensure_user_memory_schema":
                from backend.app.core.user_memory import ensure_user_memory_schema

                ensure_user_memory_schema()
            elif fn_name == "ensure_p0_saas_schema":
                from backend.app.core.p0_saas_schema import ensure_p0_saas_schema

                ensure_p0_saas_schema()
            elif fn_name == "ensure_practice_schema":
                from backend.app.core.practice_schema import ensure_practice_schema

                ensure_practice_schema()
            elif fn_name == "ensure_saas_schema":
                from backend.app.core.saas_schema import ensure_saas_schema

                ensure_saas_schema()
            elif fn_name == "ensure_saas_ops_schema":
                from backend.app.core.saas_ops_schema import ensure_saas_ops_schema

                ensure_saas_ops_schema()
            elif fn_name == "ensure_p2_saas_schema":
                from backend.app.core.p2_saas_schema import ensure_p2_saas_schema

                ensure_p2_saas_schema()
        except Exception as exc:
            logger.warning("Schema %s: %s", fn_name, exc)
    logger.info("App schemas on SQLite")


# Back-compat alias
ensure_core_schemas = ensure_app_schemas
