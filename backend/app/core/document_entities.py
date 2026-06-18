"""Persist structured contract/NDA entities at index time."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_document_entities_schema() -> None:
    from backend.app.core.database import connect_data_db

    conn = connect_data_db()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS document_entities (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            document_type TEXT NOT NULL DEFAULT 'unknown',
            entities_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, document_id)
        )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_entities_user ON document_entities(user_id)"
        )
        conn.commit()
    finally:
        conn.close()


def save_document_entities(
    user_id: str,
    document_id: str,
    filename: str,
    document_type: str,
    entities: Dict[str, Any],
) -> None:
    ensure_document_entities_schema()
    from backend.app.core.database import connect_data_db

    uid = str(user_id)
    now = _utc()
    conn = connect_data_db()
    try:
        conn.execute(
            """INSERT INTO document_entities
            (id, user_id, document_id, filename, document_type, entities_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, document_id) DO UPDATE SET
                filename=excluded.filename,
                document_type=excluded.document_type,
                entities_json=excluded.entities_json,
                updated_at=excluded.updated_at""",
            (
                str(uuid.uuid4()),
                uid,
                str(document_id),
                filename,
                document_type,
                json.dumps(entities, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_document_entities(
    user_id: str,
    *,
    document_id: str = "",
    filename: str = "",
) -> Optional[Dict[str, Any]]:
    ensure_document_entities_schema()
    from backend.app.core.database import connect_data_db

    conn = connect_data_db()
    try:
        row = None
        if document_id:
            row = conn.execute(
                "SELECT entities_json, document_type, filename FROM document_entities WHERE user_id=? AND document_id=?",
                (str(user_id), str(document_id)),
            ).fetchone()
        elif filename:
            row = conn.execute(
                "SELECT entities_json, document_type, filename FROM document_entities WHERE user_id=? AND filename=?",
                (str(user_id), filename),
            ).fetchone()
        if not row:
            return None
        entities = json.loads(row[0] or "{}")
        entities["_document_type"] = row[1]
        entities["_filename"] = row[2]
        return entities
    except Exception:
        return None
    finally:
        conn.close()
