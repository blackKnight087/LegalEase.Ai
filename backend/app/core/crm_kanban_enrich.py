"""Enrich CRM leads with Kanban card display fields."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.core.crm_lead_score import resolve_lead_risk, resolve_lead_score
from backend.app.core.crm_schema import STAGE_LABELS, normalize_stage
from backend.app.core.database import connect_data_db

STAGE_VALUE_INR: Dict[str, int] = {
    "NEW_INQUIRY": 15_000,
    "AI_REVIEW": 25_000,
    "CONSULTATION_SCHEDULED": 40_000,
    "DOCUMENTS_REQUESTED": 50_000,
    "DOCUMENTS_RECEIVED": 65_000,
    "QUALIFIED": 80_000,
    "ENGAGEMENT_LETTER_SENT": 100_000,
    "RETAINER_PAID": 150_000,
    "MATTER_CREATED": 200_000,
    "CLOSED_WON": 200_000,
    "CLOSED_LOST": 0,
}


def _doc_counts(lead_ids: List[str]) -> Dict[str, int]:
    if not lead_ids:
        return {}
    from backend.app.core.crm_schema import ensure_crm_v2_schema

    ensure_crm_v2_schema()
    conn = connect_data_db()
    placeholders = ",".join("?" * len(lead_ids))
    rows = conn.execute(
        f"SELECT lead_id, COUNT(*) FROM crm_lead_documents WHERE lead_id IN ({placeholders}) GROUP BY lead_id",
        lead_ids,
    ).fetchall()
    conn.close()
    return {r[0]: int(r[1]) for r in rows}


def _days_since(iso: str) -> int:
    if not iso:
        return 0
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except ValueError:
        return 0


def _priority(lead: Dict[str, Any], score: int) -> str:
    urgency = str(lead.get("urgency") or "").lower()
    if urgency in {"high", "urgent", "critical"} or score >= 75:
        return "high"
    if urgency in {"medium", "moderate"} or score >= 50:
        return "medium"
    return "low"


def _conversion_probability(score: int, stage: str) -> int:
    base = min(95, max(12, score))
    boosts = {
        "QUALIFIED": 12,
        "ENGAGEMENT_LETTER_SENT": 18,
        "RETAINER_PAID": 28,
        "CONSULTATION_SCHEDULED": 8,
        "DOCUMENTS_RECEIVED": 10,
    }
    return min(98, base + boosts.get(stage, 0))


def _follow_up_label(lead: Dict[str, Any], stage: str, days: int) -> str:
    if stage == "CONSULTATION_SCHEDULED":
        return "Consultation prep"
    if stage in {"DOCUMENTS_REQUESTED", "DOCUMENTS_RECEIVED"}:
        return "Documents awaited"
    if days >= 5 and stage in {"NEW_INQUIRY", "AI_REVIEW"}:
        return "Overdue follow-up"
    if days >= 2:
        return "Follow up today"
    if days == 1:
        return "Follow up tomorrow"
    return "No action due"


def _doc_badges(lead: Dict[str, Any], doc_count: int) -> List[Dict[str, str]]:
    analysis = lead.get("analysis") or {}
    if isinstance(analysis, str):
        import json

        try:
            analysis = json.loads(analysis)
        except json.JSONDecodeError:
            analysis = {}
    doc_ready = (analysis.get("document_readiness") or {}) if isinstance(analysis, dict) else {}
    required = doc_ready.get("required") or []
    badges: List[Dict[str, str]] = []
    if doc_count > 0:
        badges.append({"label": "Documents received", "status": "ok"})
    elif required:
        badges.append({"label": "Documents missing", "status": "warn"})
    else:
        badges.append({"label": "Documents pending", "status": "neutral"})
    pct = int(doc_ready.get("percent") or 0)
    if pct >= 80:
        badges.append({"label": f"Readiness {pct}%", "status": "ok"})
    intent = str(lead.get("calculated_intent") or "").upper()
    if "CRIMINAL" in intent and doc_count == 0:
        badges.append({"label": "FIR pending", "status": "warn"})
    return badges[:3]


def _recommended_action(lead: Dict[str, Any], stage: str, score: int) -> str:
    analysis = lead.get("analysis") or {}
    if isinstance(analysis, dict) and analysis.get("executive_summary"):
        return str(analysis["executive_summary"])[:160]
    if stage == "NEW_INQUIRY":
        return "Run AI review and schedule initial consultation."
    if stage == "AI_REVIEW":
        return "Schedule consultation within 24–48 hours."
    if stage == "DOCUMENTS_REQUESTED":
        return "Request FIR, identity proof, and supporting evidence."
    if stage == "QUALIFIED":
        return "Send engagement letter and discuss retainer."
    if stage == "RETAINER_PAID":
        return "Convert to matter and open case file."
    if score >= 70:
        return "High-value lead — prioritize personal outreach."
    return "Review intake notes and update next step."


def enrich_lead_for_kanban(lead: Dict[str, Any], *, doc_count: int = 0) -> Dict[str, Any]:
    stage = normalize_stage(str(lead.get("pipeline_stage") or "NEW_INQUIRY"))
    score, score_band = resolve_lead_score(lead)
    risk_100, risk_tier, risk_10 = resolve_lead_risk(lead)
    lead = {
        **lead,
        "lead_score": score,
        "lead_score_band": score_band or lead.get("lead_score_band"),
        "risk_score": risk_100,
    }
    days = _days_since(str(lead.get("created_at") or ""))
    priority = _priority(lead, score)
    assigned = str(lead.get("assigned_lawyer_id") or lead.get("assigned_attorney_id") or "").strip()
    if assigned and len(assigned) > 20:
        assigned = f"Associate {assigned[:6]}…"
    elif not assigned:
        assigned = "Unassigned"
    analysis = lead.get("analysis") or {}
    classification = {}
    if isinstance(analysis, dict):
        classification = analysis.get("classification") or {}
    case_type = (
        lead.get("case_type")
        or (classification.get("primary") if isinstance(classification, dict) else None)
        or lead.get("calculated_intent")
        or "General"
    )
    return {
        **lead,
        "pipeline_stage": stage,
        "kanban": {
            "case_type_label": str(case_type),
            "priority": priority,
            "ai_score": score,
            "score_band": score_band,
            "conversion_probability": _conversion_probability(score, stage),
            "potential_value_inr": STAGE_VALUE_INR.get(stage, 25_000),
            "days_since_created": days,
            "assigned_to": assigned,
            "follow_up_label": _follow_up_label(lead, stage, days),
            "doc_badges": _doc_badges(lead, doc_count),
            "recommended_action": _recommended_action(lead, stage, score),
            "stage_label": STAGE_LABELS.get(stage, stage),
            "risk_score": risk_100,
            "risk_tier": risk_tier,
            "risk_scale_10": risk_10,
        },
    }


def enrich_kanban_columns(
    columns: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    lead_ids = [
        str(lead.get("lead_id"))
        for leads in columns.values()
        for lead in leads
        if lead.get("lead_id")
    ]
    counts = _doc_counts(lead_ids)
    out: Dict[str, List[Dict[str, Any]]] = {}
    for stage, leads in columns.items():
        out[stage] = [
            enrich_lead_for_kanban(lead, doc_count=counts.get(str(lead.get("lead_id")), 0))
            for lead in leads
        ]
    return out
