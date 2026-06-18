"""Legal Conversion Engine — IPC↔BNS official dataset only."""
from __future__ import annotations

import pytest

from backend.app.core.legal_conversion_engine import (
    NOT_FOUND_MSG,
    convert_section,
    dataset_meta,
    ensure_legal_conversion_schema,
)


@pytest.fixture(autouse=True)
def _seed():
    ensure_legal_conversion_schema(force_reseed=True)


def test_meta_counts():
    m = dataset_meta()
    assert m["record_count"] == 572
    assert len(m["pairs"]) == 1
    assert m["pairs"][0]["pair_type"] == "ipc_bns"


def test_ipc_302_forward():
    r = convert_section("ipc_bns", "302", direction="forward")
    assert r["found"] is True
    assert r["new_section"] == "103"
    assert "murder" in r["old_title"].lower()


def test_bns_103_reverse():
    r = convert_section("ipc_bns", "103", direction="reverse")
    assert r["found"] is True
    assert r["old_section"] == "302"


def test_not_found():
    r = convert_section("ipc_bns", "99999", direction="forward")
    assert r["found"] is False
    assert NOT_FOUND_MSG in r["message"]


def test_unknown_pair_defaults_to_ipc():
    r = convert_section("iea_bsa", "302", direction="forward")
    assert r["found"] is True
    assert r["new_section"] == "103"
