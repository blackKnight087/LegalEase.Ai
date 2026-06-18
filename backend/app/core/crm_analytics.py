"""CRM firm-wide analytics."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from backend.app.core.crm_kanban_enrich import STAGE_VALUE_INR, enrich_kanban_columns
from backend.app.core.crm_schema import (
    PIPELINE_STAGES,
    STAGE_EMPTY_HINTS,
    TERMINAL_STAGES,
    ensure_crm_v2_schema,
    normalize_stage,
)
from backend.app.core.crm_service import _crm_scope
from backend.app.core.database import connect_data_db


def crm_dashboard(user_id: str) -> Dict[str, Any]:
    ensure_crm_v2_schema()
    scope_sql, scope_params = _crm_scope(user_id)
    conn = connect_data_db()
    rows = conn.execute(
        f"""
        SELECT pipeline_stage, lead_score, lead_score_band, calculated_intent,
               referral_source, assigned_lawyer_id, created_at
        FROM crm_leads WHERE {scope_sql}
        """,
        scope_params,
    ).fetchall()
    conn.close()

    stages = [normalize_stage(r[0]) for r in rows]
    c = Counter(stages)
    high_risk = sum(
        1 for r in rows if int(r[1] or 0) >= 70 or normalize_stage(r[0]) == "CLOSED_LOST"
    )

    return {
        "kpis": {
            "new_leads": c.get("NEW_INQUIRY", 0) + c.get("AI_REVIEW", 0),
            "qualified": c.get("QUALIFIED", 0),
            "converted": c.get("MATTER_CREATED", 0) + c.get("CLOSED_WON", 0),
            "pending_consultations": c.get("CONSULTATION_SCHEDULED", 0),
            "high_risk": high_risk,
            "rejected": c.get("CLOSED_LOST", 0),
            "total": len(rows),
        },
        "funnel": [{"stage": s, "count": c.get(s, 0)} for s in PIPELINE_STAGES],
        "stages": PIPELINE_STAGES,
    }


def _kanban_metrics(leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    active = [
        l
        for l in leads
        if normalize_stage(str(l.get("pipeline_stage") or "")) not in TERMINAL_STAGES
    ]
    pipeline_inr = sum(
        STAGE_VALUE_INR.get(normalize_stage(str(l.get("pipeline_stage") or "")), 20_000)
        for l in active
    )
    converted = sum(
        1
        for l in leads
        if normalize_stage(str(l.get("pipeline_stage") or "")) in {"MATTER_CREATED", "CLOSED_WON"}
    )
    consultations = sum(
        1
        for l in leads
        if normalize_stage(str(l.get("pipeline_stage") or "")) == "CONSULTATION_SCHEDULED"
    )
    total = len(leads) or 1
    return {
        "total_leads": len(leads),
        "pipeline_value_inr": pipeline_inr,
        "conversion_rate": round(100 * converted / total, 1),
        "consultations_scheduled": consultations,
        "matters_created": converted,
        "revenue_forecast_inr": int(pipeline_inr * 0.35),
    }


def crm_kanban(user_id: str) -> Dict[str, Any]:
    ensure_crm_v2_schema()
    from backend.app.core.crm_lead_score import ensure_lead_scores
    from backend.app.core.crm_v2_service import list_leads_full

    leads = list_leads_full(user_id, limit=500)
    try:
        ensure_lead_scores(user_id, leads)
    except Exception:
        pass
    columns: Dict[str, List[Dict[str, Any]]] = {s: [] for s in PIPELINE_STAGES}
    for lead in leads:
        st = normalize_stage(str(lead.get("pipeline_stage") or "NEW_INQUIRY"))
        if st not in columns:
            st = "NEW_INQUIRY"
        columns[st].append(lead)
    columns = enrich_kanban_columns(columns)
    return {
        "columns": columns,
        "stages": PIPELINE_STAGES,
        "metrics": _kanban_metrics(leads),
        "empty_hints": STAGE_EMPTY_HINTS,
    }


def crm_analytics_report(user_id: str) -> Dict[str, Any]:
    ensure_crm_v2_schema()
    scope_sql, scope_params = _crm_scope(user_id)
    conn = connect_data_db()
    rows = conn.execute(
        f"""
        SELECT pipeline_stage, referral_source, calculated_intent, lead_score,
               assigned_lawyer_id
        FROM crm_leads WHERE {scope_sql}
        """,
        scope_params,
    ).fetchall()
    conn.close()

    sources = Counter((r[1] or "Unknown").strip() or "Unknown" for r in rows)
    types = Counter((r[2] or "GENERAL") for r in rows)
    converted = sum(1 for r in rows if normalize_stage(r[0]) == "MATTER_CREATED")
    total = len(rows) or 1
    lawyers: Dict[str, Dict[str, int]] = {}
    for r in rows:
        lid = (r[4] or "unassigned").strip() or "unassigned"
        lawyers.setdefault(lid, {"assigned": 0, "converted": 0})
        lawyers[lid]["assigned"] += 1
        if normalize_stage(r[0]) == "MATTER_CREATED":
            lawyers[lid]["converted"] += 1

    scores = [int(r[3] or 0) for r in rows if r[3]]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "lead_sources": [{"source": k, "count": v} for k, v in sources.most_common(12)],
        "case_types": [{"type": k, "count": v} for k, v in types.most_common(12)],
        "conversion_rate": round(100 * converted / total, 1),
        "avg_lead_score": avg_score,
        "lawyer_performance": [
            {"lawyer_id": k, **v} for k, v in lawyers.items()
        ],
        "total_leads": total,
    }
