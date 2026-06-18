"""Phase 1 practice management — matters, templates, clauses."""
from __future__ import annotations

import os
import tempfile
import uuid

import pytest


@pytest.fixture
def practice_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("LEGALEASE_DB_PATH", path)
    from backend.app.core.practice_schema import (
        ensure_practice_schema,
        seed_builtin_templates_if_empty,
        seed_default_clauses_if_empty,
    )

    ensure_practice_schema()
    seed_builtin_templates_if_empty()
    seed_default_clauses_if_empty()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_create_matter_and_note(practice_db):
    from backend.app.core.matter_repo import (
        add_matter_note,
        create_matter,
        get_matter,
        list_matter_notes,
    )

    uid = f"u-{uuid.uuid4().hex[:8]}"
    m = create_matter(
        uid,
        matter_name="State v. Kumar",
        practice_area="Criminal",
        case_number="CR/102/2025",
        venue="Sessions Court, Kolkata",
    )
    assert m["matter_id"]
    assert m["practice_area"] == "Criminal"
    note = add_matter_note(uid, m["matter_id"], "Filed bail application under BNSS 483.")
    assert note
    notes = list_matter_notes(uid, m["matter_id"])
    assert len(notes) == 1
    full = get_matter(uid, m["matter_id"])
    assert full is not None


def test_template_render(practice_db):
    from backend.app.core.clause_repo import create_template, list_templates, render_template

    uid = f"u-{uuid.uuid4().hex[:8]}"
    tpls = list_templates(uid)
    assert len(tpls) >= 1
    tid = tpls[0]["template_id"]
    out = render_template(uid, tid, {"police_station": "Park Street", "district": "Kolkata"})
    assert "rendered" in out
    assert isinstance(out["missing_variables"], list)

    custom = create_template(
        uid,
        template_name="Test Notice",
        practice_area="Civil",
        raw_markdown_structure="Dear {CLIENT_NAME}, matter {CASE_NO}.",
        variable_json_map=["CLIENT_NAME", "CASE_NO"],
    )
    assert custom["template_id"]
    gen = render_template(
        uid,
        custom["template_id"],
        {"CLIENT_NAME": "ABC Ltd", "CASE_NO": "12/2025"},
    )
    assert "ABC Ltd" in gen["rendered"]
    assert gen["missing_variables"] == []


def test_clause_confidence_feedback(practice_db):
    from backend.app.core.clause_repo import (
        list_clauses,
        record_clause_edit_delta,
        upsert_clause,
    )

    uid = f"u-{uuid.uuid4().hex[:8]}"
    upsert_clause(
        uid,
        clause_tag="TEST_CAP",
        clause_text_content="Liability capped at fees paid.",
        practice_area="Corporate",
    )
    before = list_clauses(uid, tag="TEST_CAP")[0]["confidence_weight"]
    record_clause_edit_delta(
        uid,
        baseline="Generic vendor-only cap.",
        accepted="Mutual cap limited to 12-month fees paid.",
        clause_tag="TEST_CAP",
    )
    after = list_clauses(uid, tag="TEST_CAP")[0]["confidence_weight"]
    assert after >= before


def test_matter_workflow_signal_no_crash(practice_db):
    from backend.app.core.matter_repo import create_matter, matter_workflow_signal

    uid = f"u-{uuid.uuid4().hex[:8]}"
    m = create_matter(uid, matter_name="BNS 111 Org Crime", practice_area="Criminal")
    matter_workflow_signal(uid, m, "Prepare charge-sheet review checklist.")
