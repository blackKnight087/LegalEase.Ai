"""Phase 2 — Billing & time tracking API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.billing_service import (
    billing_summary,
    generate_invoice,
    list_time_entries,
    log_time_entry,
    polish_billing_narrative,
    record_lexicon_correction,
)
from ....core.invoice_service import (
    INVOICE_STATUSES,
    build_invoice_prefill,
    compute_totals,
    finalize_invoice,
    get_invoice,
    list_invoices,
    render_invoice_pdf,
    save_invoice,
    update_invoice_status,
)
from ....core.practice_billing_service import (
    EXPENSE_TYPES,
    billing_reports,
    billing_workspace,
    bulk_import_time_entries,
    collections_dashboard,
    create_expense,
    delete_expense,
    delete_time_entry,
    duplicate_time_entry,
    list_expenses,
    matter_billing_profile,
    matter_financial_summary,
    save_matter_billing_meta,
    update_time_entry,
)
from ....core.saas_schema import ensure_saas_schema

router = APIRouter(tags=["billing"])


class TimeEntryCreate(BaseModel):
    matter_id: str
    raw_activity: str = Field(..., min_length=3)
    units_logged: float = Field(..., gt=0)
    rate_per_unit: float = Field(..., gt=0)
    billing_type: str = "HOURLY"


class NarrativePolish(BaseModel):
    raw_activity: str
    units_logged: float = 1.0
    matter_id: str = ""


class LexiconCorrection(BaseModel):
    raw_activity: str
    polished_narrative: str = Field(..., min_length=10)


class InvoiceCreate(BaseModel):
    matter_id: str
    client_name: str = ""
    tax_rate: float = 0.18
    record_ids: Optional[List[str]] = None


class InvoicePayloadBody(BaseModel):
    payload: Dict[str, Any]
    invoice_id: Optional[str] = None
    status: str = "DRAFT"


class InvoiceStatusPatch(BaseModel):
    status: str


class TimeEntryUpdate(BaseModel):
    raw_activity: Optional[str] = None
    units_logged: Optional[float] = None
    rate_per_unit: Optional[float] = None
    narrative_description: Optional[str] = None


class ExpenseCreate(BaseModel):
    matter_id: str
    expense_date: str = ""
    expense_type: str = "Miscellaneous"
    description: str = Field(..., min_length=2)
    amount: float = Field(..., gt=0)
    billable: bool = True


class MatterBillingMeta(BaseModel):
    client_email: str = ""
    client_phone: str = ""
    client_address: str = ""
    client_gst: str = ""
    client_company: str = ""
    matter_number: str = ""
    assigned_lawyers: str = ""
    payment: Optional[Dict[str, Any]] = None


class BulkTimeImport(BaseModel):
    entries: List[Dict[str, Any]]


@router.get("/workspace")
def billing_workspace_route(
    matter_id: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return billing_workspace(
        user["id"],
        matter_id,
        username=user.get("username", ""),
    )


@router.get("/summary")
def billing_summary_route(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    return collections_dashboard(user["id"])


@router.get("/collections")
def billing_collections_route(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    return collections_dashboard(user["id"])


@router.get("/matter/{matter_id}/profile")
def matter_profile_route(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    out = matter_billing_profile(user["id"], matter_id, username=user.get("username", ""))
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.put("/matter/{matter_id}/profile")
def matter_profile_save(
    matter_id: str,
    body: MatterBillingMeta,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = save_matter_billing_meta(user["id"], matter_id, body.model_dump())
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/matter/{matter_id}/financials")
def matter_financials_route(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    out = matter_financial_summary(user["id"], matter_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/entries")
def billing_entries(
    matter_id: str = "",
    invoice_status: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return {"entries": list_time_entries(user["id"], matter_id=matter_id, invoice_status=invoice_status)}


@router.put("/entries/{record_id}")
def billing_update_entry(
    record_id: str,
    body: TimeEntryUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = update_time_entry(
        user["id"],
        record_id,
        raw_activity=body.raw_activity,
        units_logged=body.units_logged,
        rate_per_unit=body.rate_per_unit,
        narrative_description=body.narrative_description,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.delete("/entries/{record_id}")
def billing_delete_entry(record_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    out = delete_time_entry(user["id"], record_id)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/entries/{record_id}/duplicate")
def billing_duplicate_entry(record_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    out = duplicate_time_entry(user["id"], record_id)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/entries/bulk")
def billing_bulk_entries(
    body: BulkTimeImport,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return bulk_import_time_entries(user["id"], body.entries)


@router.get("/expenses")
def billing_list_expenses(
    matter_id: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return {"expenses": list_expenses(user["id"], matter_id=matter_id), "expense_types": list(EXPENSE_TYPES)}


@router.post("/expenses")
def billing_create_expense(
    body: ExpenseCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = create_expense(
        user["id"],
        matter_id=body.matter_id,
        expense_date=body.expense_date,
        expense_type=body.expense_type,
        description=body.description,
        amount=body.amount,
        billable=body.billable,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.delete("/expenses/{expense_id}")
def billing_delete_expense(expense_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    return delete_expense(user["id"], expense_id)


@router.get("/reports/{report_type}")
def billing_report_route(report_type: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    return billing_reports(user["id"], report=report_type.replace("-", "_"))


@router.post("/entries")
def billing_log_entry(
    body: TimeEntryCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = log_time_entry(
        user["id"],
        matter_id=body.matter_id,
        raw_activity=body.raw_activity,
        units_logged=body.units_logged,
        rate_per_unit=body.rate_per_unit,
        billing_type=body.billing_type,
    )
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/narrative/preview")
def billing_narrative_preview(
    body: NarrativePolish,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    ctx = ""
    if body.matter_id:
        from ....core.matter_repo import get_matter

        m = get_matter(user["id"], body.matter_id)
        if m:
            ctx = f"{m.get('practice_area')} {m.get('matter_name')}"
    return {
        "narrative": polish_billing_narrative(
            user["id"],
            body.raw_activity,
            units=body.units_logged,
            matter_context=ctx,
        )
    }


@router.post("/narrative/correct")
def billing_narrative_correct(
    body: LexiconCorrection,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return record_lexicon_correction(
        user["id"], body.raw_activity, body.polished_narrative
    )


# ---------- Invoice wizard endpoints ----------

@router.get("/invoices/prefill")
def invoice_prefill(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    if not matter_id:
        raise HTTPException(400, "matter_id required")
    out = build_invoice_prefill(user["id"], matter_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/invoices")
def invoice_list(
    matter_id: str = "",
    status: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return {"invoices": list_invoices(user["id"], matter_id=matter_id, status=status)}


@router.get("/invoices/{invoice_id}")
def invoice_get(
    invoice_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    inv = get_invoice(user["id"], invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.post("/invoices/draft")
def invoice_save_draft(
    body: InvoicePayloadBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    status = body.status if body.status in INVOICE_STATUSES else "DRAFT"
    out = save_invoice(
        user["id"],
        body.payload,
        invoice_id=body.invoice_id,
        status=status,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.put("/invoices/{invoice_id}")
def invoice_update(
    invoice_id: str,
    body: InvoicePayloadBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    status = body.status if body.status in INVOICE_STATUSES else "DRAFT"
    out = save_invoice(
        user["id"],
        body.payload,
        invoice_id=invoice_id,
        status=status,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/invoices/{invoice_id}/finalize")
def invoice_finalize(
    invoice_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = finalize_invoice(user["id"], invoice_id)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(
    invoice_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    try:
        pdf_bytes, filename = render_invoice_pdf(user["id"], invoice_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/invoices/{invoice_id}/status")
def invoice_status_patch(
    invoice_id: str,
    body: InvoiceStatusPatch,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = update_invoice_status(user["id"], invoice_id, body.status)
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@router.post("/invoices/compute-totals")
def invoice_compute_totals(
    body: InvoicePayloadBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return {"totals": compute_totals(body.payload)}


# Legacy SaaS subscription paths (avoid second router on /billing)
@router.get("/plans")
def legacy_subscription_plans():
    from ....core.payment_service import billing_public_config

    return billing_public_config()


@router.get("/payments")
def legacy_subscription_payments(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.payment_service import billing_public_config, list_payment_history

    return {"payments": list_payment_history(str(user["id"])), **billing_public_config()}


@router.get("/status")
def legacy_subscription_status(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.payment_service import billing_public_config

    return {"membership": user.get("membership", "Free"), **billing_public_config()}


@router.post("/invoices")
def billing_create_invoice(
    body: InvoiceCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Legacy one-click invoice — still supported."""
    ensure_saas_schema()
    out = generate_invoice(
        user["id"],
        body.matter_id,
        client_name=body.client_name,
        tax_rate=body.tax_rate,
        record_ids=body.record_ids,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out
