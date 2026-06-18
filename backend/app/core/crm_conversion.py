"""Lead → matter conversion with full workspace seeding."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.crm_audit import log_crm_audit
from backend.app.core.crm_schema import normalize_stage
from backend.app.core.crm_service import CASE_TYPE_LABELS
from backend.app.core.crm_v2_service import (
    get_lead_full,
    list_lead_entities,
    transition_stage,
    update_lead_extended,
)

# transition_stage imported for reject/archive


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _due_in_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def preview_conversion(user_id: str, lead_id: str) -> Dict[str, Any]:
    lead = get_lead_full(user_id, lead_id)
    if not lead:
        return {"error": "Lead not found"}
    analysis = lead.get("analysis") or {}
    preview = analysis.get("matter_preview") or {}
    intent = lead.get("calculated_intent") or "GENERAL"
    practice = CASE_TYPE_LABELS.get(intent, "General")
    entities = list_lead_entities(lead_id)
    return {
        "lead_id": lead_id,
        "matter_preview": {
            "suggested_name": preview.get("suggested_name")
            or f"{lead.get('prospect_name')} — {practice}",
            "practice_area": practice,
            "client_name": lead.get("prospect_name"),
            "venue": lead.get("city") or (lead.get("extracted_params") or {}).get("venue", ""),
            "tasks": preview.get("tasks") or [],
            "deadlines": preview.get("deadlines") or [],
            "timeline_events": preview.get("timeline_events") or [],
        },
        "entities": entities,
        "analysis_summary": analysis.get("executive_summary") or "",
        "lead_score": lead.get("lead_score"),
    }


def convert_lead_to_matter_full(user_id: str, lead_id: str) -> Dict[str, Any]:
    lead = get_lead_full(user_id, lead_id)
    if not lead:
        return {"error": "Lead not found"}
    if normalize_stage(lead.get("pipeline_stage")) == "MATTER_CREATED" and lead.get("matter_id"):
        return {"error": "Lead already converted", "matter_id": lead.get("matter_id")}

    preview = preview_conversion(user_id, lead_id)
    mp = preview.get("matter_preview") or {}
    from backend.app.core.matter_repo import add_matter_note, create_matter

    matter = create_matter(
        user_id,
        matter_name=mp.get("suggested_name") or "New matter",
        practice_area=mp.get("practice_area") or "General",
        client_name=mp.get("client_name") or "",
        venue=str(mp.get("venue") or ""),
        status_tier="ACTIVE",
        description=(lead.get("raw_intake_query") or "")[:2000],
    )
    if not matter:
        return {"error": "Failed to create matter"}
    mid = matter["matter_id"]

    try:
        from backend.app.core.matter_workflow import add_deadline, add_task, add_timeline_event

        for t in mp.get("tasks") or []:
            add_task(
                user_id,
                mid,
                title=str(t.get("title") or "Task"),
                due_date=_due_in_days(int(t.get("due_days") or 7)),
            )
        for d in mp.get("deadlines") or []:
            add_deadline(
                user_id,
                mid,
                title=str(d.get("title") or "Deadline"),
                due_date=_due_in_days(int(d.get("due_days") or 14)),
            )
        for ev in mp.get("timeline_events") or []:
            add_timeline_event(
                user_id,
                mid,
                title=str(ev.get("title") or "Event"),
                event_type=str(ev.get("event_type") or "intake"),
            )
        add_timeline_event(
            user_id,
            mid,
            title="Matter opened from Intake CRM",
            description=(lead.get("raw_intake_query") or "")[:500],
            event_type="intake",
        )
    except Exception:
        pass

    try:
        from backend.app.core.matter_entities import upsert_entity

        for ent in list_lead_entities(lead_id):
            upsert_entity(
                mid,
                entity_type=ent.get("entity_type") or "person",
                label=ent.get("label") or "",
                confidence=float(ent.get("confidence") or 0.8),
                metadata={"role": ent.get("role_label"), "from_lead": lead_id},
            )
    except Exception:
        pass

    add_matter_note(
        user_id,
        mid,
        f"Converted from intake lead {lead_id}.\n\n{lead.get('raw_intake_query', '')}",
    )

    update_lead_extended(
        user_id,
        lead_id,
        pipeline_stage="MATTER_CREATED",
        matter_id=mid,
    )
    log_crm_audit(lead_id, user_id, "converted", mid)

    return {
        "converted": True,
        "lead_id": lead_id,
        "matter": matter,
        "matter_id": mid,
        "tasks_created": len(mp.get("tasks") or []),
        "deadlines_created": len(mp.get("deadlines") or []),
        "entities_copied": len(list_lead_entities(lead_id)),
    }


def reject_lead(user_id: str, lead_id: str, reason: str) -> Optional[Dict[str, Any]]:
    lead = transition_stage(user_id, lead_id, "REJECTED", note=reason)
    if not lead:
        return None
    update_lead_extended(user_id, lead_id, rejection_reason=(reason or "")[:1000])
    log_crm_audit(lead_id, user_id, "rejected", reason)
    return get_lead_full(user_id, lead_id)


def archive_lead(user_id: str, lead_id: str) -> Optional[Dict[str, Any]]:
    lead = transition_stage(user_id, lead_id, "CLOSED", note="Archived")
    if not lead:
        return None
    update_lead_extended(user_id, lead_id, archived_at=_utc())
    log_crm_audit(lead_id, user_id, "archived", "")
    return get_lead_full(user_id, lead_id)
