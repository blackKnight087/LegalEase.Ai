"""CRM 2.0 schema — tables, pipeline stages, migrations."""
from __future__ import annotations

import logging
from typing import Dict, List

from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import use_postgres_legacy
from backend.app.core.saas_schema import ensure_saas_schema

logger = logging.getLogger("legalease.crm_schema")

PIPELINE_STAGES = [
    "NEW_INQUIRY",
    "AI_REVIEW",
    "CONSULTATION_SCHEDULED",
    "DOCUMENTS_REQUESTED",
    "DOCUMENTS_RECEIVED",
    "QUALIFIED",
    "ENGAGEMENT_LETTER_SENT",
    "RETAINER_PAID",
    "MATTER_CREATED",
    "CLOSED_WON",
    "CLOSED_LOST",
]

TERMINAL_STAGES = frozenset({"MATTER_CREATED", "CLOSED_WON", "CLOSED_LOST"})

STAGE_LABELS: Dict[str, str] = {
    "NEW_INQUIRY": "New inquiry",
    "AI_REVIEW": "AI review",
    "CONSULTATION_SCHEDULED": "Consultation scheduled",
    "DOCUMENTS_REQUESTED": "Documents requested",
    "DOCUMENTS_RECEIVED": "Documents received",
    "QUALIFIED": "Qualified",
    "ENGAGEMENT_LETTER_SENT": "Engagement letter sent",
    "RETAINER_PAID": "Retainer paid",
    "MATTER_CREATED": "Matter created",
    "CLOSED_WON": "Closed won",
    "CLOSED_LOST": "Closed lost",
}

_LEGACY_STAGE_MAP = {
    "NEW_INTAKE": "NEW_INQUIRY",
    "AI_REVIEWED": "AI_REVIEW",
    "PENDING_DOCS": "DOCUMENTS_REQUESTED",
    "DOCUMENTS_PENDING": "DOCUMENTS_REQUESTED",
    "ACCEPTED": "QUALIFIED",
    "CONVERTED_TO_MATTER": "MATTER_CREATED",
    "REJECTED": "CLOSED_LOST",
    "CLOSED": "CLOSED_WON",
}

STAGE_EMPTY_HINTS: Dict[str, str] = {
    "NEW_INQUIRY": "New client inquiries land here from your intake portal.",
    "AI_REVIEW": "Drag leads here after AI classification completes.",
    "CONSULTATION_SCHEDULED": "Move leads here once a consultation is booked.",
    "DOCUMENTS_REQUESTED": "Leads awaiting document uploads from the client.",
    "DOCUMENTS_RECEIVED": "All required documents received — verify before qualifying.",
    "QUALIFIED": "Qualified leads ready for engagement letter.",
    "ENGAGEMENT_LETTER_SENT": "Awaiting client signature on engagement terms.",
    "RETAINER_PAID": "Retainer received — prepare matter conversion.",
    "MATTER_CREATED": "Converted matters — open in Matters module.",
    "CLOSED_WON": "Successfully closed engagements.",
    "CLOSED_LOST": "Declined or lost opportunities.",
}

_CRM_V2_SQLITE = """
CREATE TABLE IF NOT EXISTS crm_lead_documents (
    doc_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    org_id TEXT DEFAULT '',
    filename TEXT NOT NULL,
    saved_path TEXT NOT NULL,
    mime_type TEXT DEFAULT '',
    doc_kind TEXT DEFAULT 'document',
    ocr_text TEXT DEFAULT '',
    indexed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_lead_docs ON crm_lead_documents(lead_id);

CREATE TABLE IF NOT EXISTS crm_lead_interactions (
    interaction_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    interaction_type TEXT NOT NULL DEFAULT 'note',
    title TEXT DEFAULT '',
    body TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_interactions ON crm_lead_interactions(lead_id);

CREATE TABLE IF NOT EXISTS crm_stage_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    from_stage TEXT DEFAULT '',
    to_stage TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_stage_hist ON crm_stage_history(lead_id);

CREATE TABLE IF NOT EXISTS crm_lead_entities (
    entity_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    label TEXT NOT NULL,
    role_label TEXT DEFAULT '',
    confidence REAL DEFAULT 0.8,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_lead_ent ON crm_lead_entities(lead_id);

CREATE TABLE IF NOT EXISTS crm_lead_tasks (
    task_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    due_date TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crm_lead_deadlines (
    deadline_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    deadline_type TEXT DEFAULT 'general',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crm_follow_up_templates (
    template_id TEXT PRIMARY KEY,
    org_id TEXT DEFAULT '',
    user_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    subject TEXT DEFAULT '',
    body_template TEXT NOT NULL,
    template_type TEXT DEFAULT 'email',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crm_audit_log (
    audit_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_audit_lead ON crm_audit_log(lead_id);
"""

_CRM_V2_PG = [
    """
    CREATE TABLE IF NOT EXISTS crm_lead_documents (
        doc_id TEXT PRIMARY KEY,
        lead_id TEXT NOT NULL,
        org_id TEXT DEFAULT '',
        filename TEXT NOT NULL,
        saved_path TEXT NOT NULL,
        mime_type TEXT DEFAULT '',
        doc_kind TEXT DEFAULT 'document',
        ocr_text TEXT DEFAULT '',
        indexed INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_crm_lead_docs ON crm_lead_documents(lead_id)",
    """
    CREATE TABLE IF NOT EXISTS crm_lead_interactions (
        interaction_id TEXT PRIMARY KEY,
        lead_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        interaction_type TEXT NOT NULL DEFAULT 'note',
        title TEXT DEFAULT '',
        body TEXT DEFAULT '',
        metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_stage_history (
        id SERIAL PRIMARY KEY,
        lead_id TEXT NOT NULL,
        from_stage TEXT DEFAULT '',
        to_stage TEXT NOT NULL,
        user_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_lead_entities (
        entity_id TEXT PRIMARY KEY,
        lead_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        label TEXT NOT NULL,
        role_label TEXT DEFAULT '',
        confidence REAL DEFAULT 0.8,
        metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_lead_tasks (
        task_id TEXT PRIMARY KEY,
        lead_id TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        due_date TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_lead_deadlines (
        deadline_id TEXT PRIMARY KEY,
        lead_id TEXT NOT NULL,
        title TEXT NOT NULL,
        due_date TEXT NOT NULL,
        deadline_type TEXT DEFAULT 'general',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_follow_up_templates (
        template_id TEXT PRIMARY KEY,
        org_id TEXT DEFAULT '',
        user_id TEXT DEFAULT '',
        name TEXT NOT NULL,
        subject TEXT DEFAULT '',
        body_template TEXT NOT NULL,
        template_type TEXT DEFAULT 'email',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_audit_log (
        audit_id TEXT PRIMARY KEY,
        lead_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        detail TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
]

_crm_v2_ready = False


def normalize_stage(stage: str) -> str:
    s = (stage or "").strip().upper()
    return _LEGACY_STAGE_MAP.get(s, s)


def ensure_crm_v2_schema() -> None:
    global _crm_v2_ready
    ensure_saas_schema()
    if _crm_v2_ready:
        return
    from backend.app.core.schema_migrations import apply_migrations

    apply_migrations(tables=["crm_leads"])
    conn = connect_data_db()
    try:
        if use_postgres_legacy():
            for stmt in _CRM_V2_PG:
                conn.execute(stmt)
        else:
            conn.executescript(_CRM_V2_SQLITE)
        for old, new in _LEGACY_STAGE_MAP.items():
            conn.execute(
                "UPDATE crm_leads SET pipeline_stage = ? WHERE pipeline_stage = ?",
                (new, old),
            )
        conn.commit()
    except Exception as exc:
        logger.warning("crm_v2 schema partial: %s", exc)
    finally:
        conn.close()
    try:
        from backend.app.core.crm_follow_up import seed_follow_up_templates

        seed_follow_up_templates()
    except Exception as exc:
        logger.warning("crm follow-up seed: %s", exc)
    _crm_v2_ready = True


def lead_select_columns() -> str:
    return """
        lead_id, user_id, org_id, prospect_name, contact_email, contact_phone,
        address, city, state, preferred_contact, preferred_language, referral_source,
        raw_intake_query, calculated_intent, extracted_params_json, pipeline_stage,
        assigned_attorney_id, assigned_lawyer_id, follow_up_draft,
        lead_score, lead_score_band, case_strength, rejection_reason,
        analysis_json, analysis_version, last_analyzed_at,
        matter_id, archived_at, created_at, updated_at
    """
