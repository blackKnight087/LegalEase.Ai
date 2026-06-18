"""Intake Command Center — firm-wide CRM dashboard payload."""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.crm_analytics import crm_dashboard, crm_kanban
from backend.app.core.crm_kanban_enrich import STAGE_VALUE_INR
from backend.app.core.crm_schema import (
    PIPELINE_STAGES,
    STAGE_LABELS,
    TERMINAL_STAGES,
    ensure_crm_v2_schema,
    normalize_stage,
)
from backend.app.core.crm_service import _crm_scope
from backend.app.core.crm_v2_service import list_leads_full
from backend.app.core.database import connect_data_db

ACTION_LABELS: Dict[str, str] = {
    "created": "New lead submitted",
    "lead_created": "New lead submitted",
    "lead_updated": "Lead details updated",
    "stage_change": "Pipeline stage updated",
    "status_change": "Status updated",
    "analysis_run": "AI intake analysis completed",
    "analyzed": "AI intake analysis completed",
    "converted": "Lead converted to matter",
    "rejected": "Lead rejected",
    "follow_up_sent": "Follow-up email sent",
    "document_upload": "Client uploaded documents",
    "document_uploaded": "Client uploaded documents",
    "archived": "Lead archived",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_waiting(created_at: str) -> int:
    dt = _parse_ts(created_at)
    if not dt:
        return 0
    return max(0, (_utc_now() - dt).days)


def _load_leads(user_id: str) -> List[Dict[str, Any]]:
    return list_leads_full(user_id, limit=500)


def _firm_activity(user_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_crm_v2_schema()
    scope_sql, scope_params = _crm_scope(user_id)
    lead_filter = scope_sql.replace("org_id", "l.org_id").replace("user_id", "l.user_id")
    conn = connect_data_db()
    rows = conn.execute(
        f"""
        SELECT a.action, a.detail, a.created_at, a.lead_id, l.prospect_name
        FROM crm_audit_log a
        INNER JOIN crm_leads l ON l.lead_id = a.lead_id
        WHERE {lead_filter}
        ORDER BY a.created_at DESC
        LIMIT ?
        """,
        (*scope_params, limit),
    ).fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    if not rows:
        return _firm_activity_from_leads(user_id, limit=limit)
    for action, detail, created_at, lead_id, name in rows:
        key = (action or "").replace("crm_", "")
        out.append(
            {
                "action": action,
                "label": ACTION_LABELS.get(key, key.replace("_", " ").title() or "Activity"),
                "detail": (detail or "")[:200],
                "created_at": created_at,
                "lead_id": lead_id,
                "prospect_name": name or "Lead",
            }
        )
    return out


def _firm_activity_from_leads(user_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    """Fallback when audit log is empty — synthesize from recent leads."""
    leads = sorted(
        _load_leads(user_id),
        key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
        reverse=True,
    )[:limit]
    out: List[Dict[str, Any]] = []
    for lead in leads:
        stage = normalize_stage(str(lead.get("pipeline_stage") or ""))
        label = "New lead submitted"
        if stage == "MATTER_CREATED":
            label = "Lead converted to matter"
        elif stage == "CONSULTATION_SCHEDULED":
            label = "Consultation scheduled"
        elif stage == "AI_REVIEW":
            label = "AI intake analysis completed"
        out.append(
            {
                "action": "synthetic",
                "label": label,
                "detail": str(lead.get("case_type") or lead.get("calculated_intent") or "")[:120],
                "created_at": lead.get("updated_at") or lead.get("created_at"),
                "lead_id": lead.get("lead_id"),
                "prospect_name": lead.get("prospect_name") or "Lead",
            }
        )
    return out


def _urgent_leads(leads: List[Dict[str, Any]], *, limit: int = 8) -> List[Dict[str, Any]]:
    urgent: List[Tuple[int, Dict[str, Any]]] = []
    for lead in leads:
        stage = normalize_stage(str(lead.get("pipeline_stage") or ""))
        if stage in TERMINAL_STAGES:
            continue
        score = int(lead.get("lead_score") or 0)
        urgency = str(lead.get("urgency") or "").lower()
        days = _days_waiting(str(lead.get("created_at") or ""))
        priority = score
        if urgency in {"high", "urgent", "critical"}:
            priority += 25
        if stage in {"NEW_INQUIRY", "AI_REVIEW"} and days >= 2:
            priority += 15
        if score >= 70 or priority >= 70:
            urgent.append((priority, lead))
    urgent.sort(key=lambda x: -x[0])
    if not urgent:
        for lead in leads:
            stage = normalize_stage(str(lead.get("pipeline_stage") or ""))
            if stage in TERMINAL_STAGES:
                continue
            sc = int(lead.get("lead_score") or 0)
            urgent.append((sc, lead))
        urgent.sort(key=lambda x: -x[0])
    result: List[Dict[str, Any]] = []
    for _, lead in urgent[:limit]:
        analysis = lead.get("analysis") or {}
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except json.JSONDecodeError:
                analysis = {}
        classification = (analysis.get("classification") or {}) if isinstance(analysis, dict) else {}
        result.append(
            {
                "lead_id": lead.get("lead_id"),
                "prospect_name": lead.get("prospect_name") or "Unknown",
                "case_type": lead.get("case_type")
                or classification.get("primary")
                or lead.get("calculated_intent")
                or "General",
                "urgency": lead.get("urgency") or "medium",
                "risk_score": int(lead.get("risk_score") or lead.get("lead_score") or 0),
                "days_waiting": _days_waiting(str(lead.get("created_at") or "")),
                "pipeline_stage": lead.get("pipeline_stage"),
                "contact_email": lead.get("contact_email") or "",
                "contact_phone": lead.get("contact_phone") or "",
            }
        )
    return result


def _follow_ups(leads: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Heuristic follow-ups from stage + age (until dedicated follow_up_at field exists)."""
    today: List[Dict[str, Any]] = []
    overdue: List[Dict[str, Any]] = []
    upcoming: List[Dict[str, Any]] = []
    for lead in leads:
        stage = normalize_stage(str(lead.get("pipeline_stage") or ""))
        if stage in TERMINAL_STAGES:
            continue
        days = _days_waiting(str(lead.get("created_at") or ""))
        entry = {
            "lead_id": lead.get("lead_id"),
            "prospect_name": lead.get("prospect_name") or "Lead",
            "pipeline_stage": stage,
            "due_label": "Follow up",
            "days_waiting": days,
        }
        if stage == "CONSULTATION_SCHEDULED":
            today.append({**entry, "due_label": "Consultation prep"})
        elif days >= 5 and stage in {"NEW_INQUIRY", "AI_REVIEW"}:
            overdue.append({**entry, "due_label": "Overdue response"})
        elif days >= 2:
            today.append({**entry, "due_label": "Check in today"})
        elif days == 1:
            upcoming.append({**entry, "due_label": "Tomorrow"})
    return {
        "due_today": today[:8],
        "overdue": overdue[:8],
        "upcoming": upcoming[:6],
        "overdue_count": len(overdue),
    }


def _pipeline_value(leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_stage: Dict[str, Dict[str, Any]] = {}
    total = 0
    for stage in PIPELINE_STAGES:
        if stage in TERMINAL_STAGES:
            continue
        by_stage[stage] = {"stage": stage, "label": STAGE_LABELS.get(stage, stage), "count": 0, "value_inr": 0}
    for lead in leads:
        stage = normalize_stage(str(lead.get("pipeline_stage") or ""))
        if stage in {"CLOSED_LOST", "CLOSED_WON"}:
            continue
        unit = STAGE_VALUE_INR.get(stage, 20_000)
        if stage not in by_stage:
            by_stage[stage] = {"stage": stage, "label": STAGE_LABELS.get(stage, stage), "count": 0, "value_inr": 0}
        by_stage[stage]["count"] += 1
        by_stage[stage]["value_inr"] += unit
        if stage != "MATTER_CREATED":
            total += unit
    converted_value = sum(
        STAGE_VALUE_INR["MATTER_CREATED"]
        for lead in leads
        if normalize_stage(str(lead.get("pipeline_stage") or "")) == "MATTER_CREATED"
    )
    return {
        "active_pipeline_inr": total,
        "converted_inr": converted_value,
        "total_inr": total + converted_value,
        "by_stage": [by_stage[s] for s in PIPELINE_STAGES if s in by_stage and by_stage[s]["count"]],
    }


def _latest_ai_preview(leads: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = [
        lead
        for lead in leads
        if lead.get("analysis") or lead.get("analysis_json") or lead.get("last_analyzed_at")
    ]
    candidates.sort(key=lambda x: str(x.get("last_analyzed_at") or x.get("updated_at") or ""), reverse=True)
    if not candidates:
        return None
    lead = candidates[0]
    analysis = lead.get("analysis") or {}
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except json.JSONDecodeError:
            analysis = {}
    laws = analysis.get("applicable_laws") or []
    sections: List[str] = []
    for law in laws[:3]:
        if isinstance(law, dict):
            sections.extend(law.get("sections") or [])
    classification = analysis.get("classification") or {}
    score = (analysis.get("lead_score") or {}).get("total") or lead.get("lead_score") or 0
    doc_req = (analysis.get("document_readiness") or {}).get("required") or []
    required_docs = [
        str(d.get("label") or d) for d in doc_req[:6] if isinstance(d, dict) or isinstance(d, str)
    ]
    return {
        "lead_id": lead.get("lead_id"),
        "prospect_name": lead.get("prospect_name"),
        "case_type": classification.get("primary") or lead.get("case_type") or "General",
        "urgency": lead.get("urgency") or "medium",
        "risk_score": int(lead.get("risk_score") or score or 0),
        "sections": sections[:6],
        "recommended_action": (analysis.get("executive_summary") or "")[:280]
        or "Review AI analysis and schedule consultation.",
        "required_documents": required_docs,
        "lead_score": int(score or 0),
    }


def _ai_recommendations(leads: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, str]]:
    recs: List[Dict[str, str]] = []
    for lead in sorted(leads, key=lambda x: -int(x.get("lead_score") or 0)):
        if len(recs) >= limit:
            break
        stage = normalize_stage(str(lead.get("pipeline_stage") or ""))
        if stage in TERMINAL_STAGES:
            continue
        score = int(lead.get("lead_score") or 0)
        if score < 55:
            continue
        name = str(lead.get("prospect_name") or "Lead")
        case = str(lead.get("case_type") or "matter")
        if stage == "NEW_INQUIRY":
            recs.append(
                {
                    "title": f"High-value lead: {name}",
                    "body": f"Run AI analysis on {case} and schedule consultation within 24 hours.",
                    "lead_id": str(lead.get("lead_id") or ""),
                }
            )
        elif stage in {"DOCUMENTS_REQUESTED", "DOCUMENTS_RECEIVED"}:
            recs.append(
                {
                    "title": f"Request documents from {name}",
                    "body": "Send follow-up for FIR, identity proof, and supporting evidence.",
                    "lead_id": str(lead.get("lead_id") or ""),
                }
            )
        elif stage == "QUALIFIED":
            recs.append(
                {
                    "title": f"Convert {name} to matter",
                    "body": "Lead is qualified — high conversion probability.",
                    "lead_id": str(lead.get("lead_id") or ""),
                }
            )
    if not recs and leads:
        recs.append(
            {
                "title": "Enable client intake portal",
                "body": "Share your public intake link to collect inquiries automatically.",
                "lead_id": "",
            }
        )
    return recs


def _lead_sources(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    c = Counter((str(lead.get("referral_source") or "").strip() or "Direct / unknown") for lead in leads)
    return [{"source": k, "count": v} for k, v in c.most_common(10)]


def _today_kpis(leads: List[Dict[str, Any]]) -> Dict[str, int]:
    today = _utc_now().date().isoformat()
    new_today = sum(1 for lead in leads if str(lead.get("created_at") or "")[:10] == today)
    consultations_today = sum(
        1
        for lead in leads
        if normalize_stage(str(lead.get("pipeline_stage") or "")) == "CONSULTATION_SCHEDULED"
        and str(lead.get("updated_at") or "")[:10] == today
    )
    return {"new_today": new_today, "consultations_today": consultations_today}


def _public_portal(user_id: str, leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    enabled = os.getenv("INTAKE_PUBLIC_ENABLED", "0").lower() in {"1", "true", "yes"}
    base = (os.getenv("PUBLIC_APP_URL") or os.getenv("NEXT_PUBLIC_APP_URL") or "http://127.0.0.1:3000").rstrip("/")
    slug = (os.getenv("INTAKE_PORTAL_SLUG") or user_id[:12]).strip()
    path = f"/intake/client"
    public_url = f"{base}{path}"
    if slug:
        public_url = f"{base}{path}?firm={slug}"
    submissions = [lead for lead in leads if (lead.get("referral_source") or "").lower() in {"website", "public", "portal", "intake form"}]
    last_sub = ""
    if leads:
        leads_sorted = sorted(leads, key=lambda x: str(x.get("created_at") or ""), reverse=True)
        last_sub = str(leads_sorted[0].get("created_at") or "")
    return {
        "enabled": enabled,
        "public_url": public_url,
        "slug": slug,
        "submissions_count": len(submissions) or len(leads),
        "last_submission_at": last_sub,
        "setup_note": "Set INTAKE_PUBLIC_ENABLED=1 and INTAKE_ORG_USER_ID in server .env for live submissions.",
    }


def crm_command_center(user_id: str) -> Dict[str, Any]:
    dash = crm_dashboard(user_id)
    leads = _load_leads(user_id)
    kanban = crm_kanban(user_id)
    total = len(leads) or 1
    converted = sum(
        1
        for lead in leads
        if normalize_stage(str(lead.get("pipeline_stage") or "")) in {"MATTER_CREATED", "CLOSED_WON"}
    )
    today_kpis = _today_kpis(leads)
    kpis = dict(dash.get("kpis") or {})
    kpis.update(today_kpis)
    kpis["conversion_rate_pct"] = round(100 * converted / total, 1)
    kpis["urgent_count"] = len(_urgent_leads(leads, limit=50))

    column_counts = {
        stage: len((kanban.get("columns") or {}).get(stage) or [])
        for stage in PIPELINE_STAGES
    }
    kanban_samples: Dict[str, List[Dict[str, Any]]] = {}
    for stage in PIPELINE_STAGES:
        if stage in {"CLOSED_LOST", "CLOSED_WON"}:
            continue
        cards = (kanban.get("columns") or {}).get(stage) or []
        kanban_samples[stage] = [
            {
                "lead_id": c.get("lead_id"),
                "prospect_name": c.get("prospect_name"),
                "case_type": c.get("case_type"),
                "lead_score": c.get("lead_score"),
                "urgency": c.get("urgency"),
            }
            for c in cards[:4]
        ]

    return {
        "kpis": kpis,
        "funnel": dash.get("funnel") or [],
        "stages": dash.get("stages") or PIPELINE_STAGES,
        "stage_labels": STAGE_LABELS,
        "pipeline_value": _pipeline_value(leads),
        "urgent_leads": _urgent_leads(leads),
        "recent_activity": _firm_activity(user_id),
        "follow_ups": _follow_ups(leads),
        "lead_sources": _lead_sources(leads),
        "latest_ai": _latest_ai_preview(leads),
        "ai_recommendations": _ai_recommendations(leads),
        "kanban_preview": {"columns": column_counts, "stages": PIPELINE_STAGES, "samples": kanban_samples},
        "public_portal": _public_portal(user_id, leads),
        "has_leads": len(leads) > 0,
    }
