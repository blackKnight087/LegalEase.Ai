"""CRM follow-up email templates."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.core.crm_schema import ensure_crm_v2_schema
from backend.app.core.database import connect_data_db
from backend.app.core.org_service import get_primary_org_id

_DEFAULT_TEMPLATES = [
    {
        "name": "Document request",
        "subject": "Documents needed for your matter",
        "body_template": (
            "Dear {prospect_name},\n\n"
            "Thank you for contacting our firm. To proceed with your {case_type} inquiry, "
            "please share the following documents at your earliest convenience:\n"
            "{missing_docs}\n\n"
            "Regards,\n{firm_name}"
        ),
        "template_type": "document_request",
    },
    {
        "name": "Consultation reminder",
        "subject": "Consultation reminder",
        "body_template": (
            "Dear {prospect_name},\n\n"
            "This is a reminder regarding your upcoming consultation with our firm "
            "concerning your {case_type} matter.\n\n"
            "Please bring any relevant documents discussed during intake.\n\n"
            "Regards,\n{firm_name}"
        ),
        "template_type": "consultation",
    },
    {
        "name": "Initial acknowledgment",
        "subject": "We received your inquiry",
        "body_template": (
            "Dear {prospect_name},\n\n"
            "We have received your legal inquiry and our team is reviewing the details. "
            "We will contact you shortly with next steps.\n\n"
            "Regards,\n{firm_name}"
        ),
        "template_type": "email",
    },
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_follow_up_templates() -> None:
    ensure_crm_v2_schema()
    conn = connect_data_db()
    try:
        row = conn.execute("SELECT COUNT(*) FROM crm_follow_up_templates").fetchone()
        if row and int(row[0] or 0) > 0:
            return
        now = _utc()
        for tpl in _DEFAULT_TEMPLATES:
            conn.execute(
                """
                INSERT INTO crm_follow_up_templates
                (template_id, org_id, user_id, name, subject, body_template, template_type, created_at)
                VALUES (?, '', '', ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    tpl["name"],
                    tpl["subject"],
                    tpl["body_template"],
                    tpl["template_type"],
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def list_follow_up_templates(user_id: str) -> List[Dict[str, Any]]:
    ensure_crm_v2_schema()
    seed_follow_up_templates()
    org_id = get_primary_org_id(str(user_id)) or ""
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT template_id, name, subject, body_template, template_type, org_id
        FROM crm_follow_up_templates
        WHERE org_id = '' OR org_id = ?
        ORDER BY name
        """,
        (org_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "template_id": r[0],
            "name": r[1],
            "subject": r[2],
            "body_template": r[3],
            "template_type": r[4],
            "org_id": r[5],
        }
        for r in rows
    ]


def render_template(body_template: str, ctx: Dict[str, str]) -> str:
    out = body_template
    for key, val in ctx.items():
        out = out.replace("{" + key + "}", val or "")
    return out
