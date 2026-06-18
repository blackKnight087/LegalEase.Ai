"""Phase 1 — Case & matter management API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.matter_repo import (
    add_matter_note,
    archive_matter,
    create_matter,
    delete_matter,
    get_matter,
    link_document_to_matter,
    list_matter_documents,
    list_matter_notes,
    list_matters,
    matter_workflow_signal,
    restore_matter,
    update_matter,
)
from ....core.matter_type_config import MATTER_TYPES, PRIORITIES, STATUS_TIERS
from ....core.matter_workflow import (
    add_deadline,
    add_hearing,
    add_task,
    add_timeline_event,
    get_matter_dashboard,
    list_deadlines,
    list_hearings,
    list_matters_summary,
    list_tasks,
    list_timeline,
    list_unlinked_documents,
    update_task,
)
from ....core.practice_schema import ensure_practice_schema
from ....core.index_jobs import list_active_jobs
from ....core.matter_policy import resolve_matter_context, require_matter_write_access
from ....core.observability import emit_event

router = APIRouter(tags=["matters"])


def _require_matter_access(user_id: str, matter_id: str) -> None:
    _ = resolve_matter_context(user_id, matter_id)


def _matter_ctx_or_404(user_id: str, matter_id: str) -> Dict[str, str]:
    ctx = resolve_matter_context(user_id, matter_id)
    emit_event(
        "matter_access_granted",
        request_user_id=str(user_id),
        owner_user_id=str(ctx.get("owner_user_id") or ""),
        matter_id=str(matter_id),
        role=str(ctx.get("role") or ""),
    )
    return ctx


def _require_matter_write_access(ctx: Dict[str, str]) -> None:
    require_matter_write_access(ctx)


class MatterCreate(BaseModel):
    matter_name: str = Field(..., min_length=2)
    practice_area: str = "General Research"
    matter_type: str = ""
    case_number: str = ""
    client_name: str = ""
    opposing_party: str = ""
    venue: str = ""
    status_tier: str = "Open"
    police_station: str = ""
    fir_number: str = ""
    filing_date: str = ""
    next_hearing_date: str = ""
    priority: str = "Medium"
    description: str = ""


class MatterUpdate(BaseModel):
    matter_name: Optional[str] = None
    practice_area: Optional[str] = None
    matter_type: Optional[str] = None
    case_number: Optional[str] = None
    status_tier: Optional[str] = None
    client_name: Optional[str] = None
    opposing_party: Optional[str] = None
    venue: Optional[str] = None
    police_station: Optional[str] = None
    fir_number: Optional[str] = None
    filing_date: Optional[str] = None
    next_hearing_date: Optional[str] = None
    priority: Optional[str] = None
    description: Optional[str] = None


class MatterNoteCreate(BaseModel):
    raw_content: str = Field(..., min_length=1)
    anonymized_content: str = ""


class LinkDocumentRequest(BaseModel):
    document_id: str


@router.get("/meta/types")
def matters_meta_types():
    return {
        "matter_types": MATTER_TYPES,
        "status_tiers": STATUS_TIERS,
        "priorities": PRIORITIES,
    }


@router.get("/health/indexing")
def matters_indexing_health(user: Dict[str, Any] = Depends(get_current_user)):
    active = list_active_jobs(user["id"])
    return {
        "active_jobs": active,
        "queue_depth": len([j for j in active if j.get("status") == "queued"]),
        "running_jobs": len([j for j in active if j.get("status") == "running"]),
        "ok": True,
    }


@router.get("/documents/unlinked")
def matters_unlinked_documents(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_practice_schema()
    return {"documents": list_unlinked_documents(user["id"])}


@router.get("")
def matters_list(
    status: str = "",
    summary: bool = Query(False),
    include_archived: bool = Query(False),
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_practice_schema()
    if summary:
        return {"matters": list_matters_summary(user["id"])}
    return {"matters": list_matters(user["id"], status=status, include_archived=include_archived)}


@router.post("")
def matters_create(
    body: MatterCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_practice_schema()
    m = create_matter(
        user["id"],
        matter_name=body.matter_name,
        practice_area=body.practice_area,
        matter_type=body.matter_type or body.practice_area,
        case_number=body.case_number,
        client_name=body.client_name,
        opposing_party=body.opposing_party,
        venue=body.venue,
        status_tier=body.status_tier,
        police_station=body.police_station,
        fir_number=body.fir_number,
        filing_date=body.filing_date,
        next_hearing_date=body.next_hearing_date,
        priority=body.priority,
        description=body.description,
    )
    return m


@router.get("/evidence-desk")
def matters_evidence_desk(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.evidence_desk import get_evidence_desk

    return get_evidence_desk(user["id"])


@router.post("/evidence-desk/scan")
def matters_evidence_desk_scan(
    user: Dict[str, Any] = Depends(get_current_user),
    max_matters: int = 8,
):
    from ....core.evidence_desk import scan_all_matters

    return scan_all_matters(user["id"], max_matters=max(1, min(max_matters, 15)))


@router.get("/hearings/digest")
def matters_hearing_digest(
    days_ahead: int = 14,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.lawyer_digest import get_hearing_digest

    return get_hearing_digest(user["id"], days_ahead=days_ahead)


@router.delete("/{matter_id}")
def matters_delete(
    matter_id: str,
    hard: bool = Query(False, description="hard=true permanently deletes"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    if (ctx.get("role") or "viewer") != "owner":
        raise HTTPException(403, "Only matter owner can delete this matter")
    if hard:
        ok = delete_matter(ctx["owner_user_id"], matter_id)
    else:
        ok = archive_matter(ctx["owner_user_id"], matter_id)
    if not ok:
        raise HTTPException(404, "Matter not found")
    return {"deleted": bool(hard), "archived": bool(not hard), "matter_id": matter_id}


@router.post("/{matter_id}/restore")
def matters_restore(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    if (ctx.get("role") or "viewer") != "owner":
        raise HTTPException(403, "Only matter owner can restore this matter")
    if not restore_matter(ctx["owner_user_id"], matter_id):
        raise HTTPException(404, "Matter not found")
    return {"restored": True, "matter_id": matter_id}


@router.get("/{matter_id}")
def matters_get(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    owner_id = ctx["owner_user_id"]
    m = get_matter(owner_id, matter_id)
    if not m:
        raise HTTPException(404, "Matter not found")
    m["notes"] = list_matter_notes(owner_id, matter_id)
    m["documents"] = list_matter_documents(owner_id, matter_id)
    return m


@router.patch("/{matter_id}")
def matters_patch(
    matter_id: str,
    body: MatterUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    m = update_matter(ctx["owner_user_id"], matter_id, **body.model_dump(exclude_none=True))
    if not m:
        raise HTTPException(404, "Matter not found")
    return m


@router.post("/{matter_id}/notes")
def matters_add_note(
    matter_id: str,
    body: MatterNoteCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    owner_id = ctx["owner_user_id"]
    m = get_matter(owner_id, matter_id)
    if not m:
        raise HTTPException(404, "Matter not found")
    note = add_matter_note(
        owner_id,
        matter_id,
        body.raw_content,
        anonymized_content=body.anonymized_content,
    )
    if not note:
        raise HTTPException(500, "Could not save note")
    matter_workflow_signal(owner_id, m, body.raw_content)
    return note


@router.post("/{matter_id}/documents/link")
def matters_link_document(
    matter_id: str,
    body: LinkDocumentRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    if not link_document_to_matter(ctx["owner_user_id"], body.document_id, matter_id):
        raise HTTPException(404, "Matter or document not found")
    return {"linked": True, "matter_id": matter_id, "document_id": body.document_id}


class TimelineCreate(BaseModel):
    title: str = Field(..., min_length=2)
    description: str = ""
    event_date: str = ""
    event_type: str = "general"


class HearingCreate(BaseModel):
    hearing_date: str
    court_name: str = ""
    purpose: str = ""
    notes: str = ""
    judge: str = ""
    judge_name: str = ""
    arguments: str = ""
    observations: str = ""
    judge_observation: str = ""
    next_hearing_date: str = ""
    summary: str = ""
    prosecution_argument: str = ""
    defense_argument: str = ""
    document_source: str = ""
    page_number: str = ""


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=2)
    due_date: str = ""
    assignee: str = ""
    task_source: str = "manual"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None


class DeadlineCreate(BaseModel):
    title: str = Field(..., min_length=2)
    due_date: str
    deadline_type: str = "filing"
    notes: str = ""


@router.get("/{matter_id}/dashboard")
def matters_dashboard(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    import json
    import time
    from pathlib import Path

    t0 = time.perf_counter()
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    dash = get_matter_dashboard(ctx["owner_user_id"], matter_id)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    # #region agent log
    try:
        log_path = Path(__file__).resolve().parents[5] / "debug-cf6ca9.log"
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "hypothesisId": "H1",
                        "location": "matters.py:matters_dashboard",
                        "message": "dashboard_timing",
                        "data": {
                            "matter_id": matter_id,
                            "elapsed_ms": elapsed_ms,
                            "ok": bool(dash),
                        },
                        "timestamp": int(time.time() * 1000),
                        "runId": "post-fix",
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion
    if not dash:
        raise HTTPException(404, "Matter not found")
    return dash


@router.get("/{matter_id}/timeline")
def matters_timeline(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"events": list_timeline(ctx["owner_user_id"], matter_id)}


@router.post("/{matter_id}/timeline")
def matters_timeline_add(
    matter_id: str,
    body: TimelineCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    try:
        return add_timeline_event(
            ctx["owner_user_id"],
            matter_id,
            title=body.title,
            description=body.description,
            event_date=body.event_date,
            event_type=body.event_type,
        )
    except ValueError:
        raise HTTPException(404, "Matter not found")


@router.get("/{matter_id}/hearings")
def matters_hearings_list(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_hearings_intel import list_hearings as list_matter_hearings

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"hearings": list_matter_hearings(ctx["owner_user_id"], matter_id)}


@router.post("/{matter_id}/hearings")
def matters_hearings_add(
    matter_id: str,
    body: HearingCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_hearings_intel import schedule_hearing

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    try:
        judge = (body.judge_name or body.judge or "").strip()
        obs = (body.judge_observation or body.observations or "").strip()
        row = schedule_hearing(
            ctx["owner_user_id"],
            matter_id,
            hearing_date=body.hearing_date,
            court_name=body.court_name,
            purpose=body.purpose,
            notes=body.notes,
            judge_name=judge,
            summary=body.summary,
            prosecution_argument=body.prosecution_argument,
            defense_argument=body.defense_argument,
            judge_observation=obs,
            next_hearing_date=body.next_hearing_date,
            document_source=body.document_source,
            page_number=body.page_number,
        )
        return {"ok": True, "message": "Hearing scheduled successfully", "hearing": row}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{matter_id}/tasks")
def matters_tasks_list(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"tasks": list_tasks(ctx["owner_user_id"], matter_id)}


@router.post("/{matter_id}/tasks")
def matters_tasks_add(
    matter_id: str,
    body: TaskCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    try:
        return add_task(
            ctx["owner_user_id"],
            matter_id,
            title=body.title,
            due_date=body.due_date,
            assignee=body.assignee,
            task_source=body.task_source,
        )
    except ValueError:
        raise HTTPException(404, "Matter not found")


@router.patch("/{matter_id}/tasks/{task_id}")
def matters_tasks_patch(
    matter_id: str,
    task_id: str,
    body: TaskUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    out = update_task(ctx["owner_user_id"], matter_id, task_id, **body.model_dump(exclude_none=True))
    if not out:
        raise HTTPException(404, "Task or matter not found")
    return out


@router.get("/{matter_id}/deadlines")
def matters_deadlines_list(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"deadlines": list_deadlines(ctx["owner_user_id"], matter_id)}


@router.post("/{matter_id}/deadlines")
def matters_deadlines_add(
    matter_id: str,
    body: DeadlineCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    try:
        return add_deadline(
            ctx["owner_user_id"],
            matter_id,
            title=body.title,
            due_date=body.due_date,
            deadline_type=body.deadline_type,
            notes=body.notes,
        )
    except ValueError:
        raise HTTPException(404, "Matter not found")


@router.get("/{matter_id}/autopilot")
def matters_autopilot(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_autopilot import analyze_matter

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    m = get_matter(ctx["owner_user_id"], matter_id)
    if not m:
        raise HTTPException(404, "Matter not found")
    return analyze_matter(str(ctx["owner_user_id"]), matter_id)


@router.get("/{matter_id}/search")
def matters_search(
    matter_id: str,
    q: str = Query("", min_length=1),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_intelligence import search_matter

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return search_matter(ctx["owner_user_id"], matter_id, q)


@router.post("/{matter_id}/timeline/generate")
def matters_timeline_generate(
    matter_id: str,
    auto_insert: bool = Query(False),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_intelligence import generate_timeline_from_docs

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    return generate_timeline_from_docs(ctx["owner_user_id"], matter_id, auto_insert=auto_insert)


@router.post("/{matter_id}/entities/extract")
def matters_extract_entities(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_entities import extract_entities_from_docs

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    try:
        ents = extract_entities_from_docs(ctx["owner_user_id"], matter_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"entities": ents, "count": len(ents)}


@router.get("/{matter_id}/intelligence/status")
def matters_intel_status(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_intel_pipeline import get_intel_status

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return get_intel_status(matter_id)


@router.post("/{matter_id}/intelligence/run")
def matters_intel_run(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_intel_pipeline import run_matter_intelligence_pipeline

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    result = run_matter_intelligence_pipeline(
        ctx["owner_user_id"], matter_id, skip_if_running=False
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "Intelligence pipeline failed")
    return result


@router.get("/{matter_id}/entities")
def matters_list_entities(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_entities import list_entities

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"entities": list_entities(ctx["owner_user_id"], matter_id)}


@router.get("/{matter_id}/evidence")
def matters_list_evidence(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_evidence import list_evidence

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"evidence": list_evidence(ctx["owner_user_id"], matter_id)}


class EvidenceCreate(BaseModel):
    title: str = Field(..., min_length=2)
    category: str = "document"
    document_id: str = ""
    tags: str = ""
    notes: str = ""
    strength: str = "unknown"


@router.post("/{matter_id}/evidence")
def matters_add_evidence(
    matter_id: str,
    body: EvidenceCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_evidence import add_evidence

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    try:
        return add_evidence(
            ctx["owner_user_id"],
            matter_id,
            title=body.title,
            category=body.category,
            document_id=body.document_id,
            tags=body.tags,
            notes=body.notes,
            strength=body.strength,
        )
    except ValueError:
        raise HTTPException(404, "Matter not found")


@router.post("/{matter_id}/evidence/extract")
def matters_extract_evidence(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_evidence import extract_evidence_from_docs

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    try:
        items = extract_evidence_from_docs(ctx["owner_user_id"], matter_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"evidence": items, "count": len(items)}


@router.post("/{matter_id}/hearings/extract")
def matters_extract_hearings(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_hearings_intel import extract_hearings_from_docs

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    try:
        return extract_hearings_from_docs(ctx["owner_user_id"], matter_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{matter_id}/smoke")
def matters_smoke(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_intelligence import run_matter_smoke_tests

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    try:
        return run_matter_smoke_tests(ctx["owner_user_id"], matter_id)
    except Exception as exc:
        logger.exception("Matter smoke test failed: %s", exc)
        raise HTTPException(500, f"Smoke test failed: {exc}") from exc


@router.post("/{matter_id}/documents/upload")
async def matters_upload_document(
    matter_id: str,
    file: UploadFile = File(...),
    ocr: str = Query("0"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from .documents import upload_document

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    from ....core.matter_enhancements import log_matter_audit

    log_matter_audit(ctx["owner_user_id"], matter_id, "document_upload_started", file.filename or "")
    owner_user = dict(user)
    owner_user["id"] = ctx["owner_user_id"]
    return await upload_document(file=file, ocr=ocr, matter_id=matter_id, user=owner_user)


@router.get("/notifications/all")
def matters_notifications_all(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.matter_enhancements import get_matter_notifications

    return {"notifications": get_matter_notifications(user["id"])}


@router.get("/{matter_id}/timeline/suggestions")
def matters_timeline_suggestions(
    matter_id: str,
    status: str = "pending",
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import list_timeline_suggestions

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"suggestions": list_timeline_suggestions(ctx["owner_user_id"], matter_id, status=status)}


@router.post("/{matter_id}/timeline/suggestions/{suggestion_id}/approve")
def matters_approve_suggestion(
    matter_id: str,
    suggestion_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import approve_timeline_suggestion

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    if not approve_timeline_suggestion(ctx["owner_user_id"], matter_id, suggestion_id):
        raise HTTPException(404, "Suggestion not found")
    return {"approved": True}


@router.post("/{matter_id}/timeline/suggestions/{suggestion_id}/reject")
def matters_reject_suggestion(
    matter_id: str,
    suggestion_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import reject_timeline_suggestion

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    if not reject_timeline_suggestion(matter_id, suggestion_id):
        raise HTTPException(404, "Suggestion not found")
    return {"rejected": True}


@router.get("/{matter_id}/entities/profiles")
def matters_entity_profiles(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import get_entity_profiles

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"profiles": get_entity_profiles(ctx["owner_user_id"], matter_id)}


@router.get("/{matter_id}/contradictions")
def matters_list_contradictions(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import list_contradictions

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    pairs = list_contradictions(ctx["owner_user_id"], matter_id)
    return {"pairs": pairs, "count": len(pairs)}


@router.post("/{matter_id}/contradictions/extract")
def matters_extract_contradictions(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import extract_and_persist_contradictions

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    return extract_and_persist_contradictions(ctx["owner_user_id"], matter_id)


@router.get("/{matter_id}/export")
def matters_export_pack(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from fastapi.responses import Response
    from ....core.matter_enhancements import export_matter_pack

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    try:
        data = export_matter_pack(ctx["owner_user_id"], matter_id)
    except ValueError:
        raise HTTPException(404, "Matter not found")
    m = get_matter(ctx["owner_user_id"], matter_id)
    safe = (m.get("matter_name") or "matter").replace(" ", "_")[:40]
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}_pack.zip"'},
    )


@router.get("/{matter_id}/audit")
def matters_audit_log(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import list_matter_audit

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"audit": list_matter_audit(ctx["owner_user_id"], matter_id)}


@router.get("/{matter_id}/members")
def matters_members_list(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import list_matter_members

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return {"members": list_matter_members(ctx["owner_user_id"], matter_id)}


class MemberAdd(BaseModel):
    user_id: str
    role: str = "viewer"


@router.post("/{matter_id}/members")
def matters_members_add(
    matter_id: str,
    body: MemberAdd,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import add_matter_member

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    if (ctx.get("role") or "viewer") != "owner":
        raise HTTPException(403, "Only matter owner can manage members")
    try:
        return add_matter_member(
            ctx["owner_user_id"], matter_id, member_user_id=body.user_id, role=body.role
        )
    except ValueError:
        raise HTTPException(404, "Matter not found")


@router.patch("/{matter_id}/documents/{document_id}")
def matters_document_meta(
    matter_id: str,
    document_id: str,
    privileged: bool = Query(False),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_enhancements import log_matter_audit, update_document_meta

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    if not update_document_meta(ctx["owner_user_id"], document_id, privileged=privileged):
        raise HTTPException(404, "Document not found")
    log_matter_audit(ctx["owner_user_id"], matter_id, "document_meta", f"privileged={privileged}")
    return {"updated": True, "privileged": privileged}


@router.get("/{matter_id}/hearing-prep-pack")
def matters_hearing_prep_pack(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.hearing_prep_pack import build_hearing_prep_pack

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return build_hearing_prep_pack(ctx["owner_user_id"], matter_id)


@router.get("/{matter_id}/client-status-letter")
def matters_client_status_letter(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.client_status_letter import draft_client_status_letter

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    return draft_client_status_letter(ctx["owner_user_id"], matter_id)


class CauseListImport(BaseModel):
    text: str = Field(..., min_length=20)


@router.post("/{matter_id}/hearings/import-cause-list")
def matters_import_cause_list(
    matter_id: str,
    body: CauseListImport,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.cause_list_import import import_cause_list_to_matter

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    return import_cause_list_to_matter(ctx["owner_user_id"], matter_id, body.text)


class VoiceHearingNote(BaseModel):
    transcript: str = Field(..., min_length=10)


@router.post("/{matter_id}/hearings/from-voice")
def matters_hearing_from_voice(
    matter_id: str,
    body: VoiceHearingNote,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.matter_hearings_intel import parse_voice_hearing_note, schedule_hearing

    ctx = _matter_ctx_or_404(user["id"], matter_id)
    _require_matter_write_access(ctx)
    parsed = parse_voice_hearing_note(body.transcript)
    if not parsed.get("hearing_date"):
        return {"ok": False, "error": "Could not detect a hearing date in the transcript", "parsed": parsed}
    h = schedule_hearing(
        ctx["owner_user_id"],
        matter_id,
        hearing_date=parsed["hearing_date"],
        court_name=parsed.get("court_name", ""),
        purpose=parsed.get("purpose", "Court appearance"),
        notes=body.transcript[:500],
        judge_name=parsed.get("judge", ""),
        next_hearing_date=parsed.get("next_hearing_date", ""),
        summary=parsed.get("summary", ""),
    )
    return {"ok": True, "hearing": h, "parsed": parsed}
