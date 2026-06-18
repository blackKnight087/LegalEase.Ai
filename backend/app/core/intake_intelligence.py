"""Full intake analysis — structured analysis_json for CRM 2.0."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from backend.app.core.crm_service import (
    CASE_TYPE_LABELS,
    _extract_params,
    _likely_sections,
    analyze_intake_query,
    classify_intake_query,
)
from backend.app.core.document_readiness import assess_document_readiness
from backend.app.core.evidence_readiness import assess_evidence_readiness
from backend.app.core.lead_scoring import compute_lead_score


def _empty_analysis() -> Dict[str, Any]:
    return {
        "executive_summary": "",
        "classification": {
            "primary": "General",
            "secondary": "",
            "subcategory": "",
            "confidence": 0.0,
        },
        "applicable_laws": [],
        "jurisdiction": {
            "city": "",
            "district": "",
            "state": "",
            "likely_court": "",
            "likely_police_station": "",
            "confidence": 0.0,
        },
        "lead_score": {"total": 0, "band": "weak", "factors": [], "explanation": ""},
        "case_strength": {"rating": "moderate", "strengths": [], "weaknesses": []},
        "document_readiness": {"percent": 0, "required": []},
        "evidence_readiness": {"percent": 0, "types": []},
        "consultation_questions": [],
        "contradictions": [],
        "entities": [],
        "matter_preview": {
            "suggested_name": "",
            "tasks": [],
            "deadlines": [],
            "timeline_events": [],
        },
    }


def _extract_entities_rule(text: str) -> List[Dict[str, Any]]:
    entities: List[Dict[str, Any]] = []
    seen: set = set()
    for m in re.finditer(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
        text or "",
    ):
        label = m.group(1).strip()
        if len(label) < 4 or label.lower() in ("the", "and", "court", "india"):
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        role = "party"
        if re.search(r"\b(client|applicant|petitioner|plaintiff)\b", text[max(0, m.start() - 40) : m.end() + 40], re.I):
            role = "client"
        elif re.search(r"\b(accused|defendant|respondent|opposing)\b", text[max(0, m.start() - 40) : m.end() + 40], re.I):
            role = "opposing_party"
        entities.append({"type": "person", "label": label, "role": role})
    for m in re.finditer(
        r"\b((?:District|High|Supreme)\s+Court[^,.]{0,40}|Police Station[^,.]{0,40})\b",
        text or "",
        re.I,
    ):
        label = m.group(1).strip()
        k = label.lower()
        if k not in seen:
            seen.add(k)
            entities.append(
                {
                    "type": "court" if "court" in k else "police_station",
                    "label": label,
                    "role": "",
                }
            )
    return entities[:25]


def _consultation_questions(intent: str, params: Dict[str, Any]) -> List[str]:
    base = [
        "What outcome do you want from legal action?",
        "What documents do you currently have in your possession?",
        "Have you sent or received any legal notice?",
        "Are there witnesses or digital evidence available?",
    ]
    extra: Dict[str, List[str]] = {
        "PROPERTY_REAL_ESTATE": [
            "When was possession lost or disputed?",
            "Do you have title documents or mutation records?",
            "Has any notice to vacate been issued?",
        ],
        "CRIMINAL_DEFENSE": [
            "Has an FIR been registered? What is the FIR number?",
            "Are you in custody or on bail?",
            "What is the next court date?",
        ],
        "FAMILY_LAW": [
            "Are there children involved?",
            "Is there a pending maintenance or divorce petition?",
        ],
        "COMMERCIAL_LITIGATION": [
            "What is the contract or payment timeline?",
            "Have you attempted recovery informally?",
        ],
    }
    return base + extra.get(intent, [])[:4]


def _executive_summary(query: str, classification: Dict[str, Any]) -> str:
    intent = classification.get("intent", "GENERAL")
    case_type = classification.get("case_type") or CASE_TYPE_LABELS.get(intent, "General")
    venue = (classification.get("parameters") or {}).get("venue", "")
    venue_p = f" in {venue}" if venue else ""
    return (
        f"This appears to be a {case_type.lower()} matter{venue_p}. "
        f"The intake describes: {(query or '')[:200]}{'…' if len(query or '') > 200 else ''} "
        f"Preliminary review suggests further document verification and a consultation are appropriate."
    )


def _case_strength(risk: int, doc_pct: int, ev_pct: int) -> Dict[str, Any]:
    strengths: List[str] = []
    weaknesses: List[str] = []
    if ev_pct >= 50:
        strengths.append("Evidence signals identified in intake")
    else:
        weaknesses.append("Limited evidence described so far")
    if doc_pct >= 50:
        strengths.append("Some required documents referenced")
    else:
        weaknesses.append("Key documents not yet confirmed")
    if risk < 50:
        strengths.append("Lower preliminary risk score")
    else:
        weaknesses.append("Elevated risk factors detected")
    rating = "strong" if len(strengths) >= 2 and len(weaknesses) <= 1 else "moderate"
    if len(weaknesses) >= 3:
        rating = "weak"
    return {"rating": rating, "strengths": strengths, "weaknesses": weaknesses}


def _matter_preview(
    prospect_name: str,
    intent: str,
    analysis: Dict[str, Any],
) -> Dict[str, Any]:
    practice = CASE_TYPE_LABELS.get(intent, "General")
    name = f"{prospect_name} — {practice}"
    tasks = [
        {"title": "Verify client identity and retainer", "due_days": 3},
        {"title": "Collect missing documents from checklist", "due_days": 7},
        {"title": "Schedule consultation", "due_days": 5},
    ]
    deadlines = [
        {"title": "Document collection deadline", "due_days": 14},
        {"title": "Consultation", "due_days": 7},
    ]
    if intent == "CRIMINAL_DEFENSE":
        tasks.insert(0, {"title": "Review FIR and custody status", "due_days": 2})
    return {
        "suggested_name": name,
        "tasks": tasks,
        "deadlines": deadlines,
        "timeline_events": [
            {"title": "Intake received", "event_type": "intake"},
            {"title": "AI qualification completed", "event_type": "intake"},
        ],
    }


def _detect_contradictions(doc_texts: List[str]) -> List[Dict[str, Any]]:
    if len(doc_texts) < 2:
        return []
    out: List[Dict[str, Any]] = []
    dates_a = re.findall(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", doc_texts[0])
    dates_b = re.findall(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", doc_texts[1])
    if dates_a and dates_b and dates_a[0] != dates_b[0]:
        out.append(
            {
                "a": f"Document 1 date: {dates_a[0]}",
                "b": f"Document 2 date: {dates_b[0]}",
                "severity": "medium",
            }
        )
    return out


def run_full_intake_analysis(
    query: str,
    user_id: str = "",
    *,
    prospect_name: str = "Client",
    doc_texts: List[str] | None = None,
) -> Dict[str, Any]:
    base = analyze_intake_query(query, user_id)
    intent = base.get("intent") or "GENERAL"
    params = base.get("parameters") or {}
    if not isinstance(params, dict):
        params = _extract_params(query)

    doc_r = assess_document_readiness(intent, query, doc_texts)
    ev_r = assess_evidence_readiness(query, doc_texts)
    score = compute_lead_score(
        intent=intent,
        confidence=float(base.get("confidence") or 0.5),
        urgency=str(base.get("urgency") or "MEDIUM"),
        risk_score=int(base.get("risk_score") or 50),
        params=params,
        document_readiness_pct=doc_r["percent"],
        evidence_readiness_pct=ev_r["percent"],
        has_witness_mention=ev_r.get("has_witness_mention", False),
        jurisdiction=str(base.get("jurisdiction") or params.get("venue", "")),
    )

    sections = base.get("likely_sections") or _likely_sections(query)
    laws: List[Dict[str, Any]] = []
    if sections:
        laws.append(
            {
                "act": "Indian Penal Code / BNS",
                "sections": sections,
                "confidence": 0.75 if len(sections) <= 3 else 0.55,
            }
        )

    venue = str(base.get("jurisdiction") or params.get("venue", ""))
    jurisdiction = {
        "city": venue,
        "district": venue,
        "state": "",
        "likely_court": "District Court" if intent != "CRIMINAL_DEFENSE" else "Magistrate / Sessions Court",
        "likely_police_station": "Local police station" if intent == "CRIMINAL_DEFENSE" else "",
        "confidence": 0.7 if venue else 0.35,
    }

    classification = {
        "primary": base.get("case_type") or CASE_TYPE_LABELS.get(intent, "General"),
        "secondary": intent.replace("_", " ").title(),
        "subcategory": params.get("timeline_hint", "") or "",
        "confidence": float(base.get("confidence") or 0.5),
    }

    analysis = _empty_analysis()
    analysis["executive_summary"] = _executive_summary(query, base)
    analysis["classification"] = classification
    analysis["applicable_laws"] = laws
    analysis["jurisdiction"] = jurisdiction
    analysis["lead_score"] = score
    analysis["case_strength"] = _case_strength(
        int(base.get("risk_score") or 50),
        doc_r["percent"],
        ev_r["percent"],
    )
    analysis["document_readiness"] = doc_r
    analysis["evidence_readiness"] = ev_r
    analysis["consultation_questions"] = _consultation_questions(intent, params)
    analysis["contradictions"] = _detect_contradictions(doc_texts or [])
    analysis["entities"] = _extract_entities_rule(query)
    analysis["matter_preview"] = _matter_preview(prospect_name, intent, analysis)

    if os.getenv("LLM_INTAKE_FULL_ANALYSIS", "1").lower() in {"1", "true", "yes"}:
        try:
            from backend.app.core.llm_orchestrator import generate_intake_legal_analysis

            llm = generate_intake_legal_analysis(query, base, user_id=user_id, kb_snippets=[])
            if llm.get("ok") and llm.get("markdown"):
                analysis["executive_summary"] = (llm["markdown"] or "")[:1200]
        except Exception:
            pass

    analysis["legacy"] = {
        "intent": intent,
        "risk_score": base.get("risk_score"),
        "urgency": base.get("urgency"),
        "legal_analysis": base.get("legal_analysis"),
    }
    return analysis
