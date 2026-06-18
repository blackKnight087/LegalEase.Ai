"""IPC ↔ BNS Intelligence Engine V3 API — deterministic lookups only."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.ipc_bns_engine_v3 import (
    NOT_FOUND_MSG,
    bulk_convert_ipc,
    compare_sections,
    dataset_meta,
    extract_and_convert_document,
    extract_text_from_upload,
    list_categories,
    lookup_bns,
    lookup_ipc,
    matter_migration_impact,
    report_to_docx_bytes,
    report_to_pdf_bytes,
    search_mappings,
    sections_by_category,
    build_conversion_report,
)

router = APIRouter(tags=["ipc-bns-v3"])


class ConvertBody(BaseModel):
    section: str
    matter_id: str = ""


class BulkBody(BaseModel):
    sections: List[str]
    matter_id: str = ""


class DocumentTextBody(BaseModel):
    text: str
    case_name: str = ""
    matter_id: str = ""


class ReportExportBody(BaseModel):
    case_name: str = ""
    conversions: List[Dict[str, Any]]
    format: str = "pdf"


@router.get("/meta")
def v3_meta():
    return dataset_meta()


@router.get("/search")
def v3_search(q: str = Query(..., min_length=1), limit: int = Query(25, ge=1, le=100)):
    return search_mappings(q, limit=limit)


@router.get("/ipc/{section}")
def v3_ipc_section(
    section: str,
    user: Dict[str, Any] = Depends(get_current_user),
    matter_id: str = Query(""),
):
    return lookup_ipc(section, user_id=user["id"], matter_id=matter_id)


@router.get("/bns/{section}")
def v3_bns_section(
    section: str,
    user: Dict[str, Any] = Depends(get_current_user),
    matter_id: str = Query(""),
):
    return lookup_bns(section, user_id=user["id"], matter_id=matter_id)


@router.get("/compare/{ipc_section}")
def v3_compare(ipc_section: str, user: Dict[str, Any] = Depends(get_current_user)):
    return compare_sections(ipc_section)


@router.post("/convert")
def v3_convert(body: ConvertBody, user: Dict[str, Any] = Depends(get_current_user)):
    out = lookup_ipc(body.section, user_id=user["id"], matter_id=body.matter_id)
    if not out.get("found"):
        return {
            "status": "not_found",
            "ipc_section": out.get("ipc_section"),
            "bns_section": None,
            "description": NOT_FOUND_MSG,
            "message": NOT_FOUND_MSG,
            **out,
        }
    return {
        "status": "mapped",
        "ipc_section": out.get("ipc_section"),
        "bns_section": out.get("bns_section"),
        "description": out.get("short_description"),
        **out,
    }


@router.post("/bulk")
def v3_bulk(body: BulkBody, user: Dict[str, Any] = Depends(get_current_user)):
    return bulk_convert_ipc(body.sections, user_id=user["id"], matter_id=body.matter_id)


@router.post("/document/convert")
def v3_document_text(body: DocumentTextBody, user: Dict[str, Any] = Depends(get_current_user)):
    return extract_and_convert_document(body.text, user_id=user["id"], matter_id=body.matter_id)


@router.post("/document/upload")
async def v3_document_upload(
    file: UploadFile = File(...),
    case_name: str = Query(""),
    matter_id: str = Query(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    try:
        text = extract_text_from_upload(file.filename or "upload.txt", data)
    except Exception as e:
        raise HTTPException(400, f"Could not read file: {e}") from e
    if not text.strip():
        raise HTTPException(400, "No text extracted from document")
    out = extract_and_convert_document(text, user_id=user["id"], matter_id=matter_id)
    out["filename"] = file.filename
    out["case_name"] = case_name
    return out


@router.post("/report/export")
def v3_report_export(body: ReportExportBody, user: Dict[str, Any] = Depends(get_current_user)):
    report = build_conversion_report(
        case_name=body.case_name,
        conversions=body.conversions,
        generated_by=user.get("email") or user.get("id", ""),
    )
    fmt = (body.format or "pdf").lower()
    if fmt == "docx":
        data = report_to_docx_bytes(report)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="ipc-bns-report.docx"'},
        )
    data = report_to_pdf_bytes(report)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="ipc-bns-report.pdf"'},
    )


@router.get("/categories")
def v3_categories():
    return {"categories": list_categories()}


@router.get("/categories/{category}")
def v3_category(category: str):
    return {"sections": sections_by_category(category)}


@router.get("/matters/{matter_id}/migration")
def v3_matter_migration(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    out = matter_migration_impact(user["id"], matter_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out
