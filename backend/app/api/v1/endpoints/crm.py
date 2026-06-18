"""Intake CRM 2.0 API."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.crm_analytics import crm_analytics_report, crm_dashboard, crm_kanban
from ....core.crm_audit import list_crm_audit
from ....core.crm_conversion import (
    archive_lead,
    convert_lead_to_matter_full,
    preview_conversion,
    reject_lead,
)
from ....core.crm_rbac import crm_permissions, require_crm_perm
from ....core.crm_schema import PIPELINE_STAGES, STAGE_EMPTY_HINTS, STAGE_LABELS, ensure_crm_v2_schema
from ....core.crm_service import analyze_intake_query, draft_follow_up_email, record_intent_correction
from ....core.crm_v2_service import (
    add_interaction,
    create_lead_extended,
    get_lead_full,
    list_interactions,
    list_lead_documents,
    run_lead_analysis,
    save_lead_document,
    transition_stage,
    update_lead_extended,
)
from ....core.saas_schema import ensure_saas_schema

router = APIRouter(tags=["crm"])

_CRM_RESERVED_PATHS = frozenset(
    {
        "dashboard",
        "kanban",
        "analytics",
        "permissions",
        "assistant",
        "classify",
        "pipeline-stages",
    }
)


class LeadCreate(BaseModel):
    prospect_name: str = Field(..., min_length=2)
    contact_email: str = Field(..., min_length=5)
    raw_intake_query: str = Field(..., min_length=10)
    contact_phone: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    preferred_contact: str = ""
    preferred_language: str = ""
    referral_source: str = ""
    assigned_lawyer_id: str = ""


class LeadUpdate(BaseModel):
    pipeline_stage: Optional[str] = None
    prospect_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    preferred_contact: Optional[str] = None
    preferred_language: Optional[str] = None
    referral_source: Optional[str] = None
    assigned_lawyer_id: Optional[str] = None
    follow_up_draft: Optional[str] = None


class StageUpdate(BaseModel):
    stage: str
    note: str = ""


class IntakeClassify(BaseModel):
    query: str = Field(..., min_length=5)


class IntentCorrection(BaseModel):
    raw_query: str
    corrected_intent: str
    original_intent: str = ""


class InteractionCreate(BaseModel):
    interaction_type: str = "note"
    title: str = ""
    body: str = ""


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=3)


class AssistantRequest(BaseModel):
    lead_id: str
    action: str = Field(..., description="summarize_lead|missing_documents|consultation_questions|convert_preview|draft_follow_up")


class FollowUpSend(BaseModel):
    template_type: str = "email"
    subject: str = ""
    body: str = ""


class FollowUpApply(BaseModel):
    template_id: str


@router.get("/permissions")
def crm_perms(user: Dict[str, Any] = Depends(get_current_user)):
    return crm_permissions(user)


@router.get("/dashboard")
def crm_dashboard_route(user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    ensure_crm_v2_schema()
    return crm_dashboard(user["id"])


@router.get("/command-center")
def crm_command_center_route(user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    from ....core.crm_command_center import crm_command_center

    return crm_command_center(user["id"])


@router.get("/kanban")
def crm_kanban_route(user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    return crm_kanban(user["id"])


@router.get("/analytics")
def crm_analytics_route(user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "analytics")
    return crm_analytics_report(user["id"])


@router.get("/pipeline-stages")
def crm_pipeline_stages(user: Dict[str, Any] = Depends(get_current_user)):
    return {"stages": PIPELINE_STAGES, "labels": STAGE_LABELS, "empty_hints": STAGE_EMPTY_HINTS}


@router.post("/classify")
def crm_classify(body: IntakeClassify, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    from backend.app.core.intake_intelligence import run_full_intake_analysis

    analysis = run_full_intake_analysis(body.query, user["id"])
    legacy = analysis.get("legacy") or {}
    return {
        **analysis,
        "intent": legacy.get("intent") or analysis.get("classification", {}).get("secondary"),
        "risk_score": legacy.get("risk_score"),
        "urgency": legacy.get("urgency"),
        "legal_analysis": legacy.get("legal_analysis") or analysis.get("executive_summary"),
        "case_type": analysis.get("classification", {}).get("primary"),
        "confidence": analysis.get("classification", {}).get("confidence"),
        "jurisdiction": (analysis.get("jurisdiction") or {}).get("city"),
        "likely_sections": [
            s
            for law in (analysis.get("applicable_laws") or [])
            for s in (law.get("sections") or [])
        ],
    }


@router.get("")
def crm_list(stage: str = "", user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    from backend.app.core.crm_v2_service import list_leads_full

    return {"leads": list_leads_full(user["id"], stage=stage)}


@router.post("")
def crm_create(body: LeadCreate, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "create")
    lead = create_lead_extended(
        user["id"],
        prospect_name=body.prospect_name,
        contact_email=body.contact_email,
        raw_intake_query=body.raw_intake_query,
        contact_phone=body.contact_phone,
        address=body.address,
        city=body.city,
        state=body.state,
        preferred_contact=body.preferred_contact,
        preferred_language=body.preferred_language,
        referral_source=body.referral_source,
        assigned_lawyer_id=body.assigned_lawyer_id,
    )
    return lead


@router.post("/assistant")
def crm_assistant(body: AssistantRequest, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    lead = get_lead_full(user["id"], body.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    analysis = lead.get("analysis") or {}
    action = body.action
    if action == "summarize_lead":
        return {"text": analysis.get("executive_summary") or lead.get("raw_intake_query", "")[:500]}
    if action == "missing_documents":
        req = analysis.get("document_readiness", {}).get("required", [])
        missing = [r["label"] for r in req if r.get("status") == "missing"]
        return {
            "missing_documents": missing,
            "readiness_percent": analysis.get("document_readiness", {}).get("percent", 0),
        }
    if action == "consultation_questions":
        return {"questions": analysis.get("consultation_questions", [])}
    if action == "convert_preview":
        return preview_conversion(user["id"], body.lead_id)
    if action == "draft_follow_up":
        intent = lead.get("calculated_intent") or "GENERAL"
        return {
            "draft": draft_follow_up_email(
                lead.get("prospect_name", "Client"),
                intent,
                lead.get("extracted_params") or {},
            )
        }
    if action == "draft_legal_notice_outline":
        laws = analysis.get("applicable_laws") or []
        sections = ", ".join(
            s for law in laws for s in (law.get("sections") or [])
        )[:200]
        outline = (
            f"DRAFT LEGAL NOTICE — {lead.get('prospect_name', 'Client')}\n\n"
            f"Subject matter: {analysis.get('classification', {}).get('primary', 'General')}\n"
            f"Relevant provisions: {sections or 'To be confirmed after document review'}\n\n"
            f"1. Facts as stated in intake\n"
            f"2. Legal grounds\n"
            f"3. Demand / relief sought\n"
            f"4. Timeline for compliance\n"
            f"5. Consequences of non-compliance\n"
        )
        return {"draft": outline, "outline": True}
    raise HTTPException(400, f"Unknown action: {action}")


@router.get("/{lead_id}")
def crm_get(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    if lead_id in _CRM_RESERVED_PATHS:
        raise HTTPException(404, "Not found")
    require_crm_perm(user, "view")
    lead = get_lead_full(user["id"], lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.patch("/{lead_id}")
def crm_patch(lead_id: str, body: LeadUpdate, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "edit")
    lead = update_lead_extended(user["id"], lead_id, **body.model_dump(exclude_none=True))
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.patch("/{lead_id}/stage")
def crm_stage(lead_id: str, body: StageUpdate, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "edit")
    try:
        lead = transition_stage(user["id"], lead_id, body.stage, note=body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.post("/{lead_id}/analyze")
def crm_analyze(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "edit")
    lead = run_lead_analysis(user["id"], lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.get("/{lead_id}/documents")
def crm_list_docs(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    return {"documents": list_lead_documents(lead_id, user["id"])}


@router.post("/{lead_id}/documents")
async def crm_upload_doc(
    lead_id: str,
    file: UploadFile = File(...),
    doc_kind: str = Form("document"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_crm_perm(user, "edit")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 25MB)")
    from ....core.crm_document_extract import extract_crm_upload_text

    fname = file.filename or "upload"
    ocr_text = extract_crm_upload_text(content, fname)
    doc = save_lead_document(
        user["id"],
        lead_id,
        fname,
        content,
        mime_type=file.content_type or "",
        doc_kind=doc_kind,
        ocr_text=ocr_text,
    )
    run_lead_analysis(user["id"], lead_id)
    return doc


@router.get("/{lead_id}/interactions")
def crm_interactions(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    return {"interactions": list_interactions(lead_id, user["id"])}


@router.post("/{lead_id}/interactions")
def crm_add_interaction(
    lead_id: str,
    body: InteractionCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if crm_permissions(user).get("notes_only"):
        if body.interaction_type != "note":
            raise HTTPException(403, "Interns may add notes only")
    else:
        require_crm_perm(user, "edit")
    return add_interaction(
        user["id"],
        lead_id,
        body.interaction_type,
        title=body.title,
        body=body.body,
    )


@router.get("/{lead_id}/audit")
def crm_audit(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    return {"audit": list_crm_audit(lead_id)}


@router.post("/{lead_id}/convert/preview")
def crm_convert_preview(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "convert")
    out = preview_conversion(user["id"], lead_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/{lead_id}/convert")
def crm_convert(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "convert")
    out = convert_lead_to_matter_full(user["id"], lead_id)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/{lead_id}/convert-to-matter")
def crm_convert_legacy(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return crm_convert(lead_id, user)


@router.post("/{lead_id}/reject")
def crm_reject(lead_id: str, body: RejectBody, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "reject")
    lead = reject_lead(user["id"], lead_id, body.reason)
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.post("/{lead_id}/archive")
def crm_archive(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "edit")
    lead = archive_lead(user["id"], lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.get("/{lead_id}/follow-up/templates")
def crm_follow_up_templates(lead_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_crm_perm(user, "view")
    lead = get_lead_full(user["id"], lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    from ....core.crm_follow_up import list_follow_up_templates

    return {"templates": list_follow_up_templates(user["id"])}


@router.post("/{lead_id}/follow-up/apply")
def crm_follow_up_apply(
    lead_id: str,
    body: FollowUpApply,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_crm_perm(user, "edit")
    lead = get_lead_full(user["id"], lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    from ....core.crm_follow_up import list_follow_up_templates, render_template

    templates = {t["template_id"]: t for t in list_follow_up_templates(user["id"])}
    tpl = templates.get(body.template_id)
    if not tpl:
        raise HTTPException(404, "Template not found")
    analysis = lead.get("analysis") or {}
    missing = [
        r["label"]
        for r in (analysis.get("document_readiness") or {}).get("required", [])
        if r.get("status") == "missing"
    ]
    ctx = {
        "prospect_name": lead.get("prospect_name", "Client"),
        "case_type": analysis.get("classification", {}).get("primary", "legal matter"),
        "missing_docs": "\n".join(f"- {m}" for m in missing) or "- (see intake notes)",
        "firm_name": "Our firm",
    }
    draft = render_template(tpl["body_template"], ctx)
    update_lead_extended(user["id"], lead_id, follow_up_draft=draft)
    return {"draft": draft, "subject": tpl.get("subject", "")}


@router.post("/{lead_id}/follow-up/send")
def crm_follow_up_send(
    lead_id: str,
    body: FollowUpSend,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_crm_perm(user, "edit")
    lead = get_lead_full(user["id"], lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    draft = body.body or lead.get("follow_up_draft") or ""
    update_lead_extended(user["id"], lead_id, follow_up_draft=draft)
    from backend.app.core.crm_audit import log_crm_audit

    log_crm_audit(lead_id, user["id"], "follow_up_sent", body.subject or "follow-up")
    add_interaction(
        user["id"],
        lead_id,
        "email",
        title=body.subject or "Follow-up sent",
        body=draft[:2000],
    )
    return {"ok": True, "draft": draft, "note": "Email delivery requires firm SMTP integration"}


@router.post("/{lead_id}/follow-up/preview")
def crm_follow_up_preview(
    lead_id: str,
    prospect_name: str = "Client",
    user: Dict[str, Any] = Depends(get_current_user),
):
    lead = get_lead_full(user["id"], lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    cls = lead.get("analysis") or analyze_intake_query(lead.get("raw_intake_query") or "", user["id"])
    intent = lead.get("calculated_intent") or cls.get("intent", "GENERAL")
    return {
        "draft": draft_follow_up_email(
            prospect_name or lead.get("prospect_name", "Client"),
            intent,
            lead.get("extracted_params") or {},
        )
    }


@router.post("/intent/correct")
def crm_intent_correct(body: IntentCorrection, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    return record_intent_correction(
        user["id"],
        body.raw_query,
        body.corrected_intent,
        original_intent=body.original_intent,
    )
