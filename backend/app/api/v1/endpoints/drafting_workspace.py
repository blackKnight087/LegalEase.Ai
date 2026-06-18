"""Drafting Studio V2 — documents, versions, export, AI generation."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.drafting_clause_intel import legal_review_report
from ....core.drafting_workspace import (
    DOCUMENT_TYPES,
    WORKFLOW_STATUSES,
    add_comment,
    compare_versions,
    create_document,
    dashboard,
    delete_document,
    export_document,
    generate_ai_draft,
    get_document,
    list_comments,
    list_documents,
    list_versions,
    restore_version,
    update_document,
)
from ....core.drafting_workspace import _polish_draft as ai_assist_polish

router = APIRouter(tags=["drafting-v2"])


class DocumentCreate(BaseModel):
    title: str = "Untitled document"
    document_type: str = "custom"
    content: str = ""
    content_format: str = "markdown"
    matter_id: str = ""
    jurisdiction: str = ""
    objectives: str = ""
    instructions: str = ""
    parties: Dict[str, str] = Field(default_factory=dict)
    status: str = "draft"


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    matter_id: Optional[str] = None
    pinned: Optional[bool] = None
    jurisdiction: Optional[str] = None
    objectives: Optional[str] = None
    instructions: Optional[str] = None
    parties: Optional[Dict[str, str]] = None
    change_summary: str = "Edited"


class AiGenerateBody(BaseModel):
    document_type: str = "custom"
    parties: Dict[str, str] = Field(default_factory=dict)
    facts: str = ""
    jurisdiction: str = ""
    objectives: str = ""
    instructions: str = ""
    use_polish: bool = True


class AiAssistBody(BaseModel):
    action: str = "rewrite"
    selection: str = ""
    instruction: str = ""


class CommentBody(BaseModel):
    body: str
    author_name: str = ""


class ExportBody(BaseModel):
    format: str = "pdf"


@router.get("/workspace/dashboard")
def ws_dashboard(user: Dict[str, Any] = Depends(get_current_user)):
    return dashboard(user["id"])


@router.get("/workspace/document-types")
def ws_document_types(user: Dict[str, Any] = Depends(get_current_user)):
    _ = user
    return {"types": DOCUMENT_TYPES, "workflow_statuses": list(WORKFLOW_STATUSES)}


@router.get("/workspace/documents")
def ws_list_documents(
    q: str = Query(""),
    status: str = Query(""),
    document_type: str = Query(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    return {
        "documents": list_documents(
            user["id"], q=q, status=status, document_type=document_type
        )
    }


@router.post("/workspace/documents")
def ws_create_document(
    body: DocumentCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    doc = create_document(
        user["id"],
        title=body.title,
        document_type=body.document_type,
        content=body.content,
        content_format=body.content_format,
        matter_id=body.matter_id,
        jurisdiction=body.jurisdiction,
        objectives=body.objectives,
        instructions=body.instructions,
        parties=body.parties,
        status=body.status,
    )
    return {"document": doc}


@router.get("/workspace/documents/{draft_id}")
def ws_get_document(
    draft_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    doc = get_document(user["id"], draft_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"document": doc, "versions": list_versions(user["id"], draft_id), "comments": list_comments(user["id"], draft_id)}


@router.patch("/workspace/documents/{draft_id}")
def ws_update_document(
    draft_id: str,
    body: DocumentUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    doc = update_document(
        user["id"],
        draft_id,
        title=body.title,
        content=body.content,
        status=body.status,
        matter_id=body.matter_id,
        pinned=body.pinned,
        jurisdiction=body.jurisdiction,
        objectives=body.objectives,
        instructions=body.instructions,
        parties=body.parties,
        change_summary=body.change_summary,
    )
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"document": doc}


@router.delete("/workspace/documents/{draft_id}")
def ws_delete_document(
    draft_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if not delete_document(user["id"], draft_id):
        raise HTTPException(404, "Document not found")
    return {"ok": True}


@router.get("/workspace/documents/{draft_id}/versions")
def ws_versions(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return {"versions": list_versions(user["id"], draft_id)}


@router.get("/workspace/documents/{draft_id}/compare")
def ws_compare(
    draft_id: str,
    version_a: int = Query(...),
    version_b: int = Query(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    out = compare_versions(user["id"], draft_id, version_a, version_b)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/restore/{version_number}")
def ws_restore(
    draft_id: str,
    version_number: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    doc = restore_version(user["id"], draft_id, version_number)
    if not doc:
        raise HTTPException(404, "Version not found")
    return {"document": doc}


@router.post("/workspace/documents/{draft_id}/export")
def ws_export(
    draft_id: str,
    body: ExportBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        data, filename, media = export_document(user["id"], draft_id, body.format)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/workspace/documents/{draft_id}/review")
def ws_review(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = get_document(user["id"], draft_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return legal_review_report(doc["content"], document_type=doc.get("document_type") or "contract")


@router.post("/workspace/documents/{draft_id}/comments")
def ws_comment(
    draft_id: str,
    body: CommentBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    out = add_comment(user["id"], draft_id, body.body, author_name=body.author_name)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/ai/generate")
def ws_ai_generate(
    body: AiGenerateBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    return generate_ai_draft(
        user["id"],
        document_type=body.document_type,
        parties=body.parties,
        facts=body.facts,
        jurisdiction=body.jurisdiction,
        objectives=body.objectives,
        instructions=body.instructions,
        use_polish=body.use_polish,
    )


@router.post("/workspace/documents/{draft_id}/ai/assist")
def ws_ai_assist(
    draft_id: str,
    body: AiAssistBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    doc = get_document(user["id"], draft_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    text = body.selection.strip() or doc["content"]
    action = (body.action or "rewrite").lower()
    instr = body.instruction.strip() or action
    prompts = {
        "rewrite": f"Rewrite in formal Indian legal language:\n{text[:8000]}",
        "summarize": f"Summarize concisely:\n{text[:8000]}",
        "expand": f"Expand with professional legal detail:\n{text[:6000]}",
        "shorten": f"Shorten while preserving legal meaning:\n{text[:8000]}",
        "formal": f"Convert to formal legal drafting style:\n{text[:8000]}",
        "explain": f"Explain this clause in plain English for a client:\n{text[:4000]}",
    }
    prompt = prompts.get(action, f"{instr}\n\n{text[:8000]}")
    result = ai_assist_polish(user["id"], prompt, doc.get("title") or "Document", instr)
    return {"result": result, "action": action}
