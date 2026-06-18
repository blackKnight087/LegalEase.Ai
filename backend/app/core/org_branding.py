"""Organization white-label branding (Enterprise tier)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.org_service import get_org, get_primary_org_id, is_org_owner
from backend.app.core.p0_saas_schema import ensure_p0_saas_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_org_branding_columns() -> None:
    ensure_p0_saas_schema()


def get_org_branding(org_id: str) -> Dict[str, Any]:
    ensure_org_branding_columns()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT org_id, name, custom_domain, logo_url, primary_color, support_email
        FROM organizations WHERE org_id = ?
        """,
        (str(org_id),),
    ).fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "org_id": row[0],
        "name": row[1],
        "custom_domain": row[2] or "",
        "logo_url": row[3] or "",
        "primary_color": row[4] or "#1e3a5f",
        "support_email": row[5] or "",
    }


def update_org_branding(
    user_id: str,
    org_id: str,
    *,
    custom_domain: Optional[str] = None,
    logo_url: Optional[str] = None,
    primary_color: Optional[str] = None,
    support_email: Optional[str] = None,
) -> Dict[str, Any]:
    if not is_org_owner(user_id, org_id):
        raise PermissionError("Owner only")
    ensure_org_branding_columns()
    fields: Dict[str, str] = {}
    if custom_domain is not None:
        fields["custom_domain"] = custom_domain.strip()[:200]
    if logo_url is not None:
        fields["logo_url"] = logo_url.strip()[:500]
    if primary_color is not None:
        fields["primary_color"] = primary_color.strip()[:32]
    if support_email is not None:
        fields["support_email"] = support_email.strip()[:200]
    if not fields:
        return get_org_branding(org_id)
    fields["updated_at"] = _utc()
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn = connect_data_db()
    conn.execute(
        f"UPDATE organizations SET {sets} WHERE org_id = ?",
        (*fields.values(), str(org_id)),
    )
    conn.commit()
    conn.close()
    return get_org_branding(org_id)


def branding_for_user(user_id: str) -> Dict[str, Any]:
    org_id = get_primary_org_id(user_id)
    if not org_id:
        return {}
    org = get_org(org_id) or {}
    brand = get_org_branding(org_id)
    brand["plan"] = org.get("plan", "Free")
    return brand
