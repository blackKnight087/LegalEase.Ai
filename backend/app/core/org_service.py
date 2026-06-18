"""Organization tenancy — firm-level isolation for matters and members."""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.p0_saas_schema import ensure_p0_saas_schema

PUBLIC_APP_URL = (
    os.getenv("PUBLIC_APP_URL") or os.getenv("NEXT_PUBLIC_APP_URL") or "http://localhost:3000"
).rstrip("/")

PLAN_SEATS = {
    "Free": int(os.getenv("ORG_SEATS_FREE", "1")),
    "Pro": int(os.getenv("ORG_SEATS_PRO", "3")),
    "Legal Pro": int(os.getenv("ORG_SEATS_LEGAL_PRO", "10")),
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_org_for_user(user_id: str, username: str, plan: str = "Free") -> str:
    """Create default organization; user becomes owner. Idempotent if already member."""
    ensure_p0_saas_schema()
    uid = str(user_id)
    existing = get_primary_org_id(uid)
    if existing:
        return existing
    org_id = str(uuid.uuid4())
    name = f"{username.strip()}'s Practice" if username else "My Practice"
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO organizations (org_id, name, plan, seat_limit, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (org_id, name, plan, PLAN_SEATS.get(plan, 1), now, now),
    )
    conn.execute(
        """
        INSERT INTO org_members (org_id, user_id, role, created_at)
        VALUES (?, ?, 'owner', ?)
        """,
        (org_id, uid, now),
    )
    conn.commit()
    conn.close()
    return org_id


def get_primary_org_id(user_id: str) -> str:
    ensure_p0_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT org_id FROM org_members
        WHERE user_id = ? ORDER BY CASE role WHEN 'owner' THEN 0 ELSE 1 END, id ASC
        LIMIT 1
        """,
        (str(user_id),),
    ).fetchone()
    conn.close()
    return str(row[0]) if row else ""


def list_user_org_ids(user_id: str) -> List[str]:
    ensure_p0_saas_schema()
    conn = connect_data_db()
    rows = conn.execute(
        "SELECT org_id FROM org_members WHERE user_id = ?",
        (str(user_id),),
    ).fetchall()
    conn.close()
    return [str(r[0]) for r in rows]


def user_in_org(user_id: str, org_id: str) -> bool:
    if not org_id:
        return False
    ensure_p0_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ? LIMIT 1",
        (str(org_id), str(user_id)),
    ).fetchone()
    conn.close()
    return bool(row)


ORG_INVITE_ROLES = frozenset({"member", "lawyer", "viewer"})


def get_org_member_role(user_id: str, org_id: str) -> str:
    """Return org role (owner, member, lawyer, viewer) or empty string."""
    if not org_id:
        return ""
    ensure_p0_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT role FROM org_members WHERE org_id = ? AND user_id = ? LIMIT 1",
        (str(org_id), str(user_id)),
    ).fetchone()
    conn.close()
    return str(row[0]).lower() if row and row[0] else ""


def is_org_owner(user_id: str, org_id: str) -> bool:
    return get_org_member_role(user_id, org_id) == "owner"


def get_org(org_id: str) -> Optional[Dict[str, Any]]:
    ensure_p0_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT org_id, name, plan, seat_limit, created_at FROM organizations WHERE org_id = ?",
        (str(org_id),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "org_id": row[0],
        "name": row[1],
        "plan": row[2],
        "seat_limit": int(row[3]),
        "created_at": row[4],
    }


def list_org_members(org_id: str, requester_id: str) -> List[Dict[str, Any]]:
    if not user_in_org(requester_id, org_id):
        return []
    ensure_p0_saas_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT om.user_id, om.role, om.created_at, u.username
        FROM org_members om
        LEFT JOIN users u ON u.id = om.user_id
        WHERE om.org_id = ?
        ORDER BY om.created_at ASC
        """,
        (str(org_id),),
    ).fetchall()
    conn.close()
    return [
        {
            "user_id": r[0],
            "role": r[1],
            "created_at": r[2],
            "username": r[3] or "",
        }
        for r in rows
    ]


def list_pending_invites(org_id: str, requester_id: str) -> List[Dict[str, Any]]:
    if not user_in_org(requester_id, org_id):
        return []
    ensure_p0_saas_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT invite_id, email, role, status, created_at, expires_at, token
        FROM org_invites
        WHERE org_id = ? AND status = 'pending'
        ORDER BY created_at DESC
        """,
        (str(org_id),),
    ).fetchall()
    conn.close()
    owner = is_org_owner(requester_id, org_id)
    out: List[Dict[str, Any]] = []
    for r in rows:
        item: Dict[str, Any] = {
            "invite_id": r[0],
            "email": r[1],
            "role": r[2],
            "status": r[3],
            "created_at": r[4],
            "expires_at": r[5],
        }
        if owner:
            item["invite_path"] = f"/invite/{r[6]}"
            item["invite_url"] = f"{PUBLIC_APP_URL}/invite/{r[6]}"
        out.append(item)
    return out


def count_org_members(org_id: str) -> int:
    ensure_p0_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT COUNT(*) FROM org_members WHERE org_id = ?",
        (str(org_id),),
    ).fetchone()
    conn.close()
    return int(row[0] if row else 0)


def create_invite(
    org_id: str,
    inviter_id: str,
    email: str,
    role: str = "member",
) -> Dict[str, Any]:
    if not is_org_owner(inviter_id, org_id):
        raise PermissionError("Only organization owners can send invites")
    role_norm = (role or "member").strip().lower()
    if role_norm not in ORG_INVITE_ROLES:
        raise ValueError(f"Invalid invite role. Allowed: {', '.join(sorted(ORG_INVITE_ROLES))}")
    role = role_norm
    org = get_org(org_id) or {}
    if count_org_members(org_id) >= int(org.get("seat_limit") or 1):
        raise ValueError("Seat limit reached for current plan")
    invite_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    now = _utc()
    exp = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    ensure_p0_saas_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO org_invites (invite_id, org_id, email, role, token, status, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (invite_id, str(org_id), email.strip().lower(), role, token, now, exp),
    )
    conn.commit()
    conn.close()
    invite_path = f"/invite/{token}"
    invite_url = f"{PUBLIC_APP_URL}{invite_path}"
    try:
        from backend.app.core.email_service import send_org_invite_email

        org_name = str((get_org(org_id) or {}).get("name") or "your team")
        send_org_invite_email(email.strip().lower(), org_name, invite_url)
    except Exception:
        pass
    return {
        "invite_id": invite_id,
        "token": token,
        "expires_at": exp,
        "invite_path": invite_path,
        "invite_url": invite_url,
    }


def revoke_invite(org_id: str, requester_id: str, invite_id: str) -> bool:
    if not is_org_owner(requester_id, org_id):
        raise PermissionError("Only organization owners can revoke invites")
    ensure_p0_saas_schema()
    conn = connect_data_db()
    cur = conn.execute(
        """
        UPDATE org_invites SET status = 'revoked'
        WHERE invite_id = ? AND org_id = ? AND status = 'pending'
        """,
        (str(invite_id), str(org_id)),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_invite_by_token(token: str) -> Optional[Dict[str, Any]]:
    ensure_p0_saas_schema()
    tok = (token or "").strip()
    if not tok:
        return None
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT i.invite_id, i.org_id, i.email, i.role, i.status, i.expires_at, o.name
        FROM org_invites i
        JOIN organizations o ON o.org_id = i.org_id
        WHERE i.token = ?
        LIMIT 1
        """,
        (tok,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "invite_id": row[0],
        "org_id": row[1],
        "email": row[2],
        "role": row[3],
        "status": row[4],
        "expires_at": row[5],
        "org_name": row[6],
    }


def _email_matches_user(invite_email: str, username: str) -> bool:
    ie = (invite_email or "").strip().lower()
    un = (username or "").strip().lower()
    if not ie or not un:
        return False
    if ie == un:
        return True
    local = ie.split("@")[0]
    return local == un


def accept_invite(token: str, user_id: str, username: str) -> Dict[str, Any]:
    inv = get_invite_by_token(token)
    if not inv:
        raise ValueError("Invite not found")
    if inv.get("status") != "pending":
        raise ValueError(f"Invite already {inv.get('status')}")
    exp = inv.get("expires_at") or ""
    if exp:
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_dt:
                raise ValueError("Invite expired")
        except ValueError:
            raise
        except Exception:
            pass
    if not _email_matches_user(str(inv.get("email") or ""), username):
        raise PermissionError(
            "This invite was sent to a different email. Log in with the invited account."
        )
    org_id = str(inv["org_id"])
    if user_in_org(str(user_id), org_id):
        _mark_invite_accepted(str(inv["invite_id"]), str(user_id))
        return {"ok": True, "org_id": org_id, "already_member": True}
    org = get_org(org_id) or {}
    if count_org_members(org_id) >= int(org.get("seat_limit") or 1):
        raise ValueError("Seat limit reached for this organization")
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO org_members (org_id, user_id, role, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(org_id, user_id) DO NOTHING
        """,
        (org_id, str(user_id), str(inv.get("role") or "member"), now),
    )
    conn.commit()
    conn.close()
    _mark_invite_accepted(str(inv["invite_id"]), str(user_id))
    return {"ok": True, "org_id": org_id, "org_name": inv.get("org_name"), "role": inv.get("role")}


def _mark_invite_accepted(invite_id: str, user_id: str) -> None:
    conn = connect_data_db()
    conn.execute(
        """
        UPDATE org_invites SET status = 'accepted'
        WHERE invite_id = ?
        """,
        (invite_id,),
    )
    conn.commit()
    conn.close()


def sync_org_plan_from_membership(org_id: str, membership: str) -> None:
    """Keep org plan aligned with owner's membership tier."""
    ensure_p0_saas_schema()
    seats = PLAN_SEATS.get(membership, 1)
    conn = connect_data_db()
    conn.execute(
        "UPDATE organizations SET plan = ?, seat_limit = ?, updated_at = ? WHERE org_id = ?",
        (membership, seats, _utc(), str(org_id)),
    )
    conn.commit()
    conn.close()
