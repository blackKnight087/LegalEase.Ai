"""Password reset tokens and email flow."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.email_service import (
    PUBLIC_APP_URL,
    resolve_delivery_email,
    send_password_reset_email,
)
from backend.app.core.p2_saas_schema import ensure_p2_saas_schema

logger = logging.getLogger("legalease.password_reset")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _find_user(identifier: str) -> Optional[Tuple[str, str, str]]:
    """Return (user_id, username, email) by username or email column."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    ensure_p2_saas_schema()
    conn = connect_data_db()
    try:
        cur = conn.execute(
            """
            SELECT id, username, COALESCE(email, '') FROM users
            WHERE LOWER(username) = LOWER(?) OR LOWER(COALESCE(email, '')) = LOWER(?)
            LIMIT 1
            """,
            (ident, ident),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return str(row[0]), str(row[1]), str(row[2] or "")


def request_password_reset(username: str) -> bool:
    """Create reset token and send email. Returns True if user exists (always True for privacy)."""
    found = _find_user(username)
    if not found:
        return True
    user_id, db_username, db_email = found
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    now = _utc()
    exp = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO password_reset_tokens (token_id, user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), str(user_id), token_hash, exp, now),
    )
    conn.commit()
    conn.close()
    reset_url = f"{PUBLIC_APP_URL}/reset-password/{raw}"
    delivery = resolve_delivery_email(db_username, db_email)
    if not delivery:
        logger.warning(
            "Password reset for user %r has no email on file. "
            "Register with a Gmail address or set users.email. Dev link: %s",
            db_username,
            reset_url,
        )
        return True
    ok = send_password_reset_email(delivery, reset_url)
    if not ok:
        logger.error(
            "Password reset email failed for %s — check SMTP/Gmail settings. Dev link: %s",
            delivery,
            reset_url,
        )
    return True


def reset_password_with_token(token: str, new_password: str) -> None:
    from legalease_auth import hash_password, run_query

    if len(new_password or "") < 6:
        raise ValueError("Password must be at least 6 characters")
    ensure_p2_saas_schema()
    th = _hash_token((token or "").strip())
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT token_id, user_id, expires_at, used_at FROM password_reset_tokens
        WHERE token_hash = ? LIMIT 1
        """,
        (th,),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("Invalid or expired reset link")
    token_id, user_id, expires_at, used_at = row
    if used_at:
        conn.close()
        raise ValueError("Reset link already used")
    try:
        exp_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp_dt:
            conn.close()
            raise ValueError("Reset link expired")
    except ValueError:
        raise
    except Exception:
        pass
    pw_hash = hash_password(new_password)
    run_query(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (pw_hash, str(user_id)),
    )
    now = _utc()
    conn.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE token_id = ?",
        (now, token_id),
    )
    conn.commit()
    conn.close()
