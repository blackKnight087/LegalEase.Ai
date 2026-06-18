"""CRM 2.0 — extended lead operations, documents, interactions."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.crm_audit import log_crm_audit
from backend.app.core.crm_schema import (
    PIPELINE_STAGES,
    ensure_crm_v2_schema,
    lead_select_columns,
    normalize_stage,
)
from backend.app.core.crm_service import (
    CASE_TYPE_LABELS,
    _crm_scope,
    _migrate_crm_org_scope,
    analyze_intake_query,
    draft_follow_up_email,
)
from backend.app.core.database import connect_data_db
from backend.app.core.intake_intelligence import run_full_intake_analysis
from backend.app.core.org_service import get_primary_org_id
from backend.app.core.saas_schema import ensure_saas_schema

ROOT = Path(__file__).resolve().parents[3]
CRM_UPLOAD_DIR = ROOT / "Data" / "crm_uploads"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_lead_row(row) -> Dict[str, Any]:
    cols = lead_select_columns().replace("\n", " ").split(",")
    # fixed order from lead_select_columns
    keys = [c.strip() for c in cols]
    d = {keys[i]: row[i] for i in range(min(len(keys), len(row)))}
    params = {}
    try:
        params = json.loads(d.get("extracted_params_json") or "{}")
    except json.JSONDecodeError:
        pass
    analysis = {}
    try:
        analysis = json.loads(d.get("analysis_json") or "{}")
    except json.JSONDecodeError:
        pass
    return {
        "lead_id": d.get("lead_id"),
        "user_id": d.get("user_id"),
        "org_id": d.get("org_id"),
        "prospect_name": d.get("prospect_name"),
        "contact_email": d.get("contact_email"),
        "contact_phone": d.get("contact_phone"),
        "address": d.get("address") or "",
        "city": d.get("city") or "",
        "state": d.get("state") or "",
        "preferred_contact": d.get("preferred_contact") or "",
        "preferred_language": d.get("preferred_language") or "",
        "referral_source": d.get("referral_source") or "",
        "raw_intake_query": d.get("raw_intake_query"),
        "calculated_intent": d.get("calculated_intent"),
        "extracted_params": params,
        "pipeline_stage": normalize_stage(d.get("pipeline_stage") or ""),
        "assigned_attorney_id": d.get("assigned_attorney_id") or "",
        "assigned_lawyer_id": d.get("assigned_lawyer_id") or "",
        "follow_up_draft": d.get("follow_up_draft") or "",
        "lead_score": int(d.get("lead_score") or 0),
        "lead_score_band": d.get("lead_score_band") or "",
        "case_strength": d.get("case_strength") or "",
        "rejection_reason": d.get("rejection_reason") or "",
        "analysis": analysis,
        "analysis_json": analysis,
        "analysis_version": int(d.get("analysis_version") or 1),
        "last_analyzed_at": d.get("last_analyzed_at") or "",
        "matter_id": d.get("matter_id") or "",
        "archived_at": d.get("archived_at") or "",
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
        "case_type": analysis.get("classification", {}).get("primary")
        or CASE_TYPE_LABELS.get(d.get("calculated_intent") or "", "General"),
        "urgency": params.get("urgency") or analysis.get("legacy", {}).get("urgency"),
        "risk_score": params.get("risk_score") or analysis.get("legacy", {}).get("risk_score"),
    }


def _lead_accessible(user_id: str, lead_id: str) -> bool:
    if not user_id or not lead_id:
        return True
    _migrate_crm_org_scope()
    scope_sql, scope_params = _crm_scope(user_id)
    conn = connect_data_db()
    row = conn.execute(
        f"SELECT 1 FROM crm_leads WHERE lead_id = ? AND {scope_sql}",
        (lead_id, *scope_params),
    ).fetchone()
    conn.close()
    return row is not None


def list_leads_full(user_id: str, *, stage: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    ensure_saas_schema()
    ensure_crm_v2_schema()
    _migrate_crm_org_scope()
    scope_sql, scope_params = _crm_scope(user_id)
    conn = connect_data_db()
    q = f"SELECT {lead_select_columns()} FROM crm_leads WHERE {scope_sql}"
    params: List[Any] = list(scope_params)
    if stage:
        ns = normalize_stage(stage)
        _stage_aliases: Dict[str, List[str]] = {
            "NEW_INQUIRY": ["NEW_INTAKE"],
            "AI_REVIEW": ["AI_REVIEWED"],
            "DOCUMENTS_REQUESTED": ["PENDING_DOCS", "DOCUMENTS_PENDING"],
            "QUALIFIED": ["ACCEPTED"],
            "MATTER_CREATED": ["CONVERTED_TO_MATTER"],
            "CLOSED_LOST": ["REJECTED"],
            "CLOSED_WON": ["CLOSED"],
        }
        aliases = _stage_aliases.get(ns, [])
        if aliases:
            placeholders = " OR ".join(["pipeline_stage = ?"] * (1 + len(aliases)))
            q += f" AND ({placeholders})"
            params.extend([ns, *aliases])
        else:
            q += " AND pipeline_stage = ?"
            params.append(ns)
    q += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_parse_lead_row(r) for r in rows]


def get_lead_full(user_id: str, lead_id: str) -> Optional[Dict[str, Any]]:
    ensure_crm_v2_schema()
    _migrate_crm_org_scope()
    scope_sql, scope_params = _crm_scope(user_id)
    conn = connect_data_db()
    row = conn.execute(
        f"SELECT {lead_select_columns()} FROM crm_leads WHERE lead_id = ? AND {scope_sql}",
        (lead_id, *scope_params),
    ).fetchone()
    conn.close()
    if not row:
        return None
    lead = _parse_lead_row(row)
    lead["documents"] = _list_lead_documents_raw(lead_id)
    lead["interactions"] = _list_interactions_raw(lead_id)
    lead["entities"] = list_lead_entities(lead_id)
    return lead


def create_lead_extended(
    user_id: str,
    *,
    prospect_name: str,
    contact_email: str,
    raw_intake_query: str,
    contact_phone: str = "",
    address: str = "",
    city: str = "",
    state: str = "",
    preferred_contact: str = "",
    preferred_language: str = "",
    referral_source: str = "",
    assigned_lawyer_id: str = "",
    run_analysis: bool = True,
) -> Dict[str, Any]:
    ensure_crm_v2_schema()
    _migrate_crm_org_scope()
    org_id = get_primary_org_id(str(user_id))
    lid = str(uuid.uuid4())
    now = _utc()

    analysis: Dict[str, Any] = {}
    classification: Dict[str, Any] = {}
    if run_analysis:
        analysis = run_full_intake_analysis(
            raw_intake_query,
            user_id,
            prospect_name=prospect_name,
        )
        classification = analysis.get("legacy") or analyze_intake_query(raw_intake_query, user_id)
    else:
        classification = analyze_intake_query(raw_intake_query, user_id)

    intent = classification.get("intent") or "GENERAL"
    score = analysis.get("lead_score") or {}
    follow_up = draft_follow_up_email(
        prospect_name,
        intent,
        classification.get("parameters") or {},
    )

    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO crm_leads (
            lead_id, user_id, org_id, prospect_name, contact_email, contact_phone,
            address, city, state, preferred_contact, preferred_language, referral_source,
            raw_intake_query, calculated_intent, extracted_params_json, pipeline_stage,
            assigned_attorney_id, assigned_lawyer_id, follow_up_draft,
            lead_score, lead_score_band, case_strength, rejection_reason,
            analysis_json, analysis_version, last_analyzed_at,
            matter_id, archived_at, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            lid,
            str(user_id),
            org_id,
            prospect_name.strip(),
            contact_email.strip(),
            contact_phone.strip(),
            address.strip(),
            city.strip(),
            state.strip(),
            preferred_contact.strip(),
            preferred_language.strip(),
            referral_source.strip(),
            raw_intake_query.strip(),
            intent,
            json.dumps(classification.get("parameters") or {}),
            "NEW_INQUIRY",
            "",
            assigned_lawyer_id,
            follow_up,
            int(score.get("total") or 0),
            score.get("band") or "",
            (analysis.get("case_strength") or {}).get("rating", ""),
            "",
            json.dumps(analysis),
            1,
            now if analysis else "",
            "",
            "",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()

    if run_analysis and analysis:
        _persist_lead_entities(lid, analysis.get("entities") or [])
        transition_stage(user_id, lid, "AI_REVIEW", note="Auto after intake analysis")

    log_crm_audit(lid, user_id, "lead_created", prospect_name)
    return get_lead_full(user_id, lid) or {}


def update_lead_extended(user_id: str, lead_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    if "extracted_params" in fields and isinstance(fields["extracted_params"], dict):
        fields["extracted_params_json"] = json.dumps(fields.pop("extracted_params"))
    allowed = {
        "pipeline_stage",
        "calculated_intent",
        "extracted_params_json",
        "assigned_attorney_id",
        "assigned_lawyer_id",
        "follow_up_draft",
        "prospect_name",
        "contact_email",
        "contact_phone",
        "address",
        "city",
        "state",
        "preferred_contact",
        "preferred_language",
        "referral_source",
        "rejection_reason",
        "archived_at",
        "matter_id",
        "lead_score",
        "lead_score_band",
        "case_strength",
        "analysis_json",
        "last_analyzed_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "pipeline_stage" in updates:
        updates["pipeline_stage"] = normalize_stage(str(updates["pipeline_stage"]))
    if "analysis_json" in updates and isinstance(updates["analysis_json"], dict):
        updates["analysis_json"] = json.dumps(updates["analysis_json"])
    if not updates:
        return get_lead_full(user_id, lead_id)
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
    log_crm_audit(lead_id, user_id, "lead_updated", ",".join(updates.keys()))
    return get_lead_full(user_id, lead_id)


def transition_stage(
    user_id: str,
    lead_id: str,
    to_stage: str,
    *,
    note: str = "",
) -> Optional[Dict[str, Any]]:
    lead = get_lead_full(user_id, lead_id)
    if not lead:
        return None
    to_stage = normalize_stage(to_stage)
    if to_stage not in PIPELINE_STAGES:
        raise ValueError(f"Invalid stage: {to_stage}")
    from_stage = normalize_stage(str(lead.get("pipeline_stage") or ""))
    if from_stage == to_stage:
        if note:
            add_interaction(user_id, lead_id, "consultation", title="Consultation updated", body=note)
        return get_lead_full(user_id, lead_id)
    ensure_crm_v2_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO crm_stage_history (lead_id, from_stage, to_stage, user_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (lead_id, from_stage, to_stage, str(user_id), _utc()),
    )
    conn.commit()
    conn.close()
    update_lead_extended(user_id, lead_id, pipeline_stage=to_stage)
    if note:
        add_interaction(user_id, lead_id, "status_change", title=f"Stage → {to_stage}", body=note)
    log_crm_audit(lead_id, user_id, "stage_change", f"{from_stage} → {to_stage}")
    return get_lead_full(user_id, lead_id)


def run_lead_analysis(user_id: str, lead_id: str) -> Optional[Dict[str, Any]]:
    lead = get_lead_full(user_id, lead_id)
    if not lead:
        return None
    doc_texts = [d.get("ocr_text") or "" for d in _list_lead_documents_raw(lead_id)]
    analysis = run_full_intake_analysis(
        lead.get("raw_intake_query") or "",
        user_id,
        prospect_name=lead.get("prospect_name") or "Client",
        doc_texts=doc_texts,
    )
    score = analysis.get("lead_score") or {}
    legacy = analysis.get("legacy") or {}
    update_lead_extended(
        user_id,
        lead_id,
        analysis_json=analysis,
        calculated_intent=legacy.get("intent") or lead.get("calculated_intent"),
        extracted_params=legacy.get("parameters") or lead.get("extracted_params") or {},
        lead_score=int(score.get("total") or 0),
        lead_score_band=score.get("band") or "",
        case_strength=(analysis.get("case_strength") or {}).get("rating", ""),
        last_analyzed_at=_utc(),
    )
    _persist_lead_entities(lead_id, analysis.get("entities") or [])
    if normalize_stage(lead.get("pipeline_stage")) == "NEW_INQUIRY":
        transition_stage(user_id, lead_id, "AI_REVIEW", note="Analysis completed")
    log_crm_audit(lead_id, user_id, "analysis_run", "")
    return get_lead_full(user_id, lead_id)


def _persist_lead_entities(lead_id: str, entities: List[Dict[str, Any]]) -> None:
    ensure_crm_v2_schema()
    conn = connect_data_db()
    conn.execute("DELETE FROM crm_lead_entities WHERE lead_id = ?", (lead_id,))
    now = _utc()
    seen: set = set()
    for ent in entities:
        label = (ent.get("label") or "").strip()
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        conn.execute(
            """
            INSERT INTO crm_lead_entities
            (entity_id, lead_id, entity_type, label, role_label, confidence, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                lead_id,
                ent.get("type") or "person",
                label,
                ent.get("role") or "",
                float(ent.get("confidence") or 0.8),
                "{}",
                now,
            ),
        )
    conn.commit()
    conn.close()


def list_lead_entities(lead_id: str) -> List[Dict[str, Any]]:
    ensure_crm_v2_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT entity_id, entity_type, label, role_label, confidence, metadata_json, created_at
        FROM crm_lead_entities WHERE lead_id = ? ORDER BY entity_type, label
        """,
        (lead_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "entity_id": r[0],
            "entity_type": r[1],
            "label": r[2],
            "role_label": r[3],
            "confidence": r[4],
            "created_at": r[6],
        }
        for r in rows
    ]


def add_interaction(
    user_id: str,
    lead_id: str,
    interaction_type: str,
    *,
    title: str = "",
    body: str = "",
) -> Dict[str, Any]:
    ensure_crm_v2_schema()
    iid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO crm_lead_interactions
        (interaction_id, lead_id, user_id, interaction_type, title, body, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, '{}', ?)
        """,
        (iid, lead_id, str(user_id), interaction_type, title, body, now),
    )
    conn.commit()
    conn.close()
    return {"interaction_id": iid, "created_at": now}


def _list_interactions_raw(lead_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    ensure_crm_v2_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT interaction_id, user_id, interaction_type, title, body, created_at
        FROM crm_lead_interactions WHERE lead_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (lead_id, limit),
    ).fetchall()
    conn.close()
    return [
        {
            "interaction_id": r[0],
            "user_id": r[1],
            "interaction_type": r[2],
            "title": r[3],
            "body": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def list_interactions(lead_id: str, user_id: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    if user_id and not _lead_accessible(user_id, lead_id):
        return []
    return _list_interactions_raw(lead_id, limit)


def save_lead_document(
    user_id: str,
    lead_id: str,
    filename: str,
    content: bytes,
    *,
    mime_type: str = "",
    doc_kind: str = "document",
    ocr_text: str = "",
) -> Dict[str, Any]:
    ensure_crm_v2_schema()
    lead = get_lead_full(user_id, lead_id)
    if not lead:
        raise ValueError("Lead not found")
    CRM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]", "_", filename)[:120]
    doc_id = str(uuid.uuid4())
    path = CRM_UPLOAD_DIR / f"{lead_id}_{doc_id}_{safe}"
    path.write_bytes(content)
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO crm_lead_documents
        (doc_id, lead_id, org_id, filename, saved_path, mime_type, doc_kind, ocr_text, indexed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            doc_id,
            lead_id,
            lead.get("org_id") or "",
            filename,
            str(path),
            mime_type,
            doc_kind,
            ocr_text[:50000],
            now,
        ),
    )
    conn.commit()
    conn.close()
    log_crm_audit(lead_id, user_id, "document_upload", filename)
    return {"doc_id": doc_id, "filename": filename, "saved_path": str(path)}


def _list_lead_documents_raw(lead_id: str) -> List[Dict[str, Any]]:
    ensure_crm_v2_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT doc_id, filename, mime_type, doc_kind, ocr_text, created_at
        FROM crm_lead_documents WHERE lead_id = ? ORDER BY created_at DESC
        """,
        (lead_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "doc_id": r[0],
            "filename": r[1],
            "mime_type": r[2],
            "doc_kind": r[3],
            "ocr_text": (r[4] or "")[:500],
            "created_at": r[5],
        }
        for r in rows
    ]


def list_lead_documents(lead_id: str, user_id: str = "") -> List[Dict[str, Any]]:
    if user_id and not _lead_accessible(user_id, lead_id):
        return []
    return _list_lead_documents_raw(lead_id)
