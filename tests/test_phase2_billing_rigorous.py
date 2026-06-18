"""Phase 2 billing — rigorous parametrize tests."""
from __future__ import annotations

import os
import uuid

import pytest

from backend.app.core.matter_repo import create_matter
from backend.app.core.practice_schema import ensure_practice_schema
from backend.app.core.saas_schema import ensure_saas_schema
from backend.app.core.billing_service import (
    billing_summary,
    generate_invoice,
    list_time_entries,
    log_time_entry,
    polish_billing_narrative,
    record_lexicon_correction,
)

RAW_ACTIVITIES = [
    "Looked at section 437 bail rules for 2 hours",
    "Research on IPC 302 murder elements",
    "Drafted contract breach notice",
    "Court hearing preparation",
    "Reviewed police case diary",
    "Client conference on BNS 111",
]
RATES = [2500.0, 5000.0, 7500.0, 10000.0]
UNITS = [0.5, 1.0, 1.5, 2.0, 3.0]


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "billing.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    ensure_practice_schema()
    ensure_saas_schema()
    yield


@pytest.fixture
def matter_id():
    uid = f"u-{uuid.uuid4().hex[:8]}"
    m = create_matter(uid, matter_name="Test Matter", practice_area="Criminal")
    return uid, m["matter_id"]


@pytest.mark.parametrize("raw", RAW_ACTIVITIES)
def test_polish_narrative_produces_professional_text(raw, matter_id):
    uid, _ = matter_id
    n = polish_billing_narrative(uid, raw, units=2.0)
    assert len(n) > 40
    assert "hour" in n.lower() or "hours" in n.lower() or "devoted" in n.lower()


@pytest.mark.parametrize("raw", RAW_ACTIVITIES[:4])
@pytest.mark.parametrize("units", UNITS[:3])
@pytest.mark.parametrize("rate", RATES[:2])
def test_log_time_entry_amount(raw, units, rate, matter_id):
    uid, mid = matter_id
    out = log_time_entry(
        uid,
        matter_id=mid,
        raw_activity=raw,
        units_logged=units,
        rate_per_unit=rate,
    )
    assert out.get("record_id")
    assert out["amount"] == round(units * rate, 2)
    assert "error" not in out


@pytest.mark.parametrize("raw", RAW_ACTIVITIES[:3])
def test_lexicon_correction_reuse(raw, matter_id):
    uid, _ = matter_id
    custom = (
        "Devoted 2.00 hours to comprehensive statutory analysis under Section 437 BNSS."
    )
    record_lexicon_correction(uid, raw, custom)
    n2 = polish_billing_narrative(uid, raw, units=2.0)
    assert custom[:40] in n2 or n2 == custom


def test_invoice_generation_inr(matter_id):
    uid, mid = matter_id
    log_time_entry(uid, matter_id=mid, raw_activity="Bail research", units_logged=2, rate_per_unit=5000)
    log_time_entry(uid, matter_id=mid, raw_activity="Filing draft", units_logged=1, rate_per_unit=5000)
    inv = generate_invoice(uid, mid, client_name="ABC Client", tax_rate=0.18)
    assert inv.get("invoice_id")
    assert inv["subtotal"] == 15000.0
    assert inv["tax_amount"] == 2700.0
    assert inv["total"] == 17700.0
    assert len(inv["line_items"]) == 2
    entries = list_time_entries(uid, matter_id=mid, invoice_status="BILLED")
    assert len(entries) == 2


def test_billing_summary(matter_id):
    uid, mid = matter_id
    log_time_entry(uid, matter_id=mid, raw_activity="Work", units_logged=1, rate_per_unit=1000)
    s = billing_summary(uid)
    assert s["unbilled_entries"] >= 1
    assert s["unbilled_amount_inr"] >= 1000
