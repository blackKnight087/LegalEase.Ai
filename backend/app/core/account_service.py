"""GDPR account export and full data purge."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db, get_sqlite_path
from backend.app.core.sql_compat import table_exists
from backend.app.core.matter_index import get_user_index_dir
from backend.app.core.matter_repo import delete_matter, list_matters
from backend.app.core.observability import emit_event
from backend.app.core.p0_saas_schema import ensure_p0_saas_schema
from backend.app.core.p2_saas_schema import ensure_p2_saas_schema

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user_faiss_dir(user_id: str) -> Path:
    return get_user_index_dir(user_id)


def _user_models_dir(user_id: str) -> Path:
    return Path(os.getenv("LEGALEASE_MODELS_DIR", str(_PROJECT_ROOT / "models"))) / str(user_id)


def export_user_data_zip(user_id: str, username: str) -> bytes:
    """Build ZIP with JSON exports of user-owned data."""
    ensure_p2_saas_schema()
    uid = str(user_id)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "user_id": uid,
            "username": username,
            "exported_at": _utc(),
            "app": "LegalEase",
        }
        zf.writestr("manifest.json", json.dumps(meta, indent=2))

        conn = connect_data_db()
        try:
            _zip_table(conn, zf, "profile.json", "SELECT * FROM user_profiles WHERE user_id = ?", (uid,))
            _zip_table(conn, zf, "chat_history.json", "SELECT * FROM chat_history WHERE user_id = ?", (uid,))
            _zip_table(conn, zf, "user_facts.json", "SELECT * FROM user_facts WHERE user_id = ?", (uid,))
            _zip_table(
                conn,
                zf,
                "adaptive_interactions.json",
                "SELECT * FROM adaptive_interactions WHERE user_id = ?",
                (uid,),
            )
            _zip_table(
                conn,
                zf,
                "matters.json",
                "SELECT * FROM matters WHERE user_id = ?",
                (uid,),
            )
            if table_exists(conn, "documents"):
                _zip_table(
                    conn,
                    zf,
                    "documents.json",
                    "SELECT id, filename, pages, uploaded_at, matter_id, saved_path FROM documents WHERE uploader_id = ?",
                    (uid,),
                )
            _zip_table(
                conn,
                zf,
                "subscriptions.json",
                "SELECT * FROM subscriptions WHERE user_id = ?",
                (uid,),
            )
        finally:
            conn.close()
    buf.seek(0)
    emit_event("account_export", user_id=uid)
    return buf.getvalue()


def _zip_table(
    conn: sqlite3.Connection,
    zf: zipfile.ZipFile,
    filename: str,
    sql: str,
    params: tuple,
) -> None:
    try:
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        zf.writestr(filename, json.dumps(rows, indent=2, default=str))
    except sqlite3.OperationalError:
        zf.writestr(filename, "[]")


def delete_user_account(user_id: str) -> Dict[str, Any]:
    """Permanently delete user and owned data (GDPR erasure)."""
    ensure_p2_saas_schema()
    uid = str(user_id)
    from legalease_auth import get_user_by_id

    user = get_user_by_id(uid)
    if not user:
        raise ValueError("User not found")

    removed: Dict[str, int] = {"matters": 0, "documents": 0, "files": 0}

    for m in list_matters(uid):
        mid = str(m.get("matter_id") or "")
        if mid and delete_matter(uid, mid):
            removed["matters"] += 1

    conn = connect_data_db()
    try:
        if _table_exists(conn, "documents"):
            doc_rows = conn.execute(
                "SELECT id, saved_path FROM documents WHERE uploader_id = ?",
                (uid,),
            ).fetchall()
            for _did, spath in doc_rows:
                p = Path(str(spath or ""))
                if p.is_file():
                    try:
                        p.unlink()
                        removed["files"] += 1
                    except OSError:
                        pass
            conn.execute("DELETE FROM documents WHERE uploader_id = ?", (uid,))
            removed["documents"] = len(doc_rows)

        for table, col in (
            ("chat_history", "user_id"),
            ("user_profiles", "user_id"),
            ("user_facts", "user_id"),
            ("adaptive_interactions", "user_id"),
            ("adaptive_feedback", "user_id"),
            ("subscriptions", "user_id"),
            ("password_reset_tokens", "user_id"),
            ("user_onboarding", "user_id"),
            ("thread_summaries", "user_id"),
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (uid,))

        _handle_org_membership(conn, uid)
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
    finally:
        conn.close()

    faiss_dir = _user_faiss_dir(uid)
    if faiss_dir.exists():
        shutil.rmtree(faiss_dir, ignore_errors=True)

    models_dir = _user_models_dir(uid)
    if models_dir.exists():
        shutil.rmtree(models_dir, ignore_errors=True)

    from backend.app.core.audit_service import log_audit

    log_audit("account_deleted", user_id=uid, detail=str(removed))
    emit_event("account_deleted", user_id=uid, removed=removed)
    return {"ok": True, "user_id": uid, "removed": removed}


def _handle_org_membership(conn: sqlite3.Connection, user_id: str) -> None:
    if not _table_exists(conn, "org_members"):
        return
    rows = conn.execute(
        "SELECT org_id, role FROM org_members WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    for org_id, role in rows:
        conn.execute(
            "DELETE FROM org_members WHERE org_id = ? AND user_id = ?",
            (org_id, user_id),
        )
        remaining = conn.execute(
            "SELECT user_id, role FROM org_members WHERE org_id = ? ORDER BY created_at ASC",
            (org_id,),
        ).fetchall()
        if not remaining:
            if _table_exists(conn, "org_invites"):
                conn.execute("DELETE FROM org_invites WHERE org_id = ?", (org_id,))
            if _table_exists(conn, "organizations"):
                conn.execute("DELETE FROM organizations WHERE org_id = ?", (org_id,))
        elif role == "owner":
            new_owner = remaining[0][0]
            conn.execute(
                "UPDATE org_members SET role = 'owner' WHERE org_id = ? AND user_id = ?",
                (org_id, new_owner),
            )
