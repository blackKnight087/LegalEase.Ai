"""Invoice wizard service — compute_totals, draft save/load, PDF."""
from __future__ import annotations

import uuid

import pytest

from backend.app.core.invoice_service import (
    build_invoice_prefill,
    compute_totals,
    finalize_invoice,
    get_invoice,
    render_invoice_pdf,
    save_invoice,
)
from backend.app.core.matter_repo import create_matter
from backend.app.core.practice_schema import ensure_practice_schema
from backend.app.core.saas_schema import ensure_saas_schema
from backend.app.core.billing_service import log_time_entry


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "invoice_svc.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    ensure_practice_schema()
    ensure_saas_schema()
    yield


@pytest.fixture
def matter_ctx():
    uid = f"u-{uuid.uuid4().hex[:8]}"
    m = create_matter(uid, matter_name="Invoice Test Matter", client_name="Test Client Ltd", practice_area="Criminal")
    return uid, m["matter_id"]


def _sample_payload(matter_id: str) -> dict:
    return {
        "client": {"name": "Test Client Ltd", "email": "client@test.com"},
        "matter": {"matter_id": matter_id, "matter_name": "Invoice Test Matter"},
        "billing": {
            "invoice_number": "LE-2026-0001",
            "invoice_date": "2026-06-01",
            "due_date": "2026-07-01",
            "currency": "INR",
            "billing_type": "Hourly",
        },
        "services": [
            {"date": "2026-06-01", "description": "Legal research", "hours": 2, "rate": 5000, "amount": 10000},
            {"date": "2026-06-02", "description": "Drafting", "hours": 1, "rate": 5000, "amount": 5000},
        ],
        "expenses": [{"description": "Court fees", "amount": 2000, "taxable": True}],
        "taxes": {"gst_percent": 18, "tax_exempt": False, "intra_state": True},
        "retainer": {"current_retainer": 5000, "apply_amount": 2000},
        "payment": {"firm_name": "Test Chambers"},
        "notes": "Professional services rendered.",
        "record_ids": [],
    }


def test_compute_totals_gst_intra_state(matter_ctx):
    _, mid = matter_ctx
    payload = _sample_payload(mid)
    totals = compute_totals(payload)
    assert totals["services_subtotal"] == 15000.0
    assert totals["expenses_subtotal"] == 2000.0
    assert totals["subtotal"] == 17000.0
    assert totals["taxable_amount"] == 17000.0
    assert totals["tax_amount"] == 3060.0
    assert totals["cgst"] == 1530.0
    assert totals["sgst"] == 1530.0
    assert totals["igst"] == 0.0
    assert totals["grand_total"] == 20060.0
    assert totals["retainer_applied"] == 2000.0
    assert totals["balance_due"] == 18060.0


def test_compute_totals_igst_inter_state(matter_ctx):
    _, mid = matter_ctx
    payload = _sample_payload(mid)
    payload["taxes"]["intra_state"] = False
    totals = compute_totals(payload)
    assert totals["igst"] == totals["tax_amount"]
    assert totals["cgst"] == 0.0
    assert totals["sgst"] == 0.0


def test_compute_totals_tax_exempt(matter_ctx):
    _, mid = matter_ctx
    payload = _sample_payload(mid)
    payload["taxes"]["tax_exempt"] = True
    totals = compute_totals(payload)
    assert totals["tax_amount"] == 0.0
    assert totals["grand_total"] == 17000.0


def test_draft_save_and_load(matter_ctx):
    uid, mid = matter_ctx
    payload = _sample_payload(mid)
    saved = save_invoice(uid, payload, status="DRAFT")
    assert saved.get("invoice_id")
    assert saved["status"] == "DRAFT"
    loaded = get_invoice(uid, saved["invoice_id"])
    assert loaded is not None
    assert loaded["client_name"] == "Test Client Ltd"
    assert loaded["payload"]["billing"]["invoice_number"] == "LE-2026-0001"
    assert loaded["balance_due"] == saved["balance_due"]


def test_prefill_from_unbilled_entries(matter_ctx):
    uid, mid = matter_ctx
    log_time_entry(uid, matter_id=mid, raw_activity="Bail research", units_logged=2, rate_per_unit=5000)
    out = build_invoice_prefill(uid, mid)
    assert "payload" in out
    assert len(out["payload"]["services"]) >= 1
    assert out["payload"]["billing"]["invoice_number"].startswith("LE-")


def test_finalize_marks_entries_billed(matter_ctx):
    uid, mid = matter_ctx
    entry = log_time_entry(uid, matter_id=mid, raw_activity="Hearing prep", units_logged=1, rate_per_unit=3000)
    pre = build_invoice_prefill(uid, mid)
    pre["payload"]["record_ids"] = [entry["record_id"]]
    saved = save_invoice(uid, pre["payload"], status="DRAFT")
    fin = finalize_invoice(uid, saved["invoice_id"])
    assert fin["status"] == "GENERATED"


def test_render_pdf_bytes(matter_ctx):
    uid, mid = matter_ctx
    saved = save_invoice(uid, _sample_payload(mid), status="DRAFT")
    pdf_bytes, filename = render_invoice_pdf(uid, saved["invoice_id"])
    assert pdf_bytes[:4] == b"%PDF"
    assert filename.endswith(".pdf")
    try:
        import fitz

        text = fitz.open(stream=pdf_bytes, filetype="pdf")[0].get_text()
        assert "LegalEase" in text and ".Ai" in text
        assert "Chambers" not in text
    except ImportError:
        pass
