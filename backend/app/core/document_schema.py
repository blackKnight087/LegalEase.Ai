"""Documents + KB status tables (app.py legacy); required before upload on fresh SQLite."""
from __future__ import annotations

import logging

from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import use_postgres_legacy

logger = logging.getLogger("legalease.document_schema")

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    uploader_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    saved_path TEXT NOT NULL,
    pages INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL,
    matter_id TEXT DEFAULT '',
    content_hash TEXT DEFAULT '',
    org_id TEXT DEFAULT '',
    privileged INTEGER DEFAULT 0,
    doc_version INTEGER DEFAULT 1,
    index_status TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_documents_uploader ON documents(uploader_id);
CREATE INDEX IF NOT EXISTS idx_documents_uploader_hash ON documents(uploader_id, content_hash);

CREATE TABLE IF NOT EXISTS knowledge_base_status (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    total_documents INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    last_updated TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""


def ensure_document_tables_schema() -> None:
    """Create documents/kb_status/logs on SQLite; Postgres via pg_rest_schema."""
    # region agent log
    try:
        import json
        import time
        from pathlib import Path

        _lp = Path(__file__).resolve().parents[3] / "debug-cf6ca9.log"
        with open(_lp, "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "hypothesisId": "B",
                        "location": "document_schema:ensure",
                        "message": "enter",
                        "data": {"postgres_legacy": use_postgres_legacy()},
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion

    if use_postgres_legacy():
        from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

        ensure_pg_rest_schema()
        return

    conn = connect_data_db(foreign_keys=True)
    try:
        if hasattr(conn, "executescript"):
            conn.executescript(_SQLITE_DDL)
        else:
            cur = conn.cursor()
            for stmt in _SQLITE_DDL.split(";"):
                s = stmt.strip()
                if s:
                    cur.execute(s)
        conn.commit()
        try:
            from backend.app.core.practice_schema import (
                _migrate_documents_content_hash,
                _migrate_documents_matter_id,
                _migrate_documents_org_id,
            )

            cur = conn.cursor()
            _migrate_documents_matter_id(cur)
            _migrate_documents_content_hash(cur)
            _migrate_documents_org_id(cur)
            conn.commit()
        except Exception as exc:
            logger.warning("Document column migrations: %s", exc)
    finally:
        conn.close()

    # region agent log
    try:
        import json
        import time
        from pathlib import Path

        _lp = Path(__file__).resolve().parents[3] / "debug-cf6ca9.log"
        with open(_lp, "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "hypothesisId": "B",
                        "location": "document_schema:ensure",
                        "message": "sqlite_tables_ok",
                        "data": {},
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion

    logger.debug("Document tables schema ensured (SQLite)")
