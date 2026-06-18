"""Phase 4 e-discovery & research — rigorous parametrize tests."""
from __future__ import annotations

import uuid

import pytest

from backend.app.core.matter_repo import create_matter
from backend.app.core.practice_schema import ensure_practice_schema
from backend.app.core.saas_schema import ensure_saas_schema
from backend.app.core.ediscovery_service import (
    create_batch,
    review_item,
    search_batch,
    triage_document,
)
from backend.app.core.research_service import (
    expand_research_query,
    log_research_query,
    record_research_feedback,
)

DISCOVERY_TEXTS = [
    (
        "Make sure the ledger adjustments are committed before regulators review Q3.",
        "RELEVANT_HIGH",
        "FINANCIAL_FRAUD",
    ),
    (
        "I was not aware of any policy violation; compliance signed off on the transfer.",
        "RELEVANT_HIGH",
        "EXCULPATORY",
    ),
    (
        "I heard someone say the director might have known.",
        "RELEVANT_MEDIUM",
        "HEARSAY_INADMISSIBLE",
    ),
    (
        "This email is attorney-client privileged legal advice only.",
        "RELEVANT_HIGH",
        "PRIVILEGE_RISK",
    ),
    (
        "Please confirm indemnity cap under the SPA before signing.",
        "RELEVANT_MEDIUM",
        "CONTRACT_BREACH",
    ),
]

RESEARCH_QUERIES = [
    "What can I do if a vendor takes my money and runs away?",
    "Need bail after FIR for cheating",
    "Contract was broken need damages",
    "Murder charge what are defenses",
]


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "p4.db"))
    ensure_practice_schema()
    ensure_saas_schema()


@pytest.fixture
def matter_ctx():
    uid = f"u-{uuid.uuid4().hex[:8]}"
    m = create_matter(uid, matter_name="Discovery Matter", practice_area="Corporate")
    return uid, m["matter_id"]


@pytest.mark.parametrize("text,expected_class,expected_tag", DISCOVERY_TEXTS)
def test_triage_tags(text, expected_class, expected_tag):
    out = triage_document(text)
    assert out["classification"] == expected_class
    assert expected_tag in (out.get("tags") or [])


@pytest.mark.parametrize("text,_,__", DISCOVERY_TEXTS[:3])
def test_batch_ingest(text, _, __, matter_ctx):
    uid, mid = matter_ctx
    batch = create_batch(
        uid,
        mid,
        "Test Batch",
        [{"source_identifier": "email@test", "text": text}],
    )
    assert batch.get("batch_id")
    assert len(batch["items"]) == 1
    assert batch["items"][0]["relevance_score"] >= 0.5


def test_review_boosts_search(matter_ctx):
    uid, mid = matter_ctx
    text = DISCOVERY_TEXTS[0][0]
    batch = create_batch(uid, mid, "Review Batch", [{"source_identifier": "e1", "text": text}])
    item_id = batch["items"][0]["item_id"]
    review_item(uid, item_id, tags=["FINANCIAL_FRAUD"], classification="RELEVANT_HIGH")
    results = search_batch(uid, batch["batch_id"], "ledger", min_score=0.5)
    assert len(results) >= 1


@pytest.mark.parametrize("query", RESEARCH_QUERIES)
def test_research_expansion(query):
    out = expand_research_query(query)
    assert len(out["expanded_queries"]) >= 2
    assert out["raw_search_term"] == query


@pytest.mark.parametrize("query", RESEARCH_QUERIES)
def test_research_log_and_feedback(query, matter_ctx):
    uid, mid = matter_ctx
    logged = log_research_query(uid, query, matter_id=mid, selected_mode="HYBRID")
    assert logged.get("query_id")
    assert len(logged["expanded_queries"]) >= 2
    fb = record_research_feedback(
        uid,
        logged["query_id"],
        1,
        rephrased_query="Section 318 BNS cheating India",
    )
    assert fb.get("recorded")
