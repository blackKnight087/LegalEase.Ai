"""Drafting Studio V4 — document lifecycle API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.drafting_lifecycle import (
    acquire_lock,
    add_annexure,
    add_review_suggestion,
    assign_reviewer,
    build_court_package,
    control_center,
    create_matter_draft,
    create_precedent,
    draft_presence,
    filing_readiness,
    heartbeat_presence,
    list_annexures,
    list_draft_timeline,
    list_precedents,
    list_review_workspace,
    list_signatures,
    mark_signed,
    matter_court_bundle_automation,
    matter_drafting_hub,
    promote_draft_to_precedent,
    release_lock,
    resolve_suggestion,
    search_precedents_ai,
    set_signature_workflow,
)
from ....core.drafting_lifecycle import ensure_v4_schema
from ....core.drafting_v3 import transition_status
from ....core.drafting_workspace import get_document
from ....core.platform_integrations import (
    control_center_for_matter,
    link_draft_to_hearing,
    list_draft_links,
    log_drafting_billing_session,
    matter_drafting_overview,
    sync_draft_filed_to_litigation,
)

router = APIRouter(tags=["drafting-v4"])


class PrecedentCreate(BaseModel):
    title: str
    content: str
    document_type: str = "custom"
    matter_id: str = ""
    tags: List[str] = Field(default_factory=list)
    court: str = ""
    judge: str = ""
    practice_area: str = ""
    outcome: str = ""
    author: str = ""


class AssignBody(BaseModel):
    assignee_user_id: str
    assignee_name: str = ""
    role: str = "reviewer"
    due_date: str = ""


class AnnexureBody(BaseModel):
    label: str
    content: str = ""
    sort_order: int = 0


class SuggestionBody(BaseModel):
    body: str
    author_name: str = ""


class SignerBody(BaseModel):
    party_label: str
    role: str = "signer"
    order: int = 1


class SignersBody(BaseModel):
    signers: List[SignerBody]


class CourtPackBody(BaseModel):
    matter_id: str
    draft_ids: List[str]
    include_cover: bool = True


class MatterDraftBody(BaseModel):
    title: str = ""
    document_type: str = "custom"
    template_id: str = ""


@router.get("/workspace/v4/control-center")
def v4_control_center(
    matter_id: str = Query(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_v4_schema()
    if matter_id:
        return control_center_for_matter(user["id"], matter_id)
    from ....core.drafting_lifecycle import control_center

    return control_center(user["id"])


@router.get("/workspace/v4/matters/{matter_id}/drafting-overview")
def v4_matter_overview(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    out = matter_drafting_overview(user["id"], matter_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/workspace/v4/precedents")
def v4_list_precedents(
    q: str = Query(""),
    document_type: str = Query(""),
    practice_area: str = Query(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    return {"precedents": list_precedents(user["id"], q=q, document_type=document_type, practice_area=practice_area)}


@router.post("/workspace/v4/precedents")
def v4_create_precedent(body: PrecedentCreate, user: Dict[str, Any] = Depends(get_current_user)):
    p = create_precedent(user["id"], **body.model_dump())
    return {"precedent": p}


@router.get("/workspace/v4/precedents/search")
def v4_precedent_search(q: str = Query(...), user: Dict[str, Any] = Depends(get_current_user)):
    return search_precedents_ai(user["id"], q)


@router.post("/workspace/documents/{draft_id}/promote-precedent")
def v4_promote(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    out = promote_draft_to_precedent(user["id"], draft_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/workspace/documents/{draft_id}/filing-readiness")
def v4_filing_readiness(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    out = filing_readiness(user["id"], draft_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/workspace/documents/{draft_id}/timeline")
def v4_timeline(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return {"events": list_draft_timeline(user["id"], draft_id)}


@router.get("/workspace/documents/{draft_id}/review-workspace")
def v4_review_ws(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    out = list_review_workspace(user["id"], draft_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/assign")
def v4_assign(draft_id: str, body: AssignBody, user: Dict[str, Any] = Depends(get_current_user)):
    out = assign_reviewer(user["id"], draft_id, **body.model_dump())
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.get("/workspace/documents/{draft_id}/annexures")
def v4_annexures(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return {"annexures": list_annexures(user["id"], draft_id)}


@router.post("/workspace/documents/{draft_id}/annexures")
def v4_add_annexure(draft_id: str, body: AnnexureBody, user: Dict[str, Any] = Depends(get_current_user)):
    out = add_annexure(user["id"], draft_id, **body.model_dump())
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/suggestions")
def v4_suggestion(draft_id: str, body: SuggestionBody, user: Dict[str, Any] = Depends(get_current_user)):
    out = add_review_suggestion(user["id"], draft_id, body.body, author_name=body.author_name)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/suggestions/{suggestion_id}/resolve")
def v4_resolve_suggestion(
    draft_id: str,
    suggestion_id: str,
    accept: bool = Query(True),
    user: Dict[str, Any] = Depends(get_current_user),
):
    return resolve_suggestion(user["id"], draft_id, suggestion_id, accept)


@router.get("/workspace/documents/{draft_id}/signatures")
def v4_signatures(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return {"signers": list_signatures(user["id"], draft_id)}


@router.post("/workspace/documents/{draft_id}/signatures")
def v4_set_signers(draft_id: str, body: SignersBody, user: Dict[str, Any] = Depends(get_current_user)):
    signers = [s.model_dump() for s in body.signers]
    return set_signature_workflow(user["id"], draft_id, signers)


@router.post("/workspace/documents/{draft_id}/signatures/{signature_id}/signed")
def v4_mark_signed(
    draft_id: str,
    signature_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    return mark_signed(user["id"], draft_id, signature_id)


@router.post("/workspace/documents/{draft_id}/lock")
def v4_lock(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    name = user.get("name") or user.get("email") or "User"
    out = acquire_lock(user["id"], draft_id, user_name=name)
    if out.get("error"):
        raise HTTPException(409, out["error"])
    return out


@router.delete("/workspace/documents/{draft_id}/lock")
def v4_unlock(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return release_lock(user["id"], draft_id)


@router.get("/workspace/documents/{draft_id}/presence")
def v4_presence(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    _ = user
    return draft_presence(draft_id)


@router.post("/workspace/documents/{draft_id}/presence/heartbeat")
def v4_heartbeat(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    name = user.get("name") or user.get("email") or "User"
    return heartbeat_presence(user["id"], draft_id, user_name=name)


@router.get("/workspace/v4/matters/{matter_id}/drafting")
def v4_matter_hub(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    out = matter_drafting_hub(user["id"], matter_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/v4/matters/{matter_id}/drafts")
def v4_matter_create_draft(
    matter_id: str,
    body: MatterDraftBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    return create_matter_draft(user["id"], matter_id, **body.model_dump())


@router.post("/workspace/v4/matters/{matter_id}/court-bundle")
def v4_court_bundle(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return matter_court_bundle_automation(user["id"], matter_id)


@router.post("/workspace/v4/court-package")
def v4_court_package(body: CourtPackBody, user: Dict[str, Any] = Depends(get_current_user)):
    try:
        data, filename, media = build_court_package(
            user["id"],
            body.matter_id,
            body.draft_ids,
            include_cover=body.include_cover,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/workspace/documents/{draft_id}/transition")
def v4_transition(
    draft_id: str,
    status: str = Query(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from backend.app.core.drafting_lifecycle import log_draft_event

    out = transition_status(user["id"], draft_id, status)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    log_draft_event(user["id"], draft_id, f"status_{status}", user_name=user.get("name") or "")
    if status in ("filed", "ready_to_file"):
        lit = sync_draft_filed_to_litigation(user["id"], draft_id)
        out["litigation_sync"] = lit
    return out


class TrackChangeBody(BaseModel):
    original_text: str
    suggested_text: str
    change_type: str = "replace"
    author_name: str = ""


class PartnerNoteBody(BaseModel):
    note: str = ""


class AssignmentStatusBody(BaseModel):
    status: str


class LinkHearingBody(BaseModel):
    hearing_id: str


@router.get("/workspace/documents/{draft_id}/links")
def v4_draft_links(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return {"links": list_draft_links(user["id"], draft_id)}


@router.post("/workspace/documents/{draft_id}/link-hearing")
def v4_link_hearing(
    draft_id: str,
    body: LinkHearingBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    out = link_draft_to_hearing(user["id"], draft_id, body.hearing_id)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/sync-litigation")
def v4_sync_litigation(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    out = sync_draft_filed_to_litigation(user["id"], draft_id)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/billing-session")
def v4_billing_session(
    draft_id: str,
    force: bool = Query(False),
    user: Dict[str, Any] = Depends(get_current_user),
):
    return log_drafting_billing_session(
        user["id"], draft_id, change_summary="Manual billing", force=force
    )


# --- Enterprise drafting (track changes, TOC, precedents, approvals) ---


@router.get("/workspace/documents/{draft_id}/collaboration-hub")
def v4_collaboration_hub(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.drafting_enterprise import get_collaboration_hub

    out = get_collaboration_hub(user["id"], draft_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/workspace/documents/{draft_id}/track-changes")
def v4_list_track_changes(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.drafting_enterprise import list_track_changes

    return {"changes": list_track_changes(user["id"], draft_id)}


@router.post("/workspace/documents/{draft_id}/track-changes")
def v4_add_track_change(
    draft_id: str,
    body: TrackChangeBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.drafting_enterprise import add_track_change

    out = add_track_change(
        user["id"],
        draft_id,
        original_text=body.original_text,
        suggested_text=body.suggested_text,
        change_type=body.change_type,
        author_name=body.author_name or user.get("name") or "",
    )
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/track-changes/{change_id}/resolve")
def v4_resolve_track_change(
    draft_id: str,
    change_id: str,
    accept: bool = Query(True),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.drafting_enterprise import resolve_track_change

    out = resolve_track_change(user["id"], draft_id, change_id, accept)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/workspace/documents/{draft_id}/assignments")
def v4_list_assignments(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.drafting_enterprise import list_draft_assignments

    return {"assignments": list_draft_assignments(user["id"], draft_id)}


@router.patch("/workspace/documents/{draft_id}/assignments/{assignment_id}")
def v4_assignment_status(
    draft_id: str,
    assignment_id: str,
    body: AssignmentStatusBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.drafting_enterprise import update_assignment_status

    return update_assignment_status(user["id"], draft_id, assignment_id, body.status)


@router.post("/workspace/documents/{draft_id}/partner-review")
def v4_partner_review(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.drafting_enterprise import send_for_partner_review

    out = send_for_partner_review(user["id"], draft_id)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/partner-approve")
def v4_partner_approve(
    draft_id: str,
    body: PartnerNoteBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.drafting_enterprise import partner_approve

    out = partner_approve(user["id"], draft_id, note=body.note)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/partner-revision")
def v4_partner_revision(
    draft_id: str,
    body: PartnerNoteBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.drafting_enterprise import partner_request_revision

    out = partner_request_revision(user["id"], draft_id, note=body.note)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.get("/workspace/documents/{draft_id}/compare-precedent")
def v4_compare_precedent(
    draft_id: str,
    precedent_id: str = Query(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.drafting_enterprise import compare_draft_to_precedent

    out = compare_draft_to_precedent(user["id"], draft_id, precedent_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/workspace/documents/{draft_id}/insert-toc")
def v4_insert_toc(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.drafting_enterprise import generate_toc_html

    doc = get_document(user["id"], draft_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    toc = generate_toc_html(doc.get("content") or "")
    body = toc + (doc.get("content") or "")
    from ....core.drafting_workspace import update_document

    updated = update_document(
        user["id"],
        draft_id,
        content=body,
        content_format=doc.get("content_format") or "html",
        change_summary="Inserted table of contents",
    )
    return {"document": updated, "toc_html": toc}


@router.post("/workspace/documents/{draft_id}/insert-annexure-index")
def v4_insert_annexure_index(draft_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.drafting_enterprise import generate_annexure_index_html
    from ....core.drafting_lifecycle import list_annexures

    doc = get_document(user["id"], draft_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    annex = list_annexures(user["id"], draft_id)
    idx = generate_annexure_index_html(annex)
    body = (doc.get("content") or "") + f"<p></p>{idx}"
    from ....core.drafting_workspace import update_document

    updated = update_document(
        user["id"],
        draft_id,
        content=body,
        content_format=doc.get("content_format") or "html",
        change_summary="Inserted annexure index",
    )
    return {"document": updated, "index_html": idx}
