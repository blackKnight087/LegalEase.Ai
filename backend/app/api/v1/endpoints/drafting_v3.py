"""Drafting Studio V3 API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.drafting_clause_intel import clause_recommendations_v3, legal_review_report
from ....core.drafting_v3 import (
    V3_WORKFLOW_STATUSES,
    autofill_document,
    compare_versions_v3,
    copilot_command,
    create_document_pack,
    document_insights,
    ensure_workspace_v3_schema,
    list_audit_trail,
    list_v3_templates,
    matter_variables,
    render_v3_template,
    resolve_comment,
    transition_status,
    workspace_search,
)
from ....core.drafting_v3 import export_document_v3
from ....core.drafting_workspace import create_document, get_document, update_document

router = APIRouter(tags=["drafting-v3"])


class TemplateRenderBody(BaseModel):
    template_id: str
    matter_id: str = ""
    variables: Dict[str, str] = Field(default_factory=dict)


class StatusTransitionBody(BaseModel):
    status: str


class CopilotBody(BaseModel):
    command: str
    selection: str = ""
    instruction: str = ""


class PackBody(BaseModel):
    draft_ids: List[str]
    format: str = "zip"


class ExportV3Body(BaseModel):
    format: str = "pdf"
    watermark: str = ""
    signature_blocks: bool = False


class CreateFromTemplateBody(BaseModel):
    template_id: str
    matter_id: str = ""
    title: str = ""
    variables: Dict[str, str] = Field(default_factory=dict)


@router.get("/workspace/v3/workflow")
def v3_workflow(user: Dict[str, Any] = Depends(get_current_user)):
    _ = user
    ensure_workspace_v3_schema()
    return {"statuses": list(V3_WORKFLOW_STATUSES)}


@router.get("/workspace/v3/templates")
def v3_templates(user: Dict[str, Any] = Depends(get_current_user)):
    return {"templates": list_v3_templates(user["id"])}


@router.post("/workspace/v3/templates/render")
def v3_render_template(body: TemplateRenderBody, user: Dict[str, Any] = Depends(get_current_user)):
    return render_v3_template(
        user["id"],
        body.template_id,
        matter_id=body.matter_id,
        extra_vars=body.variables,
    )


@router.post("/workspace/v3/templates/create-document")
def v3_create_from_template(
    body: CreateFromTemplateBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    out = render_v3_template(
        user["id"],
        body.template_id,
        matter_id=body.matter_id,
        extra_vars=body.variables,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    title = body.title or out.get("template_name") or "New document"
    doc = create_document(
        user["id"],
        title=title,
        document_type=body.template_id,
        content=out.get("rendered") or "",
        matter_id=body.matter_id,
        content_format="markdown",
    )
    return {"document": doc, "variables_used": out.get("variables_used")}


@router.get("/workspace/v3/matters/{matter_id}/variables")
def v3_matter_vars(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return {"variables": matter_variables(user["id"], matter_id)}


@router.post("/workspace/documents/{draft_id}/autofill")
def v3_autofill(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    out = autofill_document(user["id"], draft_id)
    if not out:
        raise HTTPException(404, "Document not found")
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.get("/workspace/documents/{draft_id}/insights")
def v3_insights(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = get_document(user["id"], draft_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return document_insights(
        user["id"],
        doc["content"],
        document_type=doc.get("document_type") or "contract",
        status=doc.get("status") or "draft",
        version_count=int(doc.get("version_count") or 1),
    )


@router.get("/workspace/documents/{draft_id}/clause-intel")
def v3_clause_intel(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = get_document(user["id"], draft_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return clause_recommendations_v3(
        user["id"],
        doc["content"],
        document_type=doc.get("document_type") or "contract",
    )


@router.post("/workspace/documents/{draft_id}/status")
def v3_status(draft_id: str, body: StatusTransitionBody, user: Dict[str, Any] = Depends(get_current_user)):
    out = transition_status(user["id"], draft_id, body.status)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.get("/workspace/v3/search")
def v3_search(q: str = Query(""), user: Dict[str, Any] = Depends(get_current_user)):
    return workspace_search(user["id"], q)


@router.get("/workspace/documents/{draft_id}/compare-v3")
def v3_compare(
    draft_id: str,
    version_a: int = Query(...),
    version_b: int = Query(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    out = compare_versions_v3(user["id"], draft_id, version_a, version_b)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/export-v3")
def v3_export(
    draft_id: str,
    body: ExportV3Body,
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        data, filename, media = export_document_v3(
            user["id"],
            draft_id,
            body.format,
            watermark=body.watermark,
            signature_blocks=body.signature_blocks,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/workspace/v3/pack")
def v3_pack(body: PackBody, user: Dict[str, Any] = Depends(get_current_user)):
    try:
        data, filename, media = create_document_pack(
            user["id"],
            body.draft_ids,
            pack_format=body.format,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/workspace/documents/{draft_id}/copilot")
def v3_copilot(draft_id: str, body: CopilotBody, user: Dict[str, Any] = Depends(get_current_user)):
    out = copilot_command(
        user["id"],
        draft_id,
        body.command,
        selection=body.selection,
        instruction=body.instruction,
    )
    if out.get("error"):
        raise HTTPException(404, out["error"])
    if not (out.get("result") or "").strip() and body.command.strip().lower() not in (
        "execution_block",
        "signature_block",
    ):
        raise HTTPException(
            503,
            "AI copilot is unavailable. Check LLM settings or try again.",
        )
    return out


@router.get("/workspace/documents/{draft_id}/audit")
def v3_audit(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return {"events": list_audit_trail(user["id"], draft_id)}


@router.post("/workspace/documents/{draft_id}/comments/{comment_id}/resolve")
def v3_resolve_comment(
    draft_id: str,
    comment_id: str,
    resolved: bool = Query(True),
    user: Dict[str, Any] = Depends(get_current_user),
):
    out = resolve_comment(user["id"], draft_id, comment_id, resolved=resolved)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.patch("/workspace/documents/{draft_id}/content")
def v3_save_content(
    draft_id: str,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Save editor content (html or markdown) without forcing new version every keystroke — use change_summary."""
    doc = update_document(
        user["id"],
        draft_id,
        content=body.get("content"),
        content_format=body.get("content_format", "html"),
        matter_id=body.get("matter_id"),
        title=body.get("title"),
        status=body.get("status"),
        change_summary=body.get("change_summary", "Edited"),
    )
    if not doc:
        raise HTTPException(404, "Document not found")
    from ....core.platform_integrations import log_drafting_billing_session

    summary = body.get("change_summary", "Edited")
    billing = log_drafting_billing_session(user["id"], draft_id, change_summary=summary)
    return {"document": doc, "billing": billing}


class RedlineRequest(BaseModel):
    document: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=3)


class RedlineFeedbackRequest(BaseModel):
    instruction: str
    before: str
    after: str
    accepted: bool = True


@router.post("/redline")
def drafting_redline(
    body: RedlineRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from document_services.redline_engine import apply_redline_instruction

    out = apply_redline_instruction(
        body.document, body.instruction, user_id=str(user["id"])
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/redline/feedback")
def redline_feedback(
    body: RedlineFeedbackRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from document_services.redline_engine import record_redline_feedback

    return record_redline_feedback(
        str(user["id"]),
        body.instruction,
        body.before,
        body.after,
        body.accepted,
    )
