"""Practice SaaS overview API."""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.crm_service import classify_intake_query, draft_follow_up_email
from ....services.practice_dashboard import practice_overview

router = APIRouter(tags=["practice"])


@router.get("/overview")
def get_practice_overview(user: Dict[str, Any] = Depends(get_current_user)):
    return practice_overview(user["id"])


@router.get("/limitation/presets")
def limitation_presets(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.limitation_calculator import list_limitation_presets

    return {"presets": list_limitation_presets()}


class LimitationCalc(BaseModel):
    preset_id: str
    start_date: str = Field(..., description="YYYY-MM-DD")


@router.post("/limitation/calculate")
def limitation_calculate(
    body: LimitationCalc,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.limitation_calculator import calculate_limitation

    return calculate_limitation(body.preset_id, body.start_date)


class LimitationMatterBody(LimitationCalc):
    matter_id: str
    title: str = ""


class CauseListText(BaseModel):
    text: str = Field(..., min_length=20)


class CauseListImportRow(BaseModel):
    matter_id: str = ""
    suggested_matter_id: str = ""
    hearing_date: str = ""
    court_name: str = ""
    purpose: str = ""
    selected: bool = True


class CauseListImportBody(BaseModel):
    rows: list[CauseListImportRow]


@router.post("/court-day/parse")
def court_day_parse(
    body: CauseListText,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.court_day import parse_and_match_cause_list

    return parse_and_match_cause_list(user["id"], body.text)


@router.post("/court-day/import")
def court_day_import(
    body: CauseListImportBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.court_day import import_matched_rows

    rows = [r.model_dump() for r in body.rows]
    return import_matched_rows(user["id"], rows)


@router.get("/court-day/today")
def court_day_today(
    user: Dict[str, Any] = Depends(get_current_user),
    days_ahead: int = 14,
):
    from ....core.court_day import get_court_day_today

    return get_court_day_today(user["id"], days_ahead=max(1, min(days_ahead, 60)))


@router.get("/court-day/mission-control")
def court_day_mission_control(user: Dict[str, Any] = Depends(get_current_user)):
    """Alias for Mission Control dashboard (works even if /litigation/* routes are stale)."""
    from ....core.court_day import get_court_day_today

    return get_court_day_today(user["id"], days_ahead=30)


@router.get("/court-day/prep/{matter_id}")
def court_day_prep(
    matter_id: str,
    use_ai: bool = True,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.court_day import get_prep_pack

    out = get_prep_pack(user["id"], matter_id, use_ai=use_ai)
    if not out.get("ok", True) and not out.get("markdown"):
        raise HTTPException(404, out.get("error", "Matter not found"))
    return out


@router.get("/court-day/prep/{matter_id}/pdf")
def court_day_prep_pdf(
    matter_id: str,
    use_ai: bool = True,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.hearing_prep_pack import render_prep_pack_pdf

    try:
        pdf_bytes, filename = render_prep_pack_pdf(user["id"], matter_id, use_ai=use_ai)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Failed to generate prep pack PDF: {exc}") from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/court-day/calendar.ics")
def court_day_calendar_ics(
    user: Dict[str, Any] = Depends(get_current_user),
    days_ahead: int = 60,
):
    from ....core.litigation_calendar import build_hearings_ics

    ics = build_hearings_ics(user["id"], days_ahead=max(7, min(days_ahead, 180)))
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="legalease-hearings.ics"'},
    )


@router.post("/court-day/parse-file")
async def court_day_parse_file(
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.court_day import parse_and_match_cause_list

    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 8 MB)")
    name = (file.filename or "").lower()
    text = ""
    if name.endswith(".pdf") or (file.content_type or "").startswith("application/pdf"):
        import tempfile
        from pathlib import Path

        try:
            from backend.app.core.pdf_extraction import extract_pdf_production

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            text, _method = extract_pdf_production(tmp_path, force_ocr=False)
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as exc:
            raise HTTPException(400, f"PDF extract failed: {exc}") from exc
    else:
        text = data.decode("utf-8", errors="replace")
    if len(text.strip()) < 20:
        raise HTTPException(400, "No readable text in file")
    return parse_and_match_cause_list(user["id"], text)


class CourtSyncBody(BaseModel):
    source: str = "paste"
    text: str = ""
    court_code: str = ""
    bench_id: str = ""
    hearing_date: str = ""
    auto_schedule: bool = True
    api_date: str = ""
    api_state: str = ""
    api_query: str = ""
    api_advocate: str = ""
    api_litigant: str = ""
    api_limit: int = 50
    api_district_code: str = ""
    api_court_complex_code: str = ""


class CourtSyncSettingsBody(BaseModel):
    preferred_mode: str = ""
    api_key: str = ""
    clear_api_key: bool = False


@router.get("/court-sync/status")
def court_sync_status(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.ecourts_adapter import integration_status

    return integration_status(str(user["id"]))


@router.get("/court-sync/settings")
def court_sync_settings_get(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.court_sync_settings import get_court_sync_settings

    return get_court_sync_settings(str(user["id"]))


@router.put("/court-sync/settings")
def court_sync_settings_put(
    body: CourtSyncSettingsBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.court_sync_settings import save_court_sync_settings

    return save_court_sync_settings(
        str(user["id"]),
        preferred_mode=body.preferred_mode,
        api_key=body.api_key if body.api_key else None,
        clear_api_key=body.clear_api_key,
    )


@router.post("/court-sync")
def court_sync(
    body: CourtSyncBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.ecourts_adapter import sync_cause_list

    out = sync_cause_list(
        user["id"],
        source=body.source,
        text=body.text,
        court_code=body.court_code,
        bench_id=body.bench_id,
        hearing_date=body.hearing_date,
        auto_schedule=body.auto_schedule,
        api_date=body.api_date,
        api_state=body.api_state,
        api_query=body.api_query,
        api_advocate=body.api_advocate,
        api_litigant=body.api_litigant,
        api_limit=body.api_limit,
        api_district_code=body.api_district_code,
        api_court_complex_code=body.api_court_complex_code,
    )
    if not out.get("ok"):
        raise HTTPException(400, out.get("error", "Sync failed"))
    return out


@router.get("/court-sync/history")
def court_sync_history(
    limit: int = 10,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.court_sync_log import list_court_sync_history

    return {"history": list_court_sync_history(str(user["id"]), limit=max(1, min(limit, 50)))}


def _raise_ecourts_error(exc: Exception) -> None:
    from ....core.ecourtsindia_client import ECourtsIndiaError

    if isinstance(exc, ECourtsIndiaError):
        status = exc.status_code or 502
        if status < 400:
            status = 502
        raise HTTPException(status, str(exc)) from exc
    raise exc


class EcourtsCaseSyncBody(BaseModel):
    matter_id: str
    import_hearings: bool = True
    import_orders: bool = True


@router.get("/ecourts/case/{cnr}")
def ecourts_case_preview(cnr: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.ecourts_case_sync import fetch_case_preview

    try:
        return fetch_case_preview(str(user["id"]), cnr)
    except Exception as exc:
        _raise_ecourts_error(exc)


@router.post("/ecourts/case/{cnr}/sync")
def ecourts_case_sync(
    cnr: str,
    body: EcourtsCaseSyncBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.ecourts_case_sync import sync_case_to_matter

    try:
        out = sync_case_to_matter(
            str(user["id"]),
            cnr,
            body.matter_id,
            import_hearings=body.import_hearings,
            import_orders=body.import_orders,
        )
    except Exception as exc:
        _raise_ecourts_error(exc)
    if not out.get("ok"):
        raise HTTPException(400, out.get("error", "Sync failed"))
    return out


@router.get("/ecourts/search")
def ecourts_search(
    user: Dict[str, Any] = Depends(get_current_user),
    q: str = Query("", alias="query"),
    advocates: str = "",
    litigants: str = "",
    litigant: str = "",
    court_codes: str = Query("", alias="courtCodes"),
    filing_date_from: str = Query("", alias="filingDateFrom"),
    filing_date_to: str = Query("", alias="filingDateTo"),
    page: int = 1,
    page_size: int = Query(20, alias="pageSize"),
    case_status: str = Query("", alias="caseStatus"),
    case_type: str = Query("", alias="caseType"),
    state: str = "",
):
    from ....core.ecourts_case_sync import search_ecourts

    filters: Dict[str, Any] = {
        "page": page,
        "pageSize": page_size,
    }
    if q:
        filters["q"] = q
    if advocates:
        filters["advocates"] = advocates
    lit = litigants or litigant
    if lit:
        filters["litigants"] = lit
    if court_codes:
        filters["courtCodes"] = court_codes
    if filing_date_from:
        filters["filingDateFrom"] = filing_date_from
    if filing_date_to:
        filters["filingDateTo"] = filing_date_to
    if case_status:
        filters["caseStatus"] = case_status
    if case_type:
        filters["caseType"] = case_type
    if state:
        filters["state"] = state
    try:
        return search_ecourts(str(user["id"]), **filters)
    except Exception as exc:
        _raise_ecourts_error(exc)


@router.get("/ecourts/court-structure/states")
def ecourts_court_states(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.court_sync_settings import resolve_ecourtsindia_api_key
    from ....core.ecourtsindia_client import ECourtsIndiaError, list_court_states

    api_key = resolve_ecourtsindia_api_key(str(user["id"]))
    if not api_key:
        raise HTTPException(
            400,
            "eCourtsIndia API key not configured. Add ECOURTSINDIA_API_KEY in .env "
            "or save your key in Court Sync settings.",
        )
    try:
        return list_court_states(api_key)
    except ECourtsIndiaError as exc:
        _raise_ecourts_error(exc)


@router.get("/ecourts/court-structure/states/{state}/districts")
def ecourts_court_districts(state: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.court_sync_settings import resolve_ecourtsindia_api_key
    from ....core.ecourtsindia_client import ECourtsIndiaError, list_court_districts

    api_key = resolve_ecourtsindia_api_key(str(user["id"]))
    if not api_key:
        raise HTTPException(
            400,
            "eCourtsIndia API key not configured. Add ECOURTSINDIA_API_KEY in .env "
            "or save your key in Court Sync settings.",
        )
    try:
        return list_court_districts(api_key, state)
    except ECourtsIndiaError as exc:
        _raise_ecourts_error(exc)


@router.get("/ecourts/causelist/available-dates")
def ecourts_available_dates(
    user: Dict[str, Any] = Depends(get_current_user),
    state: str = Query(..., min_length=1),
    district_code: str = Query("", alias="districtCode"),
    court_complex_code: str = Query("", alias="courtComplexCode"),
):
    from ....core.court_sync_settings import resolve_ecourtsindia_api_key
    from ....core.ecourtsindia_client import ECourtsIndiaError, get_available_cause_dates

    api_key = resolve_ecourtsindia_api_key(str(user["id"]))
    if not api_key:
        raise HTTPException(
            400,
            "eCourtsIndia API key not configured. Add ECOURTSINDIA_API_KEY in .env "
            "or save your key in Court Sync settings.",
        )
    try:
        return get_available_cause_dates(
            api_key,
            state,
            district_code=district_code,
            court_complex_code=court_complex_code,
        )
    except ECourtsIndiaError as exc:
        _raise_ecourts_error(exc)


@router.get("/evidence-desk")
def practice_evidence_desk(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.evidence_desk import get_evidence_desk

    return get_evidence_desk(user["id"])


@router.post("/evidence-desk/scan")
def practice_evidence_desk_scan(
    user: Dict[str, Any] = Depends(get_current_user),
    max_matters: int = 8,
):
    from ....core.evidence_desk import scan_all_matters

    return scan_all_matters(user["id"], max_matters=max(1, min(max_matters, 50)))


@router.post("/evidence-desk/scan-all")
def practice_evidence_desk_scan_all(
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.evidence_desk import scan_all_matters

    return scan_all_matters(user["id"], max_matters=50, scan_all=True)


@router.get("/evidence-desk/export")
def practice_evidence_desk_export(
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.evidence_desk import export_evidence_desk_markdown

    md = export_evidence_desk_markdown(user["id"])
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="evidence-desk-report.md"'},
    )


@router.post("/limitation/add-to-matter")
def limitation_add_to_matter(
    body: LimitationMatterBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.limitation_calculator import calculate_limitation
    from ....core.matter_repo import get_matter_access_context
    from ....core.matter_workflow import add_deadline

    calc = calculate_limitation(body.preset_id, body.start_date)
    if not calc.get("ok"):
        raise HTTPException(400, calc.get("error", "Calculation failed"))
    ctx = get_matter_access_context(user["id"], body.matter_id)
    if not ctx:
        raise HTTPException(404, "Matter not found")
    title = (body.title or calc.get("label") or "Limitation deadline").strip()
    dl = add_deadline(
        ctx["owner_user_id"],
        body.matter_id,
        title=title,
        due_date=str(calc["due_date"]),
        deadline_type="limitation",
        notes=str(calc.get("description", "")),
    )
    return {"ok": True, "calculation": calc, "deadline": dl}


class PublicIntakeRequest(BaseModel):
    prospect_name: str = Field(..., min_length=2)
    contact_email: str = Field(..., min_length=5)
    raw_intake_query: str = Field(..., min_length=10)
    contact_phone: str = ""
    referral_source: str = "Website"


# ---------- Litigation OS (Mission Control) ----------


@router.get("/litigation/dashboard")
def litigation_dashboard(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import get_litigation_dashboard

    return get_litigation_dashboard(user["id"])


@router.get("/litigation/diagnostics")
def litigation_diagnostics(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import get_litigation_diagnostics

    return get_litigation_diagnostics(str(user["id"]))


@router.get("/litigation/hearings")
def litigation_hearings(
    matter_id: str = "",
    status: str = "",
    from_date: str = "",
    to_date: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import list_firm_hearings

    return {"hearings": list_firm_hearings(user["id"], matter_id=matter_id, status=status, from_date=from_date, to_date=to_date)}


class HearingCreate(BaseModel):
    matter_id: str
    hearing_date: str = Field(..., min_length=8)
    hearing_time: str = ""
    court_name: str = ""
    judge: str = ""
    purpose: str = ""
    stage: str = ""
    status: str = "scheduled"
    notes: str = ""
    assigned_lawyer: str = ""


@router.post("/litigation/hearings")
def litigation_hearing_create(
    body: HearingCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import create_firm_hearing

    out = create_firm_hearing(user["id"], body.model_dump())
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


class HearingPatch(BaseModel):
    hearing_date: str = ""
    hearing_time: str = ""
    court_name: str = ""
    judge: str = ""
    purpose: str = ""
    stage: str = ""
    status: str = ""
    notes: str = ""
    assigned_lawyer: str = ""
    next_hearing_date: str = ""


@router.patch("/litigation/hearings/{hearing_id}")
def litigation_hearing_patch(
    hearing_id: str,
    body: HearingPatch,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import update_firm_hearing

    out = update_firm_hearing(user["id"], hearing_id, body.model_dump(exclude_unset=True))
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/litigation/calendar")
def litigation_calendar(
    year: int = 0,
    month: int = 0,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import get_calendar_events

    return get_calendar_events(user["id"], year=year, month=month)


@router.get("/litigation/tasks")
def litigation_tasks(
    matter_id: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import list_firm_litigation_tasks

    from ....core.litigation_os import TASK_TEMPLATES

    return {"tasks": list_firm_litigation_tasks(user["id"], matter_id=matter_id), "templates": list(TASK_TEMPLATES)}


class LitigationTaskCreate(BaseModel):
    matter_id: str
    title: str = Field(..., min_length=2)
    due_date: str = ""
    assignee: str = ""
    priority: str = ""


@router.post("/litigation/tasks")
def litigation_task_create(
    body: LitigationTaskCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import create_litigation_task

    title = body.title
    if body.priority.strip():
        title = f"[{body.priority.strip()}] {title}"
    out = create_litigation_task(
        user["id"],
        matter_id=body.matter_id,
        title=title,
        due_date=body.due_date,
        assignee=body.assignee,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


class LitigationTaskPatch(BaseModel):
    title: str = ""
    due_date: str = ""
    assignee: str = ""
    status: str = ""


@router.patch("/litigation/tasks/{task_id}")
def litigation_task_patch(
    task_id: str,
    body: LitigationTaskPatch,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import update_litigation_task

    out = update_litigation_task(user["id"], task_id, body.model_dump(exclude_unset=True))
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.delete("/litigation/tasks/{task_id}")
def litigation_task_delete(task_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import delete_litigation_task

    out = delete_litigation_task(user["id"], task_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/litigation/orders")
def litigation_orders(
    matter_id: str = "",
    q: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import list_court_orders
    from ....core.platform_integrations import enrich_orders_with_drafts

    orders = list_court_orders(user["id"], matter_id=matter_id, q=q)
    return {"orders": enrich_orders_with_drafts(orders)}


class CourtOrderPatch(BaseModel):
    matter_id: str = ""
    order_type: str = ""
    title: str = ""
    order_date: str = ""
    court_name: str = ""
    judge: str = ""
    summary: str = ""
    document_id: str = ""
    tags: str = ""


@router.patch("/litigation/orders/{order_id}")
def litigation_order_patch(
    order_id: str,
    body: CourtOrderPatch,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import save_court_order

    data = body.model_dump(exclude_unset=True)
    if not data.get("matter_id"):
        from ....core.litigation_os import list_court_orders

        existing = next((o for o in list_court_orders(user["id"], limit=500) if o["order_id"] == order_id), None)
        if not existing:
            raise HTTPException(404, "Order not found")
        data["matter_id"] = existing["matter_id"]
        for k in ("order_type", "title", "order_date", "court_name", "judge", "summary", "document_id", "tags"):
            if k not in data:
                data[k] = existing.get(k, "")
    out = save_court_order(user["id"], data, order_id=order_id)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.delete("/litigation/orders/{order_id}")
def litigation_order_delete(order_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import delete_court_order

    out = delete_court_order(user["id"], order_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/litigation/limitation/deadlines")
def litigation_limitation_deadlines(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import list_firm_limitation_deadlines

    return {"deadlines": list_firm_limitation_deadlines(user["id"])}


@router.get("/litigation/notifications")
def litigation_notifications(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import get_litigation_notifications

    return get_litigation_notifications(user["id"])


class CourtOrderBody(BaseModel):
    matter_id: str
    order_type: str = "order"
    title: str = Field(..., min_length=2)
    order_date: str = ""
    court_name: str = ""
    judge: str = ""
    summary: str = ""
    document_id: str = ""
    tags: str = ""


@router.post("/litigation/orders")
def litigation_order_save(
    body: CourtOrderBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import save_court_order

    out = save_court_order(user["id"], body.model_dump())
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.get("/litigation/watchlist-dashboard")
def litigation_watchlist_dashboard(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import get_watchlist_dashboard

    return get_watchlist_dashboard(user["id"])


@router.get("/litigation/analytics")
def litigation_analytics(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import get_litigation_analytics

    return get_litigation_analytics(user["id"])


@router.get("/litigation/war-room/{matter_id}")
def litigation_war_room(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.litigation_os import get_matter_war_room

    out = get_matter_war_room(user["id"], matter_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


class LitigationAIRequest(BaseModel):
    tool: str = Field(..., description="hearing_brief, timeline, contradictions, order_summary, cross_examination, evidence_gaps")
    matter_id: str
    extra: str = ""


@router.post("/litigation/ai")
def litigation_ai(
    body: LitigationAIRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.litigation_os import run_litigation_ai

    out = run_litigation_ai(user["id"], tool=body.tool, matter_id=body.matter_id, extra=body.extra)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/public-intake")
def public_intake(
    body: PublicIntakeRequest,
    x_intake_key: str = Header(default="", alias="X-Intake-Key"),
):
    """
    Website lead capture — enable with INTAKE_PUBLIC_ENABLED=1.
    Optional X-Intake-Key header must match INTAKE_PUBLIC_KEY when set.
    """
    if os.getenv("INTAKE_PUBLIC_ENABLED", "0").lower() not in {"1", "true", "yes"}:
        raise HTTPException(403, "Public intake is disabled")
    expected = (os.getenv("INTAKE_PUBLIC_KEY") or "").strip()
    if expected and x_intake_key != expected:
        raise HTTPException(401, "Invalid intake key")
    from backend.app.core.crm_v2_service import create_lead_extended

    intake_user = (os.getenv("INTAKE_ORG_USER_ID") or os.getenv("INTAKE_DEFAULT_USER_ID") or "").strip()
    if not intake_user:
        raise HTTPException(
            503,
            "Public intake requires INTAKE_ORG_USER_ID (firm user id that owns public leads)",
        )
    classification = classify_intake_query(body.raw_intake_query, intake_user)
    follow_up = draft_follow_up_email(
        body.prospect_name,
        classification["intent"],
        classification.get("parameters") or {},
    )
    lead = create_lead_extended(
        intake_user,
        prospect_name=body.prospect_name,
        contact_email=body.contact_email,
        raw_intake_query=body.raw_intake_query,
        contact_phone=body.contact_phone,
        referral_source=(body.referral_source or "public_web").strip() or "public_web",
    )
    return {
        "received": True,
        "lead_id": lead.get("lead_id"),
        "intent": classification["intent"],
        "confidence": classification.get("confidence"),
        "parameters": classification.get("parameters"),
        "follow_up_preview": follow_up[:500],
    }
