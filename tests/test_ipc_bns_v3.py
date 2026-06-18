"""IPC-BNS V3 engine — deterministic lookups, no hallucinated mappings."""
from __future__ import annotations

import pytest

from backend.app.core.ipc_bns_engine_v3 import (
    NOT_FOUND_MSG,
    bulk_convert_ipc,
    extract_ipc_sections,
    lookup_ipc,
    normalize_ipc_key,
    search_mappings,
)


@pytest.fixture(autouse=True)
def _seed_db():
    from backend.app.core.ipc_bns_engine_v3 import ensure_ipc_bns_schema

    ensure_ipc_bns_schema()


def test_normalize_ipc():
    assert normalize_ipc_key("IPC 302") == "302"
    assert normalize_ipc_key("304A") == "304A"


def test_mapped_section_302():
    r = lookup_ipc("302")
    assert r["found"] is True
    assert r["status"] == "mapped"
    assert "103" in str(r.get("bns_key") or r.get("bns_section"))


def test_unmapped_returns_message():
    r = lookup_ipc("99999")
    assert r["found"] is False
    assert NOT_FOUND_MSG in str(r.get("message"))


def test_search_murder_keyword():
    r = search_mappings("murder")
    assert r["count"] >= 1
    assert any("murder" in str(x.get("short_description", "")).lower() for x in r["results"])


def test_extract_sections_from_fir_text():
    text = "FIR under IPC Section 302 and u/s 420 IPC against accused."
    secs = extract_ipc_sections(text)
    assert "302" in secs
    assert "420" in secs


def test_bulk_convert():
    r = bulk_convert_ipc(["302", "99999"])
    assert r["total"] == 2
    assert r["mapped_count"] == 1
    assert r["unmapped_count"] == 1
