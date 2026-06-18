"""
Phase 3 — Client intake CRM with intent classification and follow-up drafts.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.crm_schema import PIPELINE_STAGES
from backend.app.core.database import connect_data_db
from backend.app.core.org_service import get_primary_org_id
from backend.app.core.saas_schema import ensure_saas_schema

_CRM_ORG_MIGRATED = False


def _migrate_crm_org_scope() -> None:
    """Add org_id column and backfill from org membership (once per process)."""
    global _CRM_ORG_MIGRATED
    if _CRM_ORG_MIGRATED:
        return
    from backend.app.core.schema_migrations import apply_migrations

    apply_migrations(tables=["crm_leads"])
    conn = connect_data_db()
    try:
        conn.execute(
            """
            UPDATE crm_leads SET org_id = (
                SELECT org_id FROM org_members
                WHERE user_id = crm_leads.user_id
                ORDER BY CASE role WHEN 'owner' THEN 0 ELSE 1 END, id ASC
                LIMIT 1
            )
            WHERE (org_id IS NULL OR org_id = '') AND user_id != ''
            """
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
    _CRM_ORG_MIGRATED = True


def _crm_scope(user_id: str) -> Tuple[str, List[Any]]:
    """Tenant filter: org-scoped when user belongs to an org, else user-owned leads only."""
    org_id = get_primary_org_id(str(user_id))
    if org_id:
        return "org_id = ?", [org_id]
    return "user_id = ?", [str(user_id)]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sig(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", (text or "").lower()).encode()).hexdigest()[:24]


CASE_TYPE_LABELS = {
    "CRIMINAL_DEFENSE": "Criminal",
    "COMMERCIAL_LITIGATION": "Civil",
    "FAMILY_LAW": "Family / Divorce",
    "PROPERTY_REAL_ESTATE": "Property",
    "EMPLOYMENT_LABOUR": "Employment",
    "GENERAL_CONSULTATION": "General",
    "GENERAL": "General",
}

_INTENT_RULES: List[Tuple[str, re.Pattern, Dict[str, Any]]] = [
    (
        "CRIMINAL_DEFENSE",
        re.compile(
            r"\b(fir|police|arrest|bail|ipc|bns|cheating|murder|assault|"
            r"criminal|accused|charge|custody)\b",
            re.I,
        ),
        {"priority": "HIGH"},
    ),
    (
        "COMMERCIAL_LITIGATION",
        re.compile(
            r"\b(contract|breach|vendor|payment|invoice|company|"
            r"shareholder|partnership|commercial|fraud|recovery)\b",
            re.I,
        ),
        {"priority": "MEDIUM"},
    ),
    (
        "FAMILY_LAW",
        re.compile(
            r"\b(divorce|custody|maintenance|dowry|matrimonial|"
            r"hindu marriage|domestic violence|498a)\b",
            re.I,
        ),
        {"priority": "HIGH"},
    ),
    (
        "PROPERTY_REAL_ESTATE",
        re.compile(
            r"\b(property|land|lease|rent|tenant|eviction|"
            r"registration|title|flat|builder)\b",
            re.I,
        ),
        {"priority": "MEDIUM"},
    ),
    (
        "EMPLOYMENT_LABOUR",
        re.compile(
            r"\b(termination|wrongful|salary|pf|esic|"
            r"workman|industrial dispute|harassment at work)\b",
            re.I,
        ),
        {"priority": "MEDIUM"},
    ),
]


def _extract_params(text: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    amount = re.search(
        r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:lakh|lakhs|crore|cr)?",
        text,
        re.I,
    )
    if amount:
        params["amount_in_dispute"] = amount.group(0).strip()
    venue = re.search(
        r"\b(?:in|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        text,
    )
    if venue:
        params["venue"] = venue.group(1)
    date = re.search(
        r"\b(?:january|february|march|april|may|june|july|august|"
        r"september|october|november|december|\d{1,2}[/-]\d{2,4})\b",
        text,
        re.I,
    )
    if date:
        params["timeline_hint"] = date.group(0)
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if email:
        params["email_found"] = email.group(0)
    phone = re.search(r"\b[6-9]\d{9}\b", text)
    if phone:
        params["phone_found"] = phone.group(0)
    return params


def _likely_sections(text: str) -> List[str]:
    found: List[str] = []
    for m in re.finditer(r"\b(?:IPC|BNS)\s+(\d{1,4}[a-z]?)\b", text or "", re.I):
        label = f"{m.group(0).upper()}"
        if label not in found:
            found.append(label)
    return found[:8]


def _intake_kb_snippets(query: str, user_id: str) -> List[str]:
    """Light RAG for intake (BGE embeddings only — no LLM)."""
    import os

    if os.getenv("LLM_INTAKE_USE_RAG", "0").lower() not in {"1", "true", "yes"}:
        return []
    if not user_id:
        return []
    try:
        from backend.app.core.rag_engine import retrieve
        from rag import index_exists
        from app import get_user_index_dir

        index_dir = get_user_index_dir(str(user_id))
        if not index_exists(index_dir):
            return []
        k = int(os.getenv("LLM_INTAKE_RAG_K", "3"))
        chunks = retrieve(str(user_id), query, k=k)
        return [(c.get("content") or "")[:600] for c in chunks if (c.get("content") or "").strip()]
    except Exception:
        return []


def analyze_intake_query(query: str, user_id: str = "") -> Dict[str, Any]:
    """Full intake analysis: intent, risk, urgency, sections, jurisdiction."""
    base = classify_intake_query(query, user_id)
    try:
        from backend.app.core.llm_orchestrator import (
            classify_fast,
            generate_intake_legal_analysis,
            merge_classification,
        )
        from backend.app.core.llm_task_router import router_enabled

        if router_enabled():
            llm_cls = classify_fast(query, user_id=user_id)
            if llm_cls.get("source") != "skipped_same_model":
                base = merge_classification(base, llm_cls)
    except Exception:
        pass
    intent = base.get("intent") or "GENERAL"
    params = base.get("parameters") or {}
    urgency = "LOW"
    for name, _pat, meta in _INTENT_RULES:
        if name == intent:
            urgency = meta.get("priority", "MEDIUM")
            break
    if urgency == "MEDIUM" and re.search(r"\burgent|immediate|arrest|custody\b", query, re.I):
        urgency = "HIGH"
    sections = _likely_sections(query)
    risk = 35
    if urgency == "HIGH":
        risk += 30
    if sections:
        risk += 15
    if params.get("amount_in_dispute"):
        risk += 10
    risk = min(95, risk)
    out = {
        **base,
        "case_type": base.get("case_type") or CASE_TYPE_LABELS.get(intent, "General"),
        "urgency": base.get("urgency") or urgency,
        "risk_score": risk,
        "likely_sections": sections,
        "jurisdiction": params.get("venue", ""),
        "pipeline_stages": PIPELINE_STAGES,
    }
    try:
        from backend.app.core.llm_orchestrator import (
            _rule_based_intake_markdown,
            generate_intake_legal_analysis,
        )
        from backend.app.core.llm_task_router import router_enabled

        import os

        out["legal_analysis"] = _rule_based_intake_markdown(query, out)
        out["routing"] = {
            "classifier": "rules",
            "reasoning": "rules",
            "retrieval": "none",
        }

        if (
            router_enabled()
            and (query or "").strip()
            and os.getenv("LLM_INTAKE_LEGAL_ANALYSIS", "0").lower() in {"1", "true", "yes"}
        ):
            snippets = _intake_kb_snippets(query, user_id)
            analysis = generate_intake_legal_analysis(
                query,
                out,
                user_id=user_id,
                kb_snippets=snippets,
            )
            if analysis.get("ok") and analysis.get("markdown"):
                out["legal_analysis"] = analysis["markdown"]
                role = analysis.get("model_role") or "legalease-tuned"
                out["routing"] = {
                    "classifier": "legalease-tuned",
                    "reasoning": role,
                    "retrieval": "embeddings" if snippets else "none",
                }
                if analysis.get("llm_error"):
                    out["legal_analysis_note"] = (
                        "Ollama was busy; showing rule-based analysis."
                    )
    except Exception as exc:
        import logging

        logging.getLogger("legalease.crm").warning("intake analysis enrich failed: %s", exc)
        if not out.get("legal_analysis"):
            try:
                from backend.app.core.llm_orchestrator import _rule_based_intake_markdown

                out["legal_analysis"] = _rule_based_intake_markdown(query, out)
            except Exception:
                pass
    return out


def classify_intake_query(query: str, user_id: str = "") -> Dict[str, Any]:
    """Classify consumer intake — uses corrections + keyword rules."""
    ensure_saas_schema()
    q = (query or "").strip()
    if not q:
        return {"intent": "GENERAL", "confidence": 0.0, "parameters": {}}

    if user_id:
        conn = connect_data_db()
        row = conn.execute(
            """
            SELECT corrected_intent FROM crm_intent_corrections
            WHERE user_id = ? AND raw_sig = ?
            """,
            (str(user_id), _sig(q)),
        ).fetchone()
        conn.close()
        if row:
            return {
                "intent": row[0],
                "confidence": 0.95,
                "parameters": _extract_params(q),
                "source": "learned_correction",
            }

    scores: Dict[str, int] = {}
    for intent, pat, _meta in _INTENT_RULES:
        if pat.search(q):
            scores[intent] = scores.get(intent, 0) + len(pat.findall(q)) + 1
    if re.search(r"\b(vendor|company|payment|down payment|invoice|contract)\b", q, re.I):
        scores["COMMERCIAL_LITIGATION"] = scores.get("COMMERCIAL_LITIGATION", 0) + 2
    if re.search(r"\b(cheating|fraud)\b", q, re.I) and not re.search(
        r"\b(fir|arrest|murder|bail)\b", q, re.I
    ):
        scores["COMMERCIAL_LITIGATION"] = scores.get("COMMERCIAL_LITIGATION", 0) + 1
    if scores:
        best = max(scores, key=scores.get)
        conf = min(0.92, 0.55 + 0.1 * scores[best])
        return {
            "intent": best,
            "confidence": round(conf, 2),
            "parameters": _extract_params(q),
            "source": "rules",
        }
    return {
        "intent": "GENERAL_CONSULTATION",
        "confidence": 0.45,
        "parameters": _extract_params(q),
        "source": "fallback",
    }


def draft_follow_up_email(
    prospect_name: str,
    intent: str,
    params: Dict[str, Any],
) -> str:
    """Professional consultation invitation."""
    name = prospect_name or "Sir/Madam"
    venue = params.get("venue", "your jurisdiction")
    intent_blurbs = {
        "CRIMINAL_DEFENSE": (
            "We understand you may require urgent criminal defense assistance. "
            "Our team handles bail, FIR response, and trial strategy under IPC/BNS/BNSS."
        ),
        "COMMERCIAL_LITIGATION": (
            "We note a potential commercial or contractual dispute. "
            "We can advise on recovery, breach notices, and court strategy under Indian contract law."
        ),
        "FAMILY_LAW": (
            "We handle matrimonial and family matters including maintenance, custody, "
            "and protective orders with sensitivity and procedural rigor."
        ),
        "PROPERTY_REAL_ESTATE": (
            "We assist with property disputes, title diligence, eviction, and "
            "developer/tenant conflicts."
        ),
        "EMPLOYMENT_LABOUR": (
            "We advise on wrongful termination, wage disputes, and compliance "
            "under applicable labour statutes."
        ),
    }
    blurb = intent_blurbs.get(
        intent,
        "We would be pleased to understand your matter and outline next steps under Indian law.",
    )
    amt = params.get("amount_in_dispute")
    amt_line = f"\n\nWe note the disputed amount referenced as: {amt}." if amt else ""
    return (
        f"Dear {name},\n\n"
        f"Thank you for contacting our firm.{amt_line}\n\n"
        f"{blurb}\n\n"
        f"Please share any documents (agreement, notice, FIR, correspondence) and "
        f"confirm a convenient time for a confidential consultation.\n\n"
        f"Regards,\nLegalEase Practice Team"
    )


def create_lead(
    user_id: str,
    *,
    prospect_name: str,
    contact_email: str,
    raw_intake_query: str,
    contact_phone: str = "",
    assigned_attorney_id: str = "",
) -> Dict[str, Any]:
    ensure_saas_schema()
    _migrate_crm_org_scope()
    classification = analyze_intake_query(raw_intake_query, user_id)
    org_id = get_primary_org_id(str(user_id))
    lid = str(uuid.uuid4())
    now = _utc()
    follow_up = draft_follow_up_email(
        prospect_name,
        classification["intent"],
        classification.get("parameters") or {},
    )
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO crm_leads
        (lead_id, user_id, org_id, prospect_name, contact_email, contact_phone,
         raw_intake_query, calculated_intent, extracted_params_json,
         pipeline_stage, assigned_attorney_id, follow_up_draft, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW_INQUIRY', ?, ?, ?, ?)
        """,
        (
            lid,
            str(user_id),
            org_id,
            prospect_name.strip(),
            contact_email.strip(),
            contact_phone.strip(),
            raw_intake_query.strip(),
            classification["intent"],
            json.dumps(
                {
                    **(classification.get("parameters") or {}),
                    "risk_score": classification.get("risk_score"),
                    "urgency": classification.get("urgency"),
                    "case_type": classification.get("case_type"),
                    "likely_sections": classification.get("likely_sections"),
                    "jurisdiction": classification.get("jurisdiction"),
                }
            ),
            assigned_attorney_id,
            follow_up,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return get_lead(user_id, lid) or {}


def get_lead(user_id: str, lead_id: str) -> Optional[Dict[str, Any]]:
    ensure_saas_schema()
    _migrate_crm_org_scope()
    scope_sql, scope_params = _crm_scope(user_id)
    conn = connect_data_db()
    row = conn.execute(
        f"""
        SELECT lead_id, prospect_name, contact_email, contact_phone, raw_intake_query,
               calculated_intent, extracted_params_json, pipeline_stage,
               assigned_attorney_id, follow_up_draft, created_at, updated_at
        FROM crm_leads WHERE lead_id = ? AND {scope_sql}
        """,
        (lead_id, *scope_params),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _lead_row(row)


def list_leads(
    user_id: str,
    *,
    stage: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    ensure_saas_schema()
    _migrate_crm_org_scope()
    scope_sql, scope_params = _crm_scope(user_id)
    conn = connect_data_db()
    q = f"""
        SELECT lead_id, prospect_name, contact_email, contact_phone, raw_intake_query,
               calculated_intent, extracted_params_json, pipeline_stage,
               assigned_attorney_id, follow_up_draft, created_at, updated_at
        FROM crm_leads WHERE {scope_sql}
    """
    params: List[Any] = list(scope_params)
    if stage:
        q += " AND pipeline_stage = ?"
        params.append(stage)
    q += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_lead_row(r) for r in rows]


def update_lead(
    user_id: str,
    lead_id: str,
    **fields: Any,
) -> Optional[Dict[str, Any]]:
    allowed = {
        "pipeline_stage",
        "calculated_intent",
        "assigned_attorney_id",
        "follow_up_draft",
        "prospect_name",
        "contact_email",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_lead(user_id, lead_id)
    updates["updated_at"] = _utc()
    sets = ", ".join(f"{k} = ?" for k in updates)
    scope_sql, scope_params = _crm_scope(user_id)
    conn = connect_data_db()
    conn.execute(
        f"UPDATE crm_leads SET {sets} WHERE lead_id = ? AND {scope_sql}",
        (*updates.values(), lead_id, *scope_params),
    )
    conn.commit()
    conn.close()
    return get_lead(user_id, lead_id)


def convert_lead_to_matter(user_id: str, lead_id: str) -> Dict[str, Any]:
    """Create a matter from an accepted lead."""
    lead = get_lead(user_id, lead_id)
    if not lead:
        return {"error": "Lead not found"}
    intent = lead.get("calculated_intent") or "GENERAL"
    params = lead.get("extracted_params") or {}
    practice = CASE_TYPE_LABELS.get(intent, "General")
    matter_name = f"{lead.get('prospect_name', 'Client')} — {practice}"
    from backend.app.core.matter_repo import add_matter_note, create_matter

    matter = create_matter(
        user_id,
        matter_name=matter_name,
        practice_area=practice,
        client_name=lead.get("prospect_name", ""),
        venue=str(params.get("venue", "")),
        status_tier="ACTIVE",
    )
    if matter:
        add_matter_note(
            user_id,
            matter["matter_id"],
            f"Converted from intake lead.\n\n{lead.get('raw_intake_query', '')}",
        )
        try:
            from backend.app.core.matter_workflow import add_timeline_event

            add_timeline_event(
                user_id,
                matter["matter_id"],
                title="Matter opened from intake CRM",
                description=lead.get("raw_intake_query", "")[:500],
                event_type="intake",
            )
        except Exception:
            pass
    update_lead(user_id, lead_id, pipeline_stage="MATTER_CREATED")
    return {"matter": matter, "lead_id": lead_id, "converted": True}


def record_intent_correction(
    user_id: str,
    raw_query: str,
    corrected_intent: str,
    *,
    original_intent: str = "",
) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO crm_intent_corrections
        (user_id, raw_sig, original_intent, corrected_intent, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, raw_sig) DO UPDATE SET
            corrected_intent = excluded.corrected_intent,
            original_intent = excluded.original_intent,
            updated_at = excluded.updated_at
        """,
        (str(user_id), _sig(raw_query), original_intent, corrected_intent, _utc()),
    )
    conn.commit()
    conn.close()
    return {"recorded": True, "corrected_intent": corrected_intent}


def _lead_row(row) -> Dict[str, Any]:
    params = {}
    try:
        params = json.loads(row[6] or "{}")
    except json.JSONDecodeError:
        pass
    return {
        "lead_id": row[0],
        "prospect_name": row[1],
        "contact_email": row[2],
        "contact_phone": row[3],
        "raw_intake_query": row[4],
        "calculated_intent": row[5],
        "extracted_params": params,
        "pipeline_stage": row[7],
        "assigned_attorney_id": row[8],
        "follow_up_draft": row[9],
        "created_at": row[10],
        "updated_at": row[11],
    }
