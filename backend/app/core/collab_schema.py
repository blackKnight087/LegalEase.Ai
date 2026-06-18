"""Collaboration Hub — rooms, messages, attachments, notifications."""
from __future__ import annotations

import logging

from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import use_postgres_legacy
from backend.app.core.saas_schema import ensure_saas_schema

logger = logging.getLogger("legalease.collab_schema")

_COLLAB_SQLITE = """
CREATE TABLE IF NOT EXISTS collab_rooms (
    room_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT '',
    room_type TEXT NOT NULL,
    matter_id TEXT DEFAULT '',
    dm_key TEXT DEFAULT '',
    slug TEXT DEFAULT '',
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_private INTEGER DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collab_rooms_org ON collab_rooms(org_id);
CREATE INDEX IF NOT EXISTS idx_collab_rooms_matter ON collab_rooms(matter_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_collab_rooms_dm ON collab_rooms(org_id, dm_key) WHERE dm_key != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_collab_rooms_slug ON collab_rooms(org_id, slug) WHERE slug != '';

CREATE TABLE IF NOT EXISTS collab_room_members (
    room_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    member_role TEXT DEFAULT 'member',
    joined_at TEXT NOT NULL,
    last_read_at TEXT DEFAULT '',
    muted INTEGER DEFAULT 0,
    PRIMARY KEY (room_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_collab_members_user ON collab_room_members(user_id);

CREATE TABLE IF NOT EXISTS collab_messages (
    message_id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    body TEXT DEFAULT '',
    message_type TEXT DEFAULT 'text',
    parent_id TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    pinned INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    edited_at TEXT DEFAULT '',
    deleted_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_collab_msg_room ON collab_messages(room_id, created_at);

CREATE TABLE IF NOT EXISTS collab_attachments (
    attachment_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    room_id TEXT NOT NULL,
    uploader_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    saved_path TEXT NOT NULL,
    mime_type TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collab_att_msg ON collab_attachments(message_id);

CREATE TABLE IF NOT EXISTS collab_message_reactions (
    message_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    emoji TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (message_id, user_id, emoji)
);

CREATE TABLE IF NOT EXISTS collab_mentions (
    mention_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    room_id TEXT NOT NULL,
    mentioned_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collab_mentions_user ON collab_mentions(mentioned_user_id);

CREATE TABLE IF NOT EXISTS collab_notifications (
    notification_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    org_id TEXT DEFAULT '',
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    link_path TEXT DEFAULT '',
    room_id TEXT DEFAULT '',
    message_id TEXT DEFAULT '',
    read_at TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collab_notif_user ON collab_notifications(user_id, read_at);

CREATE TABLE IF NOT EXISTS collab_audit_logs (
    log_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT DEFAULT '',
    resource_id TEXT DEFAULT '',
    detail_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collab_audit_org ON collab_audit_logs(org_id, created_at);

CREATE TABLE IF NOT EXISTS collab_chat_requests (
    request_id TEXT PRIMARY KEY,
    from_user_id TEXT NOT NULL,
    to_user_id TEXT NOT NULL,
    intro_message TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    responded_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_collab_chat_req_to ON collab_chat_requests(to_user_id, status);
CREATE INDEX IF NOT EXISTS idx_collab_chat_req_from ON collab_chat_requests(from_user_id, status);

CREATE TABLE IF NOT EXISTS collab_connections (
    connection_id TEXT PRIMARY KEY,
    user_a TEXT NOT NULL,
    user_b TEXT NOT NULL,
    pair_key TEXT NOT NULL UNIQUE,
    room_id TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collab_conn_users ON collab_connections(user_a, user_b);
"""

_COLLAB_PG = [s.strip() + ";" for s in _COLLAB_SQLITE.split(";") if s.strip()]

_collab_ready = False


def ensure_collab_schema() -> None:
    global _collab_ready
    ensure_saas_schema()
    if _collab_ready:
        return
    conn = connect_data_db()
    try:
        if use_postgres_legacy():
            for stmt in _COLLAB_PG:
                try:
                    conn.execute(stmt)
                except Exception as exc:
                    logger.debug("collab pg stmt: %s", exc)
        else:
            conn.executescript(_COLLAB_SQLITE)
        conn.commit()
    except Exception as exc:
        logger.warning("collab schema partial: %s", exc)
    finally:
        conn.close()
    _collab_ready = True
