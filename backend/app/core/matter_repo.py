"""Matter & note persistence — case workspace OS."""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.legacy_db import connect_app_db
from backend.app.core.matter_index import get_matter_index_dir
from backend.app.core.sql_compat import table_exists
from backend.app.core.org_service import (
    get_org_member_role,
    get_primary_org_id,
    list_user_org_ids,
    user_in_org,
)
from backend.app.core.p0_saas_schema import ensure_p0_saas_schema
from backend.app.core.practice_schema import ensure_practice_schema

_MATTER_COLS = (
    "matter_id",
    "user_id",
    "org_id",
    "matter_name",
    "case_number",
    "practice_area",
    "status_tier",
    "client_name",
    "opposing_party",
    "venue",
    "created_at",
    "updated_at",
    "matter_type",
    "police_station",
    "fir_number",
    "filing_date",
    "next_hearing_date",
    "priority",
    "description",
    "is_archived",
    "archived_at",
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matter_row(row) -> Dict[str, Any]:
    keys = _MATTER_COLS[: len(row)]
    out = {k: row[i] for i, k in enumerate(keys)}
    for k in _MATTER_COLS:
        out.setdefault(k, "")
    if not out.get("matter_type"):
        out["matter_type"] = out.get("practice_area") or "General Research"
    return out


def create_matter(
    user_id: str,
    *,
    matter_name: str,
    practice_area: str = "General",
    matter_type: str = "",
    case_number: str = "",
    client_name: str = "",
    opposing_party: str = "",
    venue: str = "",
    status_tier: str = "Open",
    police_station: str = "",
    fir_number: str = "",
    filing_date: str = "",
    next_hearing_date: str = "",
    priority: str = "Medium",
    description: str = "",
) -> Dict[str, Any]:
    ensure_p0_saas_schema()
    mid = str(uuid.uuid4())
    now = _utc()
    mtype = (matter_type or practice_area or "General Research").strip()
    org_id = get_primary_org_id(str(user_id))
    conn = connect_app_db()
    conn.execute(
        """
        INSERT INTO matters
        (matter_id, user_id, org_id, matter_name, case_number, practice_area, status_tier,
         client_name, opposing_party, venue, created_at, updated_at,
         matter_type, police_station, fir_number, filing_date, next_hearing_date,
         priority, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mid,
            str(user_id),
            org_id,
            matter_name.strip(),
            case_number.strip(),
            mtype,
            status_tier,
            client_name.strip(),
            opposing_party.strip(),
            venue.strip(),
            now,
            now,
            mtype,
            police_station.strip(),
            fir_number.strip(),
            filing_date.strip(),
            next_hearing_date.strip(),
            priority.strip() or "Medium",
            description.strip(),
        ),
    )
    conn.commit()
    conn.close()
    return get_matter(user_id, mid) or {}


def _fetch_matter_row(matter_id: str) -> Optional[Dict[str, Any]]:
    ensure_p0_saas_schema()
    conn = connect_app_db()
    row = conn.execute(
        f"SELECT {', '.join(_MATTER_COLS)} FROM matters WHERE matter_id = ?",
        (matter_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _matter_row(row)


def _user_can_access_matter(user_id: str, matter_id: str) -> bool:
    m = _fetch_matter_row(matter_id)
    if not m:
        return False
    uid = str(user_id)
    if str(m.get("user_id") or "") == uid:
        return True
    org_id = str(m.get("org_id") or "")
    if org_id and user_in_org(uid, org_id):
        return True
    conn = connect_app_db()
    row = conn.execute(
        "SELECT 1 FROM matter_members WHERE matter_id = ? AND user_id = ? LIMIT 1",
        (matter_id, uid),
    ).fetchone()
    conn.close()
    return bool(row)


def get_matter(user_id: str, matter_id: str) -> Optional[Dict[str, Any]]:
    if not _user_can_access_matter(user_id, matter_id):
        return None
    return _fetch_matter_row(matter_id)


def list_matters(
    user_id: str, *, status: str = "", limit: int = 100, include_archived: bool = False
) -> List[Dict[str, Any]]:
    ensure_p0_saas_schema()
    conn = connect_app_db()
    org_ids = list_user_org_ids(str(user_id))
    if org_ids:
        placeholders = ",".join("?" * len(org_ids))
        q = f"""
            SELECT {", ".join(_MATTER_COLS)}
            FROM matters
            WHERE user_id = ? OR org_id IN ({placeholders})
        """
        params: List[Any] = [str(user_id), *org_ids]
    else:
        q = f"""
            SELECT {", ".join(_MATTER_COLS)}
            FROM matters WHERE user_id = ?
        """
        params = [str(user_id)]
    if not include_archived:
        q += " AND COALESCE(is_archived, 0) = 0"
    if status:
        q += " AND status_tier = ?"
        params.append(status)
    q += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_matter_row(r) for r in rows]


def _matter_write_allowed(user_id: str, matter_id: str) -> bool:
    ctx = get_matter_access_context(user_id, matter_id)
    if not ctx:
        return False
    role = str(ctx.get("role") or "viewer")
    return role in ("owner", "lawyer")


def update_matter(user_id: str, matter_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    if not _matter_write_allowed(user_id, matter_id):
        return None
    allowed = set(_MATTER_COLS) - {"matter_id", "user_id", "created_at"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_matter(user_id, matter_id)
    updates["updated_at"] = _utc()
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn = connect_app_db()
    conn.execute(
        f"UPDATE matters SET {sets} WHERE matter_id = ?",
        (*updates.values(), matter_id),
    )
    conn.commit()
    conn.close()
    return get_matter(user_id, matter_id)


def delete_matter(user_id: str, matter_id: str) -> bool:
    """Remove matter, delete its documents, purge Global KB vectors, drop matter FAISS."""
    if not get_matter(user_id, matter_id):
        return False

    try:
        from backend.app.core.global_kb_purge import purge_matter_documents_on_delete

        purge_matter_documents_on_delete(str(user_id), matter_id)
    except Exception:
        pass

    ensure_practice_schema()
    conn = connect_app_db()
    if table_exists(conn, "documents"):
        conn.execute(
            "DELETE FROM documents WHERE uploader_id = ? AND matter_id = ?",
            (str(user_id), matter_id),
        )
    conn.execute("DELETE FROM matters WHERE matter_id = ? AND user_id = ?", (matter_id, str(user_id)))
    conn.commit()
    conn.close()

    try:
        idx = get_matter_index_dir(str(user_id), matter_id)
        if idx.exists():
            shutil.rmtree(idx, ignore_errors=True)
    except Exception:
        pass
    return True


def archive_matter(user_id: str, matter_id: str) -> bool:
    if not _matter_write_allowed(user_id, matter_id):
        return False
    conn = connect_app_db()
    cur = conn.execute(
        "UPDATE matters SET is_archived = 1, archived_at = ?, updated_at = ? WHERE matter_id = ?",
        (_utc(), _utc(), matter_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def restore_matter(user_id: str, matter_id: str) -> bool:
    if not _matter_write_allowed(user_id, matter_id):
        return False
    conn = connect_app_db()
    cur = conn.execute(
        "UPDATE matters SET is_archived = 0, archived_at = '' , updated_at = ? WHERE matter_id = ?",
        (_utc(), matter_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def has_matter_access(user_id: str, matter_id: str) -> bool:
    return _user_can_access_matter(user_id, matter_id)


def get_matter_access_context(user_id: str, matter_id: str) -> Optional[Dict[str, str]]:
    """
    Resolve matter access and owner context.
    Returns {'owner_user_id', 'request_user_id', 'role'} where role is owner/viewer/lawyer/client.
    """
    m = _fetch_matter_row(matter_id)
    if not m:
        return None
    uid = str(user_id)
    owner_uid = str(m.get("user_id") or "")
    if owner_uid == uid:
        return {
            "owner_user_id": owner_uid,
            "request_user_id": uid,
            "role": "owner",
        }
    org_id = str(m.get("org_id") or "")
    if org_id and user_in_org(uid, org_id):
        org_role = get_org_member_role(uid, org_id)
        if org_role == "owner":
            matter_role = "owner" if owner_uid == uid else "lawyer"
        elif org_role in ("lawyer", "member"):
            matter_role = "lawyer"
        elif org_role == "viewer":
            matter_role = "viewer"
        else:
            matter_role = "lawyer"
        return {
            "owner_user_id": owner_uid,
            "request_user_id": uid,
            "role": matter_role,
        }
    conn = connect_app_db()
    row = conn.execute(
        """
        SELECT m.user_id, mm.role
        FROM matter_members mm
        JOIN matters m ON m.matter_id = mm.matter_id
        WHERE mm.matter_id = ? AND mm.user_id = ?
        LIMIT 1
        """,
        (matter_id, uid),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "owner_user_id": str(row[0]),
        "request_user_id": uid,
        "role": str(row[1] or "viewer"),
    }


def add_matter_note(
    user_id: str,
    matter_id: str,
    raw_content: str,
    *,
    anonymized_content: str = "",
) -> Optional[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return None
    ensure_practice_schema()
    nid = str(uuid.uuid4())
    now = _utc()
    conn = connect_app_db()
    conn.execute(
        """
        INSERT INTO matter_notes
        (note_id, matter_id, author_id, raw_content, anonymized_content, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            nid,
            matter_id,
            str(user_id),
            raw_content.strip(),
            anonymized_content.strip(),
            now,
        ),
    )
    conn.execute(
        "UPDATE matters SET updated_at = ? WHERE matter_id = ?",
        (now, matter_id),
    )
    conn.commit()
    conn.close()
    return {"note_id": nid, "matter_id": matter_id, "timestamp": now}


def list_matter_notes(user_id: str, matter_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_app_db()
    rows = conn.execute(
        """
        SELECT note_id, matter_id, author_id, raw_content, anonymized_content, timestamp
        FROM matter_notes WHERE matter_id = ?
        ORDER BY timestamp DESC LIMIT ?
        """,
        (matter_id, limit),
    ).fetchall()
    conn.close()
    return [
        {
            "note_id": r[0],
            "matter_id": r[1],
            "author_id": r[2],
            "raw_content": r[3],
            "anonymized_content": r[4],
            "timestamp": r[5],
        }
        for r in rows
    ]


def link_document_to_matter(
    user_id: str,
    document_id: str,
    matter_id: str,
    *,
    rebuild_index: bool = True,
) -> bool:
    if not get_matter(user_id, matter_id):
        return False
    conn = connect_app_db()
    old = conn.execute(
        "SELECT matter_id FROM documents WHERE id = ? AND uploader_id = ?",
        (document_id, str(user_id)),
    ).fetchone()
    prev_matter = str(old[0] or "").strip() if old else ""
    cur = conn.execute(
        """
        UPDATE documents SET matter_id = ?
        WHERE id = ? AND uploader_id = ?
        """,
        (matter_id, document_id, str(user_id)),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    # region agent log
    try:
        from backend.app.core.debug_matter_index_log import matter_index_log

        matter_index_log(
            "H1",
            "matter_repo.py:link_document_to_matter",
            "document_linked",
            {
                "document_id": str(document_id)[:36],
                "matter_id": str(matter_id)[:36],
                "prev_matter": prev_matter[:36],
                "rebuild_index": bool(rebuild_index),
                "ok": bool(ok),
            },
        )
    except Exception:
        pass
    # endregion
    if ok and rebuild_index:
        try:
            from app import build_faiss_index

            if prev_matter and prev_matter != matter_id:
                build_faiss_index(user_id, incremental=False, matter_id=prev_matter)
            build_faiss_index(user_id, incremental=False, matter_id=matter_id)
            # region agent log
            try:
                from backend.app.core.debug_matter_index_log import matter_index_log
                from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
                from backend.app.core.matter_index import get_matter_index_dir

                idx = get_matter_index_dir(str(user_id), matter_id)
                matter_index_log(
                    "H5",
                    "matter_repo.py:link_document_to_matter",
                    "rebuild_after_link",
                    {
                        "matter_id": str(matter_id)[:36],
                        "index_dir": str(idx),
                        "vectors": count_index_vectors(idx) if index_exists(idx) else 0,
                    },
                )
            except Exception:
                pass
            # endregion
        except Exception as exc:
            # region agent log
            try:
                from backend.app.core.debug_matter_index_log import matter_index_log

                matter_index_log(
                    "H5",
                    "matter_repo.py:link_document_to_matter",
                    "rebuild_failed",
                    {"matter_id": str(matter_id)[:36], "error": str(exc)[:300]},
                )
            except Exception:
                pass
            # endregion
    return ok


def list_matter_documents(
    user_id: str, matter_id: str, *, limit: int = 200, offset: int = 0
) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_app_db()
    rows = []
    try:
        rows = conn.execute(
            """
            SELECT id, filename, pages, uploaded_at, privileged, index_status
            FROM documents
            WHERE uploader_id = ? AND matter_id = ?
            ORDER BY uploaded_at DESC
            LIMIT ? OFFSET ?
            """,
            (str(user_id), matter_id, limit, offset),
        ).fetchall()
    except Exception:
        try:
            rows = conn.execute(
                """
                SELECT id, filename, pages, uploaded_at
                FROM documents
                WHERE uploader_id = ? AND matter_id = ?
                ORDER BY uploaded_at DESC
                LIMIT ? OFFSET ?
                """,
                (str(user_id), matter_id, limit, offset),
            ).fetchall()
        except Exception:
            rows = []
    conn.close()
    return [
        {
            "document_id": r[0],
            "filename": r[1],
            "pages": r[2],
            "uploaded_at": r[3],
            "privileged": bool(r[4]) if len(r) > 4 else False,
            "index_status": r[5] if len(r) > 5 else None,
        }
        for r in rows
    ]


def matter_workflow_signal(user_id: str, matter: Dict[str, Any], note_text: str) -> None:
    try:
        from backend.app.core.adaptive_learning import record_interaction

        area = matter.get("matter_type") or matter.get("practice_area") or "General"
        record_interaction(
            str(user_id),
            "matter_workflow",
            f"[{area}] {matter.get('matter_name', '')}",
            answer=note_text[:500],
            implicit_signal="matter_note",
        )
    except Exception:
        pass
