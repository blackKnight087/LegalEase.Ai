"""Resolve and persist CRM lead AI scores and risk for Kanban and dashboards."""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from backend.app.core.lead_scoring import compute_lead_score


def _parse_analysis(lead: Dict[str, Any]) -> Dict[str, Any]:
    analysis = lead.get("analysis") or lead.get("analysis_json")
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except json.JSONDecodeError:
            analysis = {}
    return analysis if isinstance(analysis, dict) else {}


def _parse_params(lead: Dict[str, Any]) -> Dict[str, Any]:
    params = lead.get("extracted_params") or {}
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except json.JSONDecodeError:
            params = {}
    return params if isinstance(params, dict) else {}


def _band_from_total(total: int) -> str:
    if total >= 85:
        return "excellent"
    if total >= 70:
        return "strong"
    if total >= 50:
        return "moderate"
    return "weak"


def _risk_tier(risk: int) -> str:
    if risk >= 70:
        return "high"
    if risk >= 40:
        return "medium"
    return "low"


def _risk_to_scale_10(risk_100: int) -> int:
    if risk_100 <= 0:
        return 0
    return max(1, min(10, round(risk_100 / 10)))


def compute_quick_lead_analysis(
    lead: Dict[str, Any],
    user_id: str = "",
) -> Dict[str, Any]:
    """Fast rule-based score + analysis (no LLM) for leads missing AI scoring."""
    from backend.app.core.crm_service import analyze_intake_query
    from backend.app.core.intake_intelligence import assess_document_readiness, assess_evidence_readiness

    query = (lead.get("raw_intake_query") or "").strip()
    if len(query) < 8:
        return {
            "lead_score": {"total": 0, "band": "weak", "factors": [], "explanation": ""},
            "legacy": {"risk_score": 0, "urgency": "LOW"},
        }

    base = analyze_intake_query(query, user_id or str(lead.get("user_id") or ""))
    intent = base.get("intent") or "GENERAL"
    params = base.get("parameters") or {}
    if not isinstance(params, dict):
        params = {}

    risk = int(base.get("risk_score") or 50)
    urgency = str(base.get("urgency") or "MEDIUM")
    params["risk_score"] = risk
    params["urgency"] = urgency

    doc_r = assess_document_readiness(intent, query, [])
    ev_r = assess_evidence_readiness(query, [])
    score = compute_lead_score(
        intent=intent,
        confidence=float(base.get("confidence") or 0.5),
        urgency=urgency,
        risk_score=risk,
        params=params,
        document_readiness_pct=int(doc_r.get("percent") or 0),
        evidence_readiness_pct=int(ev_r.get("percent") or 0),
        has_witness_mention=bool(ev_r.get("has_witness_mention")),
        jurisdiction=str(base.get("jurisdiction") or params.get("venue", "")),
    )

    return {
        "lead_score": score,
        "classification": {
            "primary": base.get("case_type") or intent,
            "confidence": float(base.get("confidence") or 0.5),
        },
        "document_readiness": doc_r,
        "evidence_readiness": ev_r,
        "executive_summary": (base.get("legal_analysis") or "")[:500],
        "legacy": {
            "intent": intent,
            "parameters": params,
            "urgency": urgency,
            "risk_score": risk,
        },
    }


def resolve_lead_score(lead: Dict[str, Any]) -> Tuple[int, str]:
    """Best available score: DB column → stored analysis → quick compute."""
    stored = int(lead.get("lead_score") or 0)
    band = str(lead.get("lead_score_band") or "").strip()

    analysis = _parse_analysis(lead)
    ls = analysis.get("lead_score") if analysis else {}
    if isinstance(ls, dict):
        from_analysis = int(ls.get("total") or 0)
        if from_analysis > 0:
            return from_analysis, str(ls.get("band") or band or _band_from_total(from_analysis))

    if stored > 0:
        return stored, band or _band_from_total(stored)

    quick = compute_quick_lead_analysis(lead)
    qscore = quick.get("lead_score") or {}
    total = int(qscore.get("total") or 0)
    if total > 0:
        return total, str(qscore.get("band") or _band_from_total(total))

    return 0, band or "weak"


def resolve_lead_risk(lead: Dict[str, Any]) -> Tuple[int, str, int]:
    """
    Resolve legal risk on 0–100 scale, tier label, and 1–10 display scale.
    Higher risk = more urgent/complex matter (not lead quality).
    """
    analysis = _parse_analysis(lead)
    legacy = analysis.get("legacy") or {}
    params = _parse_params(lead)

    candidates = [
        lead.get("risk_score"),
        params.get("risk_score"),
        legacy.get("risk_score"),
    ]
    for raw in candidates:
        if raw is None:
            continue
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            return val, _risk_tier(val), _risk_to_scale_10(val)

    query = (lead.get("raw_intake_query") or "").strip()
    if len(query) >= 8:
        quick = compute_quick_lead_analysis(lead, str(lead.get("user_id") or ""))
        leg = quick.get("legacy") or {}
        val = int(leg.get("risk_score") or 0)
        if val > 0:
            return val, _risk_tier(val), _risk_to_scale_10(val)

    urgency = str(lead.get("urgency") or legacy.get("urgency") or params.get("urgency") or "MEDIUM").upper()
    lead_score = resolve_lead_score(lead)[0]
    base = 35
    if urgency in {"HIGH", "URGENT", "CRITICAL"}:
        base += 28
    elif urgency == "LOW":
        base -= 12
    if lead_score >= 75:
        base += 8
    elif lead_score < 40:
        base -= 5
    if "criminal" in str(lead.get("calculated_intent") or "").lower():
        base += 15
    val = max(10, min(95, base))
    return val, _risk_tier(val), _risk_to_scale_10(val)


def ensure_lead_scores(user_id: str, leads: list[Dict[str, Any]]) -> None:
    """Persist scores and risk for leads that have intake text but missing fields."""
    from backend.app.core.crm_v2_service import update_lead_extended

    for lead in leads:
        lead_id = str(lead.get("lead_id") or "")
        if not lead_id:
            continue

        total, band = resolve_lead_score(lead)
        risk_100, risk_tier, risk_10 = resolve_lead_risk(lead)
        if total <= 0 and risk_100 <= 0:
            continue

        analysis = _parse_analysis(lead)
        params = _parse_params(lead)
        stored_score = int(lead.get("lead_score") or 0)
        stored_risk = int(params.get("risk_score") or lead.get("risk_score") or 0)

        needs_update = (
            (total > 0 and stored_score != total)
            or (risk_100 > 0 and stored_risk != risk_100)
            or not analysis.get("lead_score")
        )
        if not needs_update:
            continue

        fields: Dict[str, Any] = {}
        if total > 0:
            fields["lead_score"] = total
            fields["lead_score_band"] = band

        if risk_100 > 0:
            params = {**params, "risk_score": risk_100, "urgency": params.get("urgency") or risk_tier}
            fields["extracted_params"] = params

        if not analysis.get("lead_score") or not legacy_risk_present(analysis, risk_100):
            quick = compute_quick_lead_analysis(lead, user_id)
            existing = analysis
            merged = {**existing, **quick} if existing else quick
            if risk_100 > 0 and isinstance(merged.get("legacy"), dict):
                merged["legacy"]["risk_score"] = risk_100
            fields["analysis_json"] = merged

        update_lead_extended(user_id, lead_id, **fields)

        if total > 0:
            lead["lead_score"] = total
            lead["lead_score_band"] = band
        if risk_100 > 0:
            lead["risk_score"] = risk_100
            lead["extracted_params"] = params
        if "analysis_json" in fields:
            lead["analysis"] = fields["analysis_json"]


def legacy_risk_present(analysis: Dict[str, Any], risk: int) -> bool:
    legacy = analysis.get("legacy") or {}
    try:
        return int(legacy.get("risk_score") or 0) == risk
    except (TypeError, ValueError):
        return False
