"""SAAS_STATUS extensions: trust, portal, esign, job queue."""
from __future__ import annotations

import json
import uuid

import pytest

from backend.app.core.matter_repo import create_matter
from backend.app.core.practice_schema import ensure_practice_schema
from backend.app.core.saas_schema import ensure_saas_schema


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "ext.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    ensure_practice_schema()
    ensure_saas_schema()
    yield


@pytest.fixture
def matter_ctx():
    uid = f"u-{uuid.uuid4().hex[:8]}"
    m = create_matter(uid, matter_name="Portal Test", practice_area="Civil")
    return uid, m["matter_id"]


def test_trust_deposit_and_transfer(matter_ctx):
    from backend.app.core.trust_service import (
        get_or_create_trust_account,
        post_trust_transaction,
    )

    uid, mid = matter_ctx
    acct = get_or_create_trust_account(uid, mid)
    assert acct["trust_balance"] == 0
    post_trust_transaction(
        uid, mid, ledger_type="TRUST", txn_type="DEPOSIT", amount=100000, narrative="Retainer"
    )
    post_trust_transaction(
        uid,
        mid,
        ledger_type="TRUST",
        txn_type="TRANSFER_TO_OPERATING",
        amount=25000,
        narrative="Fees draw",
    )
    acct2 = get_or_create_trust_account(uid, mid)
    assert acct2["trust_balance"] == 75000
    assert acct2["operating_balance"] == 25000


def test_trust_insufficient_funds(matter_ctx):
    from backend.app.core.trust_service import post_trust_transaction

    uid, mid = matter_ctx
    out = post_trust_transaction(
        uid, mid, ledger_type="TRUST", txn_type="DISBURSEMENT", amount=1, narrative="x"
    )
    assert "Insufficient" in out.get("error", "")


def test_client_portal_token(matter_ctx):
    from backend.app.core.client_portal_service import (
        create_portal_access,
        get_client_portal_view,
    )

    uid, mid = matter_ctx
    access = create_portal_access(uid, mid, "client@example.com", days_valid=7)
    assert access.get("portal_token")
    view = get_client_portal_view(access["portal_token"])
    assert view.get("matter", {}).get("matter_name") == "Portal Test"
    assert "disclaimer" in view


def test_esign_mock_request(matter_ctx):
    from backend.app.core.esign_service import create_signing_request, mark_signed

    uid, mid = matter_ctx
    req = create_signing_request(
        uid,
        document_title="NDA",
        document_body="Party A agrees...",
        signer_name="Raj",
        signer_email="raj@test.com",
        matter_id=mid,
    )
    assert req.get("sign_url")
    assert req.get("request_id")
    done = mark_signed(req["request_id"])
    assert done["status"] == "SIGNED"


def test_ediscovery_job_inline_process(matter_ctx):
    from backend.app.core.job_queue import enqueue_ediscovery_job, get_job, process_job

    uid, mid = matter_ctx
    docs = [
        {"source_identifier": "a", "text": "The ledger must be adjusted before audit next week."},
        {"source_identifier": "b", "text": "I deny knowledge of any off-book transfers."},
    ]
    enq = enqueue_ediscovery_job(uid, mid, "Batch A", docs)
    assert enq.get("job_id")
    result = process_job(enq["job_id"])
    assert result.get("batch_id") or "error" not in result
    job = get_job(enq["job_id"])
    assert job["status"] == "COMPLETED"
    assert job.get("result", {}).get("batch_id")
