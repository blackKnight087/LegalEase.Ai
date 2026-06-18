"""Collaboration Hub — rooms, messaging, search, notifications."""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Tuple

from backend.app.core.collab_schema import ensure_collab_schema
from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import insert_or_ignore, insert_or_replace
from backend.app.core.collab_timeline import log_collab_timeline
from backend.app.core.matter_repo import get_matter, get_matter_access_context, list_matters
from backend.app.core.matter_workflow import add_deadline, add_task
from backend.app.core.org_service import get_primary_org_id, list_org_members, user_in_org

logger = logging.getLogger("legalease.collab")

ROOT = Path(__file__).resolve().parents[3]
UPLOAD_ROOT = ROOT / "Data" / "collab_uploads"

# Soft anti-spam (not HTTP rate limits): duplicate body within 2s per user+room.
_recent_message_fingerprints: DefaultDict[str, List[Tuple[float, str]]] = defaultdict(list)

DEFAULT_CHANNELS = [
    ("general", "General", "firm"),
    ("management", "Management", "firm"),
    ("associates", "Associates", "firm"),
    ("criminal-team", "Criminal Team", "practice"),
    ("civil-team", "Civil Team", "practice"),
    ("corporate-team", "Corporate Team", "practice"),
    ("litigation", "Litigation", "practice"),
    ("client-intake", "Client Intake", "firm"),
    ("hearing-prep", "Hearing Prep", "firm"),
]


def collab_scope_id(user_id: str) -> str:
    """Firm org id, or personal workspace id for solo accounts."""
    return get_primary_org_id(user_id) or f"personal:{user_id}"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return (s[:60] or "room").strip("-")


def _dm_key(user_a: str, user_b: str) -> str:
    return ":".join(sorted([str(user_a), str(user_b)]))


def _row_room(row: Tuple) -> Dict[str, Any]:
    return {
        "room_id": row[0],
        "org_id": row[1],
        "room_type": row[2],
        "matter_id": row[3] or "",
        "dm_key": row[4] or "",
        "slug": row[5] or "",
        "name": row[6],
        "description": row[7] or "",
        "is_private": bool(row[8]),
        "created_by": row[9],
        "created_at": row[10],
        "updated_at": row[11],
    }


def _audit(org_id: str, user_id: str, action: str, resource_type: str, resource_id: str, detail: Dict[str, Any]) -> None:
    ensure_collab_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO collab_audit_logs
        (log_id, org_id, user_id, action, resource_type, resource_id, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            org_id,
            user_id,
            action,
            resource_type,
            resource_id,
            json.dumps(detail or {}),
            _utc(),
        ),
    )
    conn.commit()
    conn.close()


def _username_map(org_id: str) -> Dict[str, str]:
    conn = connect_data_db()
    if org_id and not org_id.startswith("personal:"):
        rows = conn.execute(
            """
            SELECT om.user_id, COALESCE(u.username, u.id)
            FROM org_members om
            LEFT JOIN users u ON u.id = om.user_id
            WHERE om.org_id = ?
            """,
            (org_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, COALESCE(username, id) FROM users LIMIT 200",
        ).fetchall()
    conn.close()
    return {str(r[0]): str(r[1]) for r in rows}


def _users_from_auth_db(exclude_user_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    """Load users from login DB (legalease.db) — reliable when data DB is empty."""
    try:
        from legalease_auth import ensure_db, run_query

        ensure_db()
        rows = run_query(
            """
            SELECT id, COALESCE(NULLIF(username, ''), id)
            FROM users WHERE id != ?
            ORDER BY username ASC LIMIT ?
            """,
            (str(exclude_user_id), limit),
            fetch=True,
        ) or []
        return [{"user_id": r[0], "username": r[1], "role": "member"} for r in rows]
    except Exception:
        return []


def list_collab_members(user_id: str) -> List[Dict[str, Any]]:
    org_id = get_primary_org_id(user_id)
    if org_id:
        members = list_org_members(org_id, user_id)
        if members:
            return members
    auth_users = _users_from_auth_db(user_id)
    if auth_users:
        return auth_users
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT id, COALESCE(username, id) FROM users
        WHERE id != ? ORDER BY username ASC LIMIT 100
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()
    return [{"user_id": r[0], "username": r[1], "role": "member"} for r in rows]


def _user_exists(user_id: str) -> bool:
    try:
        from legalease_auth import get_user_by_id

        if get_user_by_id(str(user_id)):
            return True
    except Exception:
        pass
    conn = connect_data_db()
    row = conn.execute("SELECT 1 FROM users WHERE id = ? LIMIT 1", (str(user_id),)).fetchone()
    conn.close()
    return bool(row)


def are_users_connected(user_id: str, peer_user_id: str) -> bool:
    if user_id == peer_user_id:
        return False
    ensure_collab_schema()
    pk = _dm_key(user_id, peer_user_id)
    conn = connect_data_db()
    row = conn.execute(
        "SELECT 1 FROM collab_connections WHERE pair_key = ? LIMIT 1",
        (pk,),
    ).fetchone()
    if row:
        conn.close()
        return True
    room_row = conn.execute(
        "SELECT room_id FROM collab_rooms WHERE dm_key = ? AND room_type = 'dm' LIMIT 1",
        (pk,),
    ).fetchone()
    if room_row:
        rid = str(room_row[0])
        mems = conn.execute(
            "SELECT user_id FROM collab_room_members WHERE room_id = ?",
            (rid,),
        ).fetchall()
        conn.close()
        ids = {str(m[0]) for m in mems}
        if user_id in ids and peer_user_id in ids:
            _register_connection(user_id, peer_user_id, rid)
            return True
    conn.close()
    return False


def _connection_status(user_id: str, other_id: str) -> str:
    """none | connected | pending_sent | pending_received"""
    try:
        if are_users_connected(user_id, other_id):
            return "connected"
        ensure_collab_schema()
        conn = connect_data_db()
        out = conn.execute(
            """
            SELECT 1 FROM collab_chat_requests
            WHERE from_user_id = ? AND to_user_id = ? AND status = 'pending' LIMIT 1
            """,
            (user_id, other_id),
        ).fetchone()
        inc = conn.execute(
            """
            SELECT 1 FROM collab_chat_requests
            WHERE from_user_id = ? AND to_user_id = ? AND status = 'pending' LIMIT 1
            """,
            (other_id, user_id),
        ).fetchone()
        conn.close()
        if out:
            return "pending_sent"
        if inc:
            return "pending_received"
    except Exception:
        pass
    return "none"


def search_users_by_username(
    user_id: str,
    query: str,
    *,
    limit: int = 20,
    your_username: str = "",
) -> Dict[str, Any]:
    from backend.app.core.user_search import (
        iter_user_search_rows,
        normalize_user_search_query,
        search_hint_for_query,
    )

    q = normalize_user_search_query(query)
    if len(q) < 1:
        return {"users": [], "hint": "Type a username or email to search.", "your_username": your_username}
    ensure_collab_schema()
    min_len = 1 if len(q) >= 3 else 2
    if len(q) < min_len:
        return {
            "users": [],
            "hint": "Type at least 2 characters (3+ recommended).",
            "your_username": your_username,
        }
    rows = iter_user_search_rows(user_id, q, limit=limit)
    out: List[Dict[str, Any]] = []
    for r in rows:
        oid = str(r[0])
        uname = str(r[1] or oid)
        display = str(r[2] or "").strip() if len(r) > 2 else ""
        is_self = oid == str(user_id)
        out.append(
            {
                "user_id": oid,
                "username": uname,
                "display_name": display,
                "is_self": is_self,
                "connection_status": "self" if is_self else _connection_status(user_id, oid),
            }
        )
    hint = search_hint_for_query(user_id, q, len(out), your_username=your_username)
    return {"users": out, "hint": hint, "your_username": your_username, "query": q}


def list_chat_requests(user_id: str) -> Dict[str, List[Dict[str, Any]]]:
    ensure_collab_schema()
    conn = connect_data_db()
    incoming_rows = conn.execute(
        """
        SELECT r.request_id, r.from_user_id, r.intro_message, r.status, r.created_at,
               COALESCE(u.username, r.from_user_id)
        FROM collab_chat_requests r
        LEFT JOIN users u ON u.id = r.from_user_id
        WHERE r.to_user_id = ? AND r.status = 'pending'
        ORDER BY r.created_at DESC
        """,
        (str(user_id),),
    ).fetchall()
    outgoing_rows = conn.execute(
        """
        SELECT r.request_id, r.to_user_id, r.intro_message, r.status, r.created_at,
               COALESCE(u.username, r.to_user_id)
        FROM collab_chat_requests r
        LEFT JOIN users u ON u.id = r.to_user_id
        WHERE r.from_user_id = ? AND r.status = 'pending'
        ORDER BY r.created_at DESC
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()
    return {
        "incoming": [
            {
                "request_id": r[0],
                "from_user_id": r[1],
                "intro_message": r[2] or "",
                "status": r[3],
                "created_at": r[4],
                "from_username": r[5],
            }
            for r in incoming_rows
        ],
        "outgoing": [
            {
                "request_id": r[0],
                "to_user_id": r[1],
                "intro_message": r[2] or "",
                "status": r[3],
                "created_at": r[4],
                "to_username": r[5],
            }
            for r in outgoing_rows
        ],
    }


def _register_connection(user_id: str, peer_user_id: str, room_id: str) -> None:
    ensure_collab_schema()
    pk = _dm_key(user_id, peer_user_id)
    conn = connect_data_db()
    insert_or_ignore(
        conn,
        """
        INSERT OR IGNORE INTO collab_connections
        (connection_id, user_a, user_b, pair_key, room_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        """
        INSERT INTO collab_connections
        (connection_id, user_a, user_b, pair_key, room_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (pair_key) DO NOTHING
        """,
        (str(uuid.uuid4()), user_id, peer_user_id, pk, room_id, _utc()),
    )
    conn.commit()
    conn.close()


def _create_dm_room(user_id: str, peer_user_id: str) -> Dict[str, Any]:
    """Create DM room (caller must verify connection first)."""
    ensure_collab_schema()
    scope = collab_scope_id(user_id)
    dm = _dm_key(user_id, peer_user_id)
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT room_id, org_id, room_type, matter_id, dm_key, slug, name, description,
               is_private, created_by, created_at, updated_at
        FROM collab_rooms WHERE dm_key = ? AND room_type = 'dm' LIMIT 1
        """,
        (dm,),
    ).fetchone()
    if row:
        conn.close()
        room = _row_room(row)
        _add_room_member(room["room_id"], user_id)
        _add_room_member(room["room_id"], peer_user_id)
        _register_connection(user_id, peer_user_id, room["room_id"])
        return room
    names = _username_map(scope)
    peer_name = names.get(peer_user_id, "Colleague")
    my_name = names.get(user_id, "You")
    rid = str(uuid.uuid4())
    now = _utc()
    title = f"{my_name} ↔ {peer_name}"
    conn.execute(
        """
        INSERT INTO collab_rooms
        (room_id, org_id, room_type, matter_id, dm_key, slug, name, description, is_private, created_by, created_at, updated_at)
        VALUES (?, ?, 'dm', '', ?, '', ?, '', 1, ?, ?, ?)
        """,
        (rid, scope, dm, title, user_id, now, now),
    )
    conn.commit()
    conn.close()
    _add_room_member(rid, user_id)
    _add_room_member(rid, peer_user_id)
    _register_connection(user_id, peer_user_id, rid)
    _audit(scope, user_id, "dm_created", "room", rid, {"peer": peer_user_id})
    return get_room(user_id, rid) or {}


def send_chat_request(
    user_id: str,
    to_user_id: str,
    *,
    intro_message: str = "",
) -> Dict[str, Any]:
    if user_id == to_user_id:
        raise ValueError("Cannot message yourself")
    if not _user_exists(to_user_id):
        raise ValueError("User not found — check the username and try again")
    ensure_collab_schema()
    if are_users_connected(user_id, to_user_id):
        room = _create_dm_room(user_id, to_user_id)
        return {"status": "connected", "room": room}
    st = _connection_status(user_id, to_user_id)
    if st == "pending_sent":
        return {"status": "pending_sent", "message": "Request already sent — waiting for them to accept."}
    if st == "pending_received":
        return accept_chat_request_by_users(to_user_id, user_id)
    rid = str(uuid.uuid4())
    now = _utc()
    intro = (intro_message or "Would like to chat with you on Firm Chat.").strip()[:500]
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO collab_chat_requests
        (request_id, from_user_id, to_user_id, intro_message, status, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
        """,
        (rid, user_id, to_user_id, intro, now),
    )
    conn.commit()
    conn.close()
    from_name = _username_map(collab_scope_id(user_id)).get(user_id, "Someone")
    _notify(
        to_user_id,
        "",
        "chat_request",
        f"{from_name} wants to chat on Firm Chat",
        intro,
        "/collaboration",
    )
    return {"status": "pending_sent", "request_id": rid, "message": "Chat request sent. They must accept before you can message."}


def accept_chat_request(user_id: str, request_id: str) -> Dict[str, Any]:
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT request_id, from_user_id, to_user_id, intro_message
        FROM collab_chat_requests
        WHERE request_id = ? AND status = 'pending' LIMIT 1
        """,
        (request_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError("Request not found or already handled")
    if str(row[2]) != str(user_id):
        raise PermissionError("Only the recipient can accept this request")
    return accept_chat_request_by_users(str(row[1]), str(row[2]), request_id=str(row[0]))


def accept_chat_request_by_users(
    from_user_id: str,
    to_user_id: str,
    *,
    request_id: str = "",
) -> Dict[str, Any]:
    ensure_collab_schema()
    now = _utc()
    conn = connect_data_db()
    if request_id:
        conn.execute(
            "UPDATE collab_chat_requests SET status = 'accepted', responded_at = ? WHERE request_id = ?",
            (now, request_id),
        )
    else:
        conn.execute(
            """
            UPDATE collab_chat_requests SET status = 'accepted', responded_at = ?
            WHERE from_user_id = ? AND to_user_id = ? AND status = 'pending'
            """,
            (now, from_user_id, to_user_id),
        )
        conn.execute(
            """
            UPDATE collab_chat_requests SET status = 'accepted', responded_at = ?
            WHERE from_user_id = ? AND to_user_id = ? AND status = 'pending'
            """,
            (now, to_user_id, from_user_id),
        )
    conn.commit()
    conn.close()
    room = _create_dm_room(from_user_id, to_user_id)
    accepter = _username_map(collab_scope_id(to_user_id)).get(to_user_id, "They")
    _notify(
        from_user_id,
        "",
        "chat_request_accepted",
        f"{accepter} accepted your chat request",
        "You can now message each other in Firm Chat.",
        f"/collaboration?room={room.get('room_id', '')}",
        room.get("room_id", ""),
    )
    return {"status": "connected", "room": room}


def reject_chat_request(user_id: str, request_id: str) -> Dict[str, Any]:
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT to_user_id FROM collab_chat_requests WHERE request_id = ? AND status = 'pending'",
        (request_id,),
    ).fetchone()
    if not row or str(row[0]) != str(user_id):
        conn.close()
        raise PermissionError("Cannot reject this request")
    conn.execute(
        "UPDATE collab_chat_requests SET status = 'rejected', responded_at = ? WHERE request_id = ?",
        (_utc(), request_id),
    )
    conn.commit()
    conn.close()
    return {"status": "rejected"}


def _check_message_spam(user_id: str, room_id: str, body: str) -> None:
    """Duplicate detection — avoids accidental double-send, not normal chat volume."""
    key = f"{user_id}:{room_id}"
    now = time.time()
    norm = (body or "").strip().lower()
    window = _recent_message_fingerprints[key]
    window[:] = [(t, b) for t, b in window if now - t < 2.0]
    if norm and any(b == norm for _, b in window):
        raise ValueError("Duplicate message — wait a moment before resending.")
    if norm:
        window.append((now, norm))


def _notify(
    user_id: str,
    org_id: str,
    ntype: str,
    title: str,
    body: str = "",
    link_path: str = "",
    room_id: str = "",
    message_id: str = "",
) -> None:
    ensure_collab_schema()
    nid = str(uuid.uuid4())
    created = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO collab_notifications
        (notification_id, user_id, org_id, notification_type, title, body, link_path, room_id, message_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (nid, user_id, org_id, ntype, title, body, link_path, room_id, message_id, created),
    )
    conn.commit()
    conn.close()
    try:
        from backend.app.core.collab_realtime import publish_notification

        publish_notification(
            user_id,
            {
                "notification_id": nid,
                "notification_type": ntype,
                "title": title,
                "body": body,
                "link_path": link_path,
                "room_id": room_id,
                "message_id": message_id,
                "created_at": created,
            },
        )
    except Exception:
        pass
    if ntype in ("message", "mention"):
        _maybe_email_collab_notify(user_id, title, body, link_path)


def _maybe_email_collab_notify(
    user_id: str, title: str, body: str, link_path: str
) -> None:
    try:
        from legalease_auth import get_user_by_id

        user = get_user_by_id(str(user_id))
        email = (user or {}).get("email") or (user or {}).get("username") or ""
        if not email or "@" not in str(email):
            return
        from backend.app.core.email_service import send_email

        app_url = os.getenv("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")
        link = f"{app_url}{link_path}" if link_path.startswith("/") else link_path
        html = f"<p><b>{title}</b></p><p>{body}</p><p><a href='{link}'>Open in LegalEase</a></p>"
        send_email(str(email), f"LegalEase — {title}", html)
    except Exception:
        pass


def _message_seen_by(room_id: str, message_created_at: str, sender_id: str) -> List[str]:
    """User IDs who have read up to this message (read receipts)."""
    ensure_collab_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT user_id FROM collab_room_members
        WHERE room_id = ? AND user_id != ? AND last_read_at >= ?
        """,
        (room_id, sender_id, message_created_at),
    ).fetchall()
    conn.close()
    return [str(r[0]) for r in rows]


def _add_room_member(room_id: str, user_id: str, role: str = "member") -> None:
    ensure_collab_schema()
    conn = connect_data_db()
    insert_or_ignore(
        conn,
        """
        INSERT OR IGNORE INTO collab_room_members (room_id, user_id, member_role, joined_at, last_read_at)
        VALUES (?, ?, ?, ?, '')
        """,
        """
        INSERT INTO collab_room_members (room_id, user_id, member_role, joined_at, last_read_at)
        VALUES (?, ?, ?, ?, '')
        ON CONFLICT (room_id, user_id) DO NOTHING
        """,
        (room_id, user_id, role, _utc()),
    )
    conn.commit()
    conn.close()


def _user_in_room(user_id: str, room_id: str) -> bool:
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT 1 FROM collab_room_members WHERE room_id = ? AND user_id = ? LIMIT 1",
        (room_id, user_id),
    ).fetchone()
    conn.close()
    return bool(row)


def _count_room_members(room_id: str) -> int:
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT COUNT(*) FROM collab_room_members WHERE room_id = ?",
        (room_id,),
    ).fetchone()
    conn.close()
    return int(row[0] if row else 0)


def _require_room_access(user_id: str, room_id: str) -> Dict[str, Any]:
    room = get_room(user_id, room_id)
    if not room:
        raise PermissionError("Room not found or access denied")
    if room.get("room_type") == "dm":
        if _count_room_members(room_id) > 2:
            raise PermissionError("Invalid private chat configuration")
        if not _dm_peer_id(user_id, room_id):
            raise PermissionError("Private chat access denied")
    return room


def _enrich_dm_room(user_id: str, room: Dict[str, Any]) -> Dict[str, Any]:
    """Show only the other party's name — DMs are never listed for non-members."""
    if room.get("room_type") != "dm":
        return room
    peer = _dm_peer_id(user_id, room["room_id"])
    if not peer:
        return room
    names = _username_map(room.get("org_id", ""))
    room = dict(room)
    room["peer_user_id"] = peer
    room["name"] = names.get(peer, "Direct message")
    room["is_private_dm"] = True
    room["description"] = "Private 1-to-1 — only you two can read this (free on all accounts)"
    return room


def _message_notify_preview(body: str, message_type: str) -> str:
    if message_type == "voice":
        return "Voice message"
    return (body or "").strip()[:120] or "New message"


def seed_org_channels(org_id: str, creator_id: str) -> None:
    ensure_collab_schema()
    for slug, name, _ in DEFAULT_CHANNELS:
        conn = connect_data_db()
        exists = conn.execute(
            "SELECT 1 FROM collab_rooms WHERE org_id = ? AND slug = ? LIMIT 1",
            (org_id, slug),
        ).fetchone()
        conn.close()
        if exists:
            continue
        try:
            create_channel(creator_id, slug=slug, name=name, org_id=org_id)
        except Exception as exc:
            logger.debug("seed channel %s: %s", slug, exc)


def create_channel(
    user_id: str,
    *,
    slug: str,
    name: str,
    org_id: str = "",
    description: str = "",
    channel_type: str = "firm",
) -> Dict[str, Any]:
    ensure_collab_schema()
    oid = org_id or collab_scope_id(user_id)
    if oid.startswith("personal:"):
        if str(user_id) != oid.split(":", 1)[-1]:
            raise PermissionError("Not in workspace")
        members = [{"user_id": user_id}]
    elif not user_in_org(user_id, oid):
        raise PermissionError("Not in organization")
    else:
        members = list_org_members(oid, user_id)
    slug_norm = _slugify(slug)
    rid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO collab_rooms
        (room_id, org_id, room_type, matter_id, dm_key, slug, name, description, is_private, created_by, created_at, updated_at)
        VALUES (?, ?, 'channel', '', '', ?, ?, ?, 0, ?, ?, ?)
        """,
        (rid, oid, slug_norm, name.strip(), description, user_id, now, now),
    )
    conn.commit()
    conn.close()
    for m in members:
        _add_room_member(rid, str(m["user_id"]))
    _audit(oid, user_id, "channel_created", "room", rid, {"slug": slug_norm, "channel_type": channel_type})
    return get_room(user_id, rid) or {}


def get_or_create_dm(user_id: str, peer_user_id: str) -> Dict[str, Any]:
    ensure_collab_schema()
    if user_id == peer_user_id:
        raise ValueError("Cannot DM yourself")
    if not _user_exists(peer_user_id):
        raise ValueError("User not found")
    if not are_users_connected(user_id, peer_user_id):
        raise PermissionError(
            "Not connected yet. Search their username and send a chat request — they must accept first."
        )
    return _create_dm_room(user_id, peer_user_id)


def ensure_matter_room(user_id: str, matter_id: str) -> Dict[str, Any]:
    ensure_collab_schema()
    if not get_matter_access_context(user_id, matter_id):
        raise PermissionError("Matter access denied")
    matter = get_matter(user_id, matter_id) or {}
    org_id = str(matter.get("org_id") or collab_scope_id(user_id))
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT room_id, org_id, room_type, matter_id, dm_key, slug, name, description,
               is_private, created_by, created_at, updated_at
        FROM collab_rooms WHERE matter_id = ? LIMIT 1
        """,
        (matter_id,),
    ).fetchone()
    conn.close()
    if row:
        room = _row_room(row)
        _sync_matter_room_members(user_id, matter_id, room["room_id"])
        return room
    mname = (matter.get("matter_name") or matter.get("title") or "Matter").strip()
    slug = _slugify(mname)
    rid = str(uuid.uuid4())
    now = _utc()
    display = mname if mname.startswith("#") else f"# {mname}"
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO collab_rooms
        (room_id, org_id, room_type, matter_id, dm_key, slug, name, description, is_private, created_by, created_at, updated_at)
        VALUES (?, ?, 'matter', ?, '', ?, ?, ?, 0, ?, ?, ?)
        """,
        (rid, org_id, matter_id, slug, display, f"Matter room — {mname}", user_id, now, now),
    )
    conn.commit()
    conn.close()
    _sync_matter_room_members(user_id, matter_id, rid)
    _audit(org_id, user_id, "matter_room_created", "room", rid, {"matter_id": matter_id})
    return get_room(user_id, rid) or {}


def _sync_matter_room_members(user_id: str, matter_id: str, room_id: str) -> None:
    from backend.app.core.matter_enhancements import list_matter_members

    _add_room_member(room_id, user_id, "member")
    owner = get_matter(user_id, matter_id)
    if owner and owner.get("user_id"):
        _add_room_member(room_id, str(owner["user_id"]), "owner")
    try:
        for m in list_matter_members(user_id, matter_id):
            _add_room_member(room_id, str(m.get("user_id", "")), str(m.get("role", "member")))
    except Exception:
        pass
    org_id = get_primary_org_id(user_id)
    if org_id:
        for m in list_org_members(org_id, user_id):
            _add_room_member(room_id, str(m["user_id"]))


def get_room(user_id: str, room_id: str) -> Optional[Dict[str, Any]]:
    ensure_collab_schema()
    if not _user_in_room(user_id, room_id):
        return None
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT room_id, org_id, room_type, matter_id, dm_key, slug, name, description,
               is_private, created_by, created_at, updated_at
        FROM collab_rooms WHERE room_id = ?
        """,
        (room_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    room = _enrich_dm_room(user_id, _row_room(row))
    room["unread_count"] = unread_count(user_id, room_id)
    return room


def _sync_accessible_matter_rooms(user_id: str) -> None:
    """Ensure each accessible matter has a dedicated Firm Chat channel."""
    for m in list_matters(user_id, limit=80):
        mid = str(m.get("matter_id") or "")
        if not mid:
            continue
        try:
            if get_matter_access_context(user_id, mid):
                ensure_matter_room(user_id, mid)
        except Exception as exc:
            logger.debug("matter room sync %s: %s", mid, exc)


def _message_preview_text(body: str, message_type: str) -> str:
    if message_type == "voice":
        return "Voice message"
    if message_type == "task_ref":
        return "Task linked in chat"
    b = (body or "").strip()
    if b.startswith("📎"):
        return b.replace("📎", "").strip() or "Attachment"
    return b[:120] if b else ""


def _room_last_message(room_id: str, org_id: str) -> Dict[str, Any]:
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT m.body, m.message_type, m.created_at, m.sender_id
        FROM collab_messages m
        WHERE m.room_id = ? AND m.deleted_at = ''
        ORDER BY m.created_at DESC LIMIT 1
        """,
        (room_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {}
    names = _username_map(org_id)
    return {
        "last_message_preview": _message_preview_text(row[0], row[1]),
        "last_message_at": row[2],
        "last_sender_id": row[3],
        "last_sender_name": names.get(row[3], ""),
    }


def list_rooms(user_id: str) -> List[Dict[str, Any]]:
    ensure_collab_schema()
    scope = collab_scope_id(user_id)
    seed_org_channels(scope, user_id)
    _sync_accessible_matter_rooms(user_id)
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT r.room_id, r.org_id, r.room_type, r.matter_id, r.dm_key, r.slug, r.name,
               r.description, r.is_private, r.created_by, r.created_at, r.updated_at
        FROM collab_rooms r
        INNER JOIN collab_room_members m ON m.room_id = r.room_id AND m.user_id = ?
        ORDER BY r.updated_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        room = _enrich_dm_room(user_id, _row_room(row))
        room["unread_count"] = unread_count(user_id, room["room_id"])
        room.update(_room_last_message(room["room_id"], room.get("org_id", "")))
        out.append(room)
    return out


def unread_count(user_id: str, room_id: str) -> int:
    ensure_collab_schema()
    conn = connect_data_db()
    mem = conn.execute(
        "SELECT last_read_at FROM collab_room_members WHERE room_id = ? AND user_id = ?",
        (room_id, user_id),
    ).fetchone()
    last_read = (mem[0] if mem else "") or "1970-01-01"
    n = conn.execute(
        """
        SELECT COUNT(*) FROM collab_messages
        WHERE room_id = ? AND sender_id != ? AND created_at > ? AND deleted_at = ''
        """,
        (room_id, user_id, last_read),
    ).fetchone()
    conn.close()
    return int(n[0] if n else 0)


def mark_room_read(user_id: str, room_id: str) -> None:
    _require_room_access(user_id, room_id)
    ensure_collab_schema()
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        "UPDATE collab_room_members SET last_read_at = ? WHERE room_id = ? AND user_id = ?",
        (now, room_id, user_id),
    )
    conn.commit()
    conn.close()


def _parse_mentions(body: str, org_id: str) -> List[str]:
    names = _username_map(org_id)
    by_name = {v.lower(): k for k, v in names.items()}
    found: List[str] = []
    for m in re.finditer(r"@([A-Za-z0-9_.-]+)", body or ""):
        uname = m.group(1).lower()
        uid = by_name.get(uname)
        if uid and uid not in found:
            found.append(uid)
    return found


def list_messages(
    user_id: str,
    room_id: str,
    *,
    before: str = "",
    since: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    room = _require_room_access(user_id, room_id)
    ensure_collab_schema()
    limit = max(1, min(100, int(limit)))
    names = _username_map(room.get("org_id", ""))
    conn = connect_data_db()
    if since:
        rows = conn.execute(
            """
            SELECT message_id, room_id, sender_id, body, message_type, parent_id,
                   metadata_json, pinned, created_at, edited_at
            FROM collab_messages
            WHERE room_id = ? AND deleted_at = '' AND created_at > ?
            ORDER BY created_at ASC LIMIT ?
            """,
            (room_id, since, limit),
        ).fetchall()
    elif before:
        rows = conn.execute(
            """
            SELECT message_id, room_id, sender_id, body, message_type, parent_id,
                   metadata_json, pinned, created_at, edited_at
            FROM collab_messages
            WHERE room_id = ? AND deleted_at = '' AND created_at < ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (room_id, before, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT message_id, room_id, sender_id, body, message_type, parent_id,
                   metadata_json, pinned, created_at, edited_at
            FROM collab_messages
            WHERE room_id = ? AND deleted_at = ''
            ORDER BY created_at DESC LIMIT ?
            """,
            (room_id, limit),
        ).fetchall()
    conn.close()
    msgs = []
    ordered = rows if since else reversed(rows)
    for r in ordered:
        mid = r[0]
        meta = {}
        try:
            meta = json.loads(r[6] or "{}")
        except json.JSONDecodeError:
            pass
        seen_ids = _message_seen_by(room_id, r[8], r[2])
        seen_by = [names.get(uid, uid[:8]) for uid in seen_ids]
        msgs.append(
            {
                "message_id": mid,
                "room_id": r[1],
                "sender_id": r[2],
                "sender_name": names.get(r[2], r[2][:8]),
                "body": r[3],
                "message_type": r[4],
                "parent_id": r[5] or "",
                "metadata": meta,
                "pinned": bool(r[7]),
                "created_at": r[8],
                "edited_at": r[9] or "",
                "attachments": list_attachments(
                    mid,
                    org_id=room.get("org_id", ""),
                    matter_id=room.get("matter_id") or "",
                    matter_name=(
                        (get_matter(user_id, room["matter_id"]) or {}).get("matter_name", "")
                        if room.get("matter_id")
                        else ""
                    ),
                ),
                "reactions": list_reactions(mid),
                "seen_by": seen_by,
                "seen": len(seen_by) > 0,
            }
        )
    return msgs


def list_attachments(
    message_id: str,
    *,
    org_id: str = "",
    matter_id: str = "",
    matter_name: str = "",
) -> List[Dict[str, Any]]:
    ensure_collab_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT attachment_id, filename, mime_type, file_size, version, created_at, uploader_id, room_id
        FROM collab_attachments WHERE message_id = ?
        """,
        (message_id,),
    ).fetchall()
    conn.close()
    names = _username_map(org_id) if org_id else {}
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "attachment_id": r[0],
                "filename": r[1],
                "mime_type": r[2],
                "file_size": r[3],
                "version": r[4] or 1,
                "created_at": r[5],
                "uploader_id": r[6],
                "uploader_name": names.get(r[6], ""),
                "matter_id": matter_id,
                "matter_name": matter_name,
                "room_id": r[7] if len(r) > 7 else "",
            }
        )
    return out


def list_reactions(message_id: str) -> List[Dict[str, Any]]:
    ensure_collab_schema()
    conn = connect_data_db()
    rows = conn.execute(
        "SELECT emoji, user_id, created_at FROM collab_message_reactions WHERE message_id = ?",
        (message_id,),
    ).fetchall()
    conn.close()
    return [{"emoji": r[0], "user_id": r[1], "created_at": r[2]} for r in rows]


def _dm_peer_id(user_id: str, room_id: str) -> Optional[str]:
    conn = connect_data_db()
    rows = conn.execute(
        "SELECT user_id FROM collab_room_members WHERE room_id = ? AND user_id != ?",
        (room_id, user_id),
    ).fetchall()
    conn.close()
    if rows:
        return str(rows[0][0])
    return None


def send_message(
    user_id: str,
    room_id: str,
    *,
    body: str,
    message_type: str = "text",
    parent_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    room = _require_room_access(user_id, room_id)
    _check_message_spam(user_id, room_id, body)
    if room.get("room_type") == "dm":
        peer = _dm_peer_id(user_id, room_id)
        if peer and not are_users_connected(user_id, peer):
            raise PermissionError(
                "Chat not connected yet. Wait for them to accept your request, or accept theirs."
            )
    ensure_collab_schema()
    mid = str(uuid.uuid4())
    now = _utc()
    meta = json.dumps(metadata or {})
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO collab_messages
        (message_id, room_id, sender_id, body, message_type, parent_id, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (mid, room_id, user_id, (body or "").strip(), message_type, parent_id or "", meta, now),
    )
    conn.execute(
        "UPDATE collab_rooms SET updated_at = ? WHERE room_id = ?",
        (now, room_id),
    )
    conn.commit()
    conn.close()
    org_id = room.get("org_id", "")
    for uid in _parse_mentions(body, org_id):
        if uid != user_id:
            ensure_collab_schema()
            conn = connect_data_db()
            conn.execute(
                """
                INSERT INTO collab_mentions (mention_id, message_id, room_id, mentioned_user_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), mid, room_id, uid, now),
            )
            conn.commit()
            conn.close()
            sender = _username_map(org_id).get(user_id, "Someone")
            _notify(
                uid,
                org_id,
                "mention",
                f"{sender} mentioned you",
                (body or "")[:200],
                f"/collaboration?room={room_id}",
                room_id,
                mid,
            )
    conn = connect_data_db()
    members = conn.execute(
        "SELECT user_id FROM collab_room_members WHERE room_id = ? AND user_id != ?",
        (room_id, user_id),
    ).fetchall()
    conn.close()
    sender = _username_map(org_id).get(user_id, "Someone")
    preview = _message_notify_preview(body, message_type)
    is_dm = room.get("room_type") == "dm"
    for (uid,) in members:
        if uid not in _parse_mentions(body, org_id):
            if is_dm:
                title = f"New message from {sender}"
                notif_body = preview
            else:
                title = f"New message in {room.get('name', 'chat')}"
                notif_body = f"{sender}: {preview}"
            _notify(
                str(uid),
                org_id,
                "message",
                title,
                notif_body,
                f"/collaboration?room={room_id}",
                room_id,
                mid,
            )
    mark_room_read(user_id, room_id)
    _audit(org_id, user_id, "message_sent", "message", mid, {"room_id": room_id})
    matter_id = room.get("matter_id") or ""
    if matter_id and (body or "").strip() and message_type in ("text", ""):
        sender = _username_map(org_id).get(user_id, "Team member")
        snippet = (body or "").strip()[:160]
        log_collab_timeline(
            user_id,
            matter_id,
            title=f"{sender} — Firm Chat",
            description=snippet,
            event_type="discussion",
        )
    msgs = list_messages(user_id, room_id, limit=1)
    return msgs[-1] if msgs else {"message_id": mid, "body": body}


def add_reaction(user_id: str, message_id: str, emoji: str) -> Dict[str, Any]:
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT room_id FROM collab_messages WHERE message_id = ?",
        (message_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError("Message not found")
    room_id = row[0]
    _require_room_access(user_id, room_id)
    em = (emoji or "👍").strip()[:16]
    conn = connect_data_db()
    insert_or_replace(
        conn,
        """
        INSERT OR REPLACE INTO collab_message_reactions (message_id, user_id, emoji, created_at)
        VALUES (?, ?, ?, ?)
        """,
        """
        INSERT INTO collab_message_reactions (message_id, user_id, emoji, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (message_id, user_id, emoji) DO UPDATE SET created_at = EXCLUDED.created_at
        """,
        (message_id, user_id, em, _utc()),
    )
    conn.commit()
    conn.close()
    return {"message_id": message_id, "reactions": list_reactions(message_id)}


def save_attachment(
    user_id: str,
    room_id: str,
    message_id: str,
    *,
    filename: str,
    content: bytes,
    mime_type: str = "",
) -> Dict[str, Any]:
    room = _require_room_access(user_id, room_id)
    ensure_collab_schema()
    safe = re.sub(r"[^\w.\- ]", "_", filename or "file")[:180]
    aid = str(uuid.uuid4())
    dest_dir = UPLOAD_ROOT / (room.get("org_id") or "default") / room_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{aid}_{safe}"
    dest.write_bytes(content)
    now = _utc()
    conn = connect_data_db()
    prev = conn.execute(
        "SELECT COUNT(*) FROM collab_attachments WHERE room_id = ? AND filename = ?",
        (room_id, safe),
    ).fetchone()
    version = int((prev[0] if prev else 0) or 0) + 1
    conn.execute(
        """
        INSERT INTO collab_attachments
        (attachment_id, message_id, room_id, uploader_id, filename, saved_path, mime_type, file_size, version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (aid, message_id, room_id, user_id, safe, str(dest), mime_type, len(content), version, now),
    )
    conn.commit()
    conn.close()
    org_id = room.get("org_id", "")
    conn = connect_data_db()
    members = conn.execute(
        "SELECT user_id FROM collab_room_members WHERE room_id = ? AND user_id != ?",
        (room_id, user_id),
    ).fetchall()
    conn.close()
    for (uid,) in members:
        _notify(
            str(uid),
            org_id,
            "document",
            f"File shared in {room.get('name', 'room')}",
            safe,
            f"/collaboration?room={room_id}",
            room_id,
            message_id,
        )
    matter_id = room.get("matter_id") or ""
    if matter_id:
        uploader = _username_map(org_id).get(user_id, "Team member")
        log_collab_timeline(
            user_id,
            matter_id,
            title=f"{uploader} shared {safe}",
            description=f"Version v{version} · Firm Chat",
            event_type="document",
        )
    return {
        "attachment_id": aid,
        "filename": safe,
        "version": version,
        "mime_type": mime_type,
        "file_size": len(content),
    }


def get_attachment_path(user_id: str, attachment_id: str) -> Optional[Tuple[str, str]]:
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT room_id, filename, saved_path FROM collab_attachments WHERE attachment_id = ?",
        (attachment_id,),
    ).fetchone()
    conn.close()
    if not row or not _user_in_room(user_id, row[0]):
        return None
    path = Path(row[2])
    if not path.is_file():
        return None
    return row[1], str(path)


def create_task_from_message(
    user_id: str,
    message_id: str,
    *,
    title: str = "",
    assignee: str = "",
    due_date: str = "",
    priority: str = "Medium",
) -> Dict[str, Any]:
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT room_id, body, metadata_json FROM collab_messages WHERE message_id = ?",
        (message_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError("Message not found")
    room_id, body, meta_raw = row
    room = _require_room_access(user_id, room_id)
    matter_id = room.get("matter_id") or ""
    if not matter_id:
        raise ValueError("Tasks require a matter-linked room")
    meta = {}
    try:
        meta = json.loads(meta_raw or "{}")
    except json.JSONDecodeError:
        pass
    task_title = (title or body or "Task from chat").strip()[:500]
    task = add_task(user_id, matter_id, title=task_title, due_date=due_date, assignee=assignee, task_source="collab")
    meta["task_id"] = task.get("task_id")
    meta["priority"] = priority
    conn = connect_data_db()
    conn.execute(
        "UPDATE collab_messages SET message_type = 'task_ref', metadata_json = ? WHERE message_id = ?",
        (json.dumps(meta), message_id),
    )
    conn.commit()
    conn.close()
    if assignee and assignee != user_id:
        _notify(
            assignee,
            room.get("org_id", ""),
            "task",
            "Task assigned from Firm Chat",
            task_title,
            f"/matters/{matter_id}/tasks",
            room_id,
            message_id,
        )
    sender = _username_map(room.get("org_id", "")).get(user_id, "Team member")
    log_collab_timeline(
        user_id,
        matter_id,
        title=f"Task from chat: {task_title[:120]}",
        description=f"Created by {sender}",
        event_type="task",
    )
    return {"task": task, "matter_id": matter_id}


def create_deadline_from_message(
    user_id: str,
    message_id: str,
    *,
    title: str = "",
    due_date: str,
    deadline_type: str = "filing",
    notes: str = "",
) -> Dict[str, Any]:
    if not due_date:
        raise ValueError("due_date required")
    ensure_collab_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT room_id, body FROM collab_messages WHERE message_id = ?",
        (message_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError("Message not found")
    room = _require_room_access(user_id, row[0])
    matter_id = room.get("matter_id") or ""
    if not matter_id:
        raise ValueError("Deadlines require a matter-linked room")
    dl_title = (title or row[1] or "Deadline from chat").strip()[:500]
    dl = add_deadline(
        user_id,
        matter_id,
        title=dl_title,
        due_date=due_date,
        deadline_type=deadline_type,
        notes=notes,
    )
    log_collab_timeline(
        user_id,
        matter_id,
        title=f"Deadline from chat: {dl_title[:120]}",
        description=f"Due {due_date}",
        event_type="deadline",
    )
    return {"deadline": dl, "matter_id": matter_id}


def search_collab(user_id: str, query: str, *, limit: int = 40) -> Dict[str, Any]:
    ensure_collab_schema()
    q = (query or "").strip()
    if len(q) < 2:
        return {"messages": [], "rooms": [], "query": q}
    org_id = get_primary_org_id(user_id) or ""
    like = f"%{q}%"
    conn = connect_data_db()
    rooms = conn.execute(
        """
        SELECT r.room_id, r.name, r.room_type, r.slug
        FROM collab_rooms r
        INNER JOIN collab_room_members m ON m.room_id = r.room_id AND m.user_id = ?
        WHERE r.name LIKE ? OR r.slug LIKE ?
        LIMIT 15
        """,
        (user_id, like, like),
    ).fetchall()
    msgs = conn.execute(
        """
        SELECT m.message_id, m.room_id, m.body, m.created_at, r.name, r.room_type
        FROM collab_messages m
        INNER JOIN collab_room_members mem ON mem.room_id = m.room_id AND mem.user_id = ?
        INNER JOIN collab_rooms r ON r.room_id = m.room_id
        WHERE m.deleted_at = '' AND m.body LIKE ?
        ORDER BY m.created_at DESC LIMIT ?
        """,
        (user_id, like, min(limit, 50)),
    ).fetchall()
    conn.close()
    return {
        "query": q,
        "rooms": [
            {"room_id": r[0], "name": r[1], "room_type": r[2], "slug": r[3]}
            for r in rooms
        ],
        "messages": [
            {
                "message_id": m[0],
                "room_id": m[1],
                "body": m[2],
                "created_at": m[3],
                "room_name": m[4],
                "room_type": m[5] if len(m) > 5 else "",
            }
            for m in msgs
        ],
    }


def list_notifications(user_id: str, *, unread_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_collab_schema()
    conn = connect_data_db()
    if unread_only:
        rows = conn.execute(
            """
            SELECT notification_id, notification_type, title, body, link_path, room_id, message_id, created_at
            FROM collab_notifications
            WHERE user_id = ? AND read_at = ''
            ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, min(limit, 100)),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT notification_id, notification_type, title, body, link_path, room_id, message_id, created_at, read_at
            FROM collab_notifications
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, min(limit, 100)),
        ).fetchall()
    conn.close()
    if unread_only:
        return [
            {
                "notification_id": r[0],
                "type": r[1],
                "title": r[2],
                "body": r[3],
                "link_path": r[4],
                "room_id": r[5],
                "message_id": r[6],
                "created_at": r[7],
                "read": False,
            }
            for r in rows
        ]
    return [
        {
            "notification_id": r[0],
            "type": r[1],
            "title": r[2],
            "body": r[3],
            "link_path": r[4],
            "room_id": r[5],
            "message_id": r[6],
            "created_at": r[7],
            "read": bool(r[8]),
        }
        for r in rows
    ]


def mark_notification_read(user_id: str, notification_id: str) -> None:
    ensure_collab_schema()
    conn = connect_data_db()
    conn.execute(
        "UPDATE collab_notifications SET read_at = ? WHERE notification_id = ? AND user_id = ?",
        (_utc(), notification_id, user_id),
    )
    conn.commit()
    conn.close()


def _heuristic_digest(msgs: List[Dict[str, Any]]) -> Dict[str, Any]:
    action_items: List[str] = []
    open_issues: List[str] = []
    deadlines: List[str] = []
    decisions: List[str] = []
    for m in msgs:
        b = (m.get("body") or "").strip()
        if not b:
            continue
        low = b.lower()
        if any(w in low for w in ("decided", "agreed", "approved", "will proceed")):
            decisions.append(b[:200])
        if "?" in b or low.startswith(("need", "should we", "whether")):
            open_issues.append(b[:200])
        if any(w in low for w in ("by ", "before ", "deadline", "due", "hearing")):
            deadlines.append(b[:200])
        if any(w in low for w in ("verify", "review", "prepare", "file", "submit", "check")):
            action_items.append(b[:200])
    lines = [f"• {m.get('sender_name', '?')}: {(m.get('body') or '')[:160]}" for m in msgs[-25:]]
    return {
        "summary_text": "\n".join(lines) if lines else "No messages yet.",
        "key_decisions": decisions[-8:],
        "open_issues": open_issues[-8:],
        "action_items": action_items[-10:],
        "deadlines": deadlines[-8:],
    }


def summarize_room(user_id: str, room_id: str, *, limit: int = 100) -> Dict[str, Any]:
    room = _require_room_access(user_id, room_id)
    msgs = list_messages(user_id, room_id, limit=limit)
    base = _heuristic_digest(msgs)
    return {
        "room_id": room_id,
        "room_name": room.get("name"),
        "message_count": len(msgs),
        "matter_id": room.get("matter_id") or "",
        **base,
        "ai_note": "Quick digest from recent messages (no AI).",
    }


def room_context_panel(user_id: str, room_id: str) -> Dict[str, Any]:
    """Rich right-rail context for matter channels and DMs."""
    room = _require_room_access(user_id, room_id)
    org_id = room.get("org_id", "") or collab_scope_id(user_id)
    matter_id = room.get("matter_id") or ""
    panel: Dict[str, Any] = {
        "room_id": room_id,
        "room_type": room.get("room_type"),
        "room_name": room.get("name"),
        "matter_id": matter_id,
    }
    if matter_id:
        try:
            from backend.app.core.matter_workflow import list_deadlines, list_tasks, list_timeline
            from backend.app.core.matter_repo import list_matter_documents
            from backend.app.core.matter_enhancements import list_matter_members

            m = get_matter(user_id, matter_id) or {}
            tasks = list_tasks(user_id, matter_id)
            open_tasks = [t for t in tasks if str(t.get("status", "")).lower() in ("open", "pending", "")]
            deadlines = list_deadlines(user_id, matter_id)
            next_dl = ""
            for d in sorted(deadlines, key=lambda x: x.get("due_date", "")):
                if d.get("due_date"):
                    next_dl = str(d["due_date"])
                    break
            docs = list_matter_documents(user_id, matter_id)
            evidence_count = 0
            try:
                from backend.app.core.matter_evidence import list_evidence

                evidence_count = len(list_evidence(user_id, matter_id))
            except Exception:
                pass
            members = []
            try:
                members = list_matter_members(user_id, matter_id)
            except Exception:
                pass
            names = _username_map(org_id)
            timeline = list_timeline(user_id, matter_id, limit=12)
            panel.update(
                {
                    "matter_name": m.get("matter_name") or room.get("name"),
                    "open_tasks": len(open_tasks),
                    "total_tasks": len(tasks),
                    "documents": len(docs),
                    "evidence": evidence_count,
                    "next_deadline": next_dl,
                    "participants": [
                        {
                            "user_id": str(x.get("user_id", "")),
                            "username": names.get(
                                str(x.get("user_id", "")),
                                str(x.get("username") or x.get("user_id", "")),
                            )[:24],
                            "role": str(x.get("role", "member")),
                        }
                        for x in members[:12]
                    ],
                    "timeline": [
                        {
                            "title": t.get("title", ""),
                            "event_type": t.get("event_type", ""),
                            "created_at": t.get("created_at", t.get("event_date", "")),
                        }
                        for t in timeline[:10]
                    ],
                    "pinned_files": list_attachments_from_room(user_id, room_id, limit=5),
                }
            )
        except Exception as exc:
            logger.debug("room_context_panel matter %s: %s", matter_id, exc)
    elif room.get("room_type") == "dm":
        peer = _dm_peer_id(user_id, room_id)
        if peer:
            from backend.app.core.collab_presence import presence_for_users

            names = _username_map(org_id)
            pres = presence_for_users(org_id, [peer])
            p = pres.get(peer, {})
            panel["peer"] = {
                "user_id": peer,
                "username": names.get(peer, peer[:8]),
                "online": bool(p.get("online")),
                "last_seen": p.get("last_seen", 0),
            }
        panel["shared_files"] = list_attachments_from_room(user_id, room_id, limit=8)
    return panel


def list_attachments_from_room(user_id: str, room_id: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    _require_room_access(user_id, room_id)
    ensure_collab_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT a.attachment_id, a.filename, a.mime_type, a.created_at, a.uploader_id
        FROM collab_attachments a
        INNER JOIN collab_messages m ON m.message_id = a.message_id
        WHERE a.room_id = ? AND m.deleted_at = ''
        ORDER BY a.created_at DESC LIMIT ?
        """,
        (room_id, min(limit, 20)),
    ).fetchall()
    conn.close()
    return [
        {
            "attachment_id": r[0],
            "filename": r[1],
            "mime_type": r[2],
            "created_at": r[3],
            "uploader_id": r[4],
        }
        for r in rows
    ]


def room_activity_stats(user_id: str, room_id: str) -> Dict[str, Any]:
    room = _require_room_access(user_id, room_id)
    msgs = list_messages(user_id, room_id, limit=300)
    doc_count = 0
    task_count = 0
    for m in msgs:
        doc_count += len(m.get("attachments") or [])
        if m.get("message_type") == "task_ref":
            task_count += 1
    matter_id = room.get("matter_id") or ""
    matter_name = ""
    if matter_id:
        matter_name = str((get_matter(user_id, matter_id) or {}).get("matter_name") or "")
    return {
        "room_id": room_id,
        "message_count": len(msgs),
        "documents_shared": doc_count,
        "tasks_created": task_count,
        "matter_id": matter_id,
        "matter_name": matter_name,
        "room_type": room.get("room_type"),
        "room_name": room.get("name"),
    }
