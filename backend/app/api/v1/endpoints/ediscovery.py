"""Phase 4 — Evidence Intelligence Center API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.ediscovery_service import (
    create_batch,
    get_batch,
    get_matter_evidence_timeline,
    list_batches,
    list_evidence_repository,
    process_evidence_upload,
    review_item,
    search_batch,
    triage_document,
)
from ....core.evidence_extraction import supported_extensions
from ....core.evidence_intelligence import (
    analyze_evidence,
    detect_contradictions,
    identify_statutes,
    match_court_orders,
)
from ....core.job_queue import enqueue_ediscovery_job, get_job
from ....core.saas_schema import ensure_saas_schema

router = APIRouter(tags=["ediscovery"])


class DiscoveryDoc(BaseModel):
    source_identifier: str = "document"
    text: str = Field(..., min_length=10)


class BatchCreate(BaseModel):
    matter_id: str
    batch_title: str = Field(..., min_length=2)
    documents: List[DiscoveryDoc] = Field(..., min_length=1)


class TriageRequest(BaseModel):
    text: str = Field(..., min_length=10)
    matter_id: str = ""


class ItemReview(BaseModel):
    tags: Optional[List[str]] = None
    classification: str = ""
    verified: bool = True


class ContradictionRequest(BaseModel):
    document_a: str = Field(..., min_length=20)
    document_b: str = Field(..., min_length=20)
    label_a: str = "Document A"
    label_b: str = "Document B"


class StatuteRequest(BaseModel):
    text: str = Field(..., min_length=20)
    matter_id: str = ""


class CourtOrderRequest(BaseModel):
    text: str = Field(..., min_length=20)
    matter_id: str = ""


class AnalyzeTextRequest(BaseModel):
    text: str = Field(..., min_length=10)
    matter_id: str = ""
    source: str = "manual"


@router.get("/evidence/formats")
def evidence_supported_formats(user: Dict[str, Any] = Depends(get_current_user)):
    _ = user
    return {"formats": supported_extensions()}


@router.post("/evidence/upload")
async def evidence_upload(
    file: UploadFile = File(...),
    matter_id: str = Form(...),
    batch_title: str = Form(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    data = await file.read()
    if len(data) < 8:
        raise HTTPException(400, "File is empty")
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(400, "File exceeds 50 MB limit")
    out = process_evidence_upload(
        user["id"],
        matter_id,
        file.filename or "evidence",
        data,
        batch_title=batch_title or f"Evidence — {file.filename or 'upload'}",
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/evidence/analyze")
def evidence_analyze_text(
    body: AnalyzeTextRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    analysis = analyze_evidence(
        body.text,
        user_id=user["id"],
        matter_id=body.matter_id,
        source=body.source,
    )
    court_orders = match_court_orders(user["id"], body.text, matter_id=body.matter_id)
    return {"analysis": analysis, "court_orders": court_orders}


@router.get("/evidence/repository")
def evidence_repository(
    matter_id: str = "",
    limit: int = Query(100, ge=1, le=300),
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return list_evidence_repository(user["id"], matter_id=matter_id, limit=limit)


@router.get("/evidence/timeline")
def evidence_timeline(
    matter_id: str = Query(..., min_length=1),
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return {"timeline": get_matter_evidence_timeline(user["id"], matter_id)}


@router.post("/evidence/contradictions")
def evidence_contradictions(
    body: ContradictionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _ = user
    return detect_contradictions(body.document_a, body.document_b)


@router.post("/evidence/statutes")
def evidence_statutes(
    body: StatuteRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _ = user
    statutes = identify_statutes(body.text)
    return {"statutes": statutes, "count": len(statutes)}


@router.post("/evidence/court-orders")
def evidence_court_orders(
    body: CourtOrderRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    results = match_court_orders(user["id"], body.text, matter_id=body.matter_id)
    return {"results": results, "count": len(results)}


@router.post("/triage")
def ediscovery_triage(
    body: TriageRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    triage = triage_document(body.text, user_id=user["id"], matter_id=body.matter_id)
    from backend.app.core.evidence_intelligence import analyze_evidence

    analysis = analyze_evidence(
        body.text, user_id=user["id"], matter_id=body.matter_id, source="triage"
    )
    return {"triage": triage, "analysis": analysis}


@router.get("/batches")
def ediscovery_batches(
    matter_id: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return {"batches": list_batches(user["id"], matter_id=matter_id)}


@router.post("/batches")
def ediscovery_create_batch(
    body: BatchCreate,
    user: Dict[str, Any] = Depends(get_current_user),
    async_job: bool = Query(False, description="Queue via Redis for background worker"),
):
    ensure_saas_schema()
    docs = [
        {"source_identifier": d.source_identifier, "text": d.text}
        for d in body.documents
    ]
    if async_job or len(docs) >= 5:
        return enqueue_ediscovery_job(
            user["id"], body.matter_id, body.batch_title, docs
        )
    from backend.app.core.ediscovery_service import create_evidence_batch

    out = create_evidence_batch(user["id"], body.matter_id, body.batch_title, docs)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/jobs/{job_id}")
def ediscovery_job_status(
    job_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/batches/{batch_id}")
def ediscovery_get_batch(
    batch_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    batch = get_batch(user["id"], batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    return batch


@router.get("/batches/{batch_id}/search")
def ediscovery_search(
    batch_id: str,
    q: str = "",
    min_score: float = 0.0,
    user: Dict[str, Any] = Depends(get_current_user),
):
    return {"results": search_batch(user["id"], batch_id, q, min_score=min_score)}


@router.post("/items/{item_id}/review")
def ediscovery_review(
    item_id: str,
    body: ItemReview,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = review_item(
        user["id"],
        item_id,
        tags=body.tags,
        classification=body.classification,
        verified=body.verified,
    )
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


class PiiDetectRequest(BaseModel):
    text: str = Field(..., min_length=1)


class PiiRedactRequest(BaseModel):
    text: str = Field(..., min_length=1)
    types: Optional[List[str]] = None
    enabled: bool = True


class PiiWhitelistRequest(BaseModel):
    phrase: str = Field(..., min_length=3)


@router.post("/pii/detect")
def pii_detect(
    body: PiiDetectRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from document_services.pii_redactor import detect_pii

    return detect_pii(body.text, user_id=str(user["id"]))


@router.post("/pii/whitelist")
def pii_whitelist(
    body: PiiWhitelistRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from document_services.pii_redactor import whitelist_pii_phrase

    return whitelist_pii_phrase(str(user["id"]), body.phrase)


@router.post("/pii/redact")
def pii_redact(
    body: PiiRedactRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from document_services.pii_redactor import redact_text

    return redact_text(body.text, body.types, body.enabled)
