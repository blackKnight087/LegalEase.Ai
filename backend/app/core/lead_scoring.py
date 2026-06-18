"""Lead scoring engine — 0–100 with factor breakdown."""
from __future__ import annotations

import os
from typing import Any, Dict, List

_DEFAULT_WEIGHTS = {
    "evidence_strength": 20,
    "document_availability": 20,
    "legal_viability": 20,
    "financial_impact": 15,
    "urgency": 15,
    "jurisdiction_clarity": 10,
}


def _band(total: int) -> str:
    if total >= 85:
        return "excellent"
    if total >= 70:
        return "strong"
    if total >= 50:
        return "moderate"
    return "weak"


def compute_lead_score(
    *,
    intent: str = "",
    confidence: float = 0.5,
    urgency: str = "MEDIUM",
    risk_score: int = 50,
    params: Dict[str, Any] | None = None,
    document_readiness_pct: int = 0,
    evidence_readiness_pct: int = 0,
    has_witness_mention: bool = False,
    jurisdiction: str = "",
) -> Dict[str, Any]:
    params = params or {}
    weights = dict(_DEFAULT_WEIGHTS)
    raw = os.getenv("CRM_SCORE_WEIGHTS_JSON", "").strip()
    if raw:
        try:
            import json

            weights.update(json.loads(raw))
        except Exception:
            pass

    factors: List[Dict[str, Any]] = []

    ev = min(weights["evidence_strength"], int(evidence_readiness_pct / 5))
    if has_witness_mention:
        ev = min(weights["evidence_strength"], ev + 4)
    factors.append(
        {
            "name": "Evidence Strength",
            "score": ev,
            "max": weights["evidence_strength"],
            "note": "Based on evidence signals in intake and uploads",
        }
    )

    doc = min(weights["document_availability"], int(document_readiness_pct / 5))
    factors.append(
        {
            "name": "Document Availability",
            "score": doc,
            "max": weights["document_availability"],
            "note": "Required documents mentioned or uploaded",
        }
    )

    legal = min(weights["legal_viability"], int(confidence * weights["legal_viability"]))
    if intent and intent not in ("GENERAL", "GENERAL_CONSULTATION"):
        legal = min(weights["legal_viability"], legal + 3)
    factors.append(
        {
            "name": "Legal Viability",
            "score": legal,
            "max": weights["legal_viability"],
            "note": "Classification confidence and matter type clarity",
        }
    )

    fin = 5
    if params.get("amount_in_dispute"):
        fin = min(weights["financial_impact"], 12)
    factors.append(
        {
            "name": "Financial Impact",
            "score": fin,
            "max": weights["financial_impact"],
            "note": "Dispute value if stated",
        }
    )

    urg_map = {"HIGH": 15, "MEDIUM": 10, "LOW": 5}
    urg = urg_map.get((urgency or "MEDIUM").upper(), 10)
    factors.append(
        {
            "name": "Urgency",
            "score": min(weights["urgency"], urg),
            "max": weights["urgency"],
            "note": f"Urgency tier: {urgency}",
        }
    )

    jur = 3
    if jurisdiction:
        jur = min(weights["jurisdiction_clarity"], 8)
    if params.get("venue"):
        jur = min(weights["jurisdiction_clarity"], jur + 2)
    factors.append(
        {
            "name": "Jurisdiction Clarity",
            "score": jur,
            "max": weights["jurisdiction_clarity"],
            "note": jurisdiction or "Venue not yet clear",
        }
    )

    total = min(100, sum(int(f["score"]) for f in factors))
    return {
        "total": total,
        "band": _band(total),
        "factors": factors,
        "explanation": (
            f"Composite score {total}/100 ({_band(total)}). "
            f"Risk indicator {risk_score}/100. "
            "Higher scores reflect clearer jurisdiction, stronger evidence signals, and better document readiness."
        ),
    }
