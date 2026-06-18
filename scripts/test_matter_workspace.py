#!/usr/bin/env python3
"""Regression tests for matter workspace isolation and enhancements."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_resolve_rag_fail_closed():
    from backend.app.core.matter_index import resolve_rag_index_dir

    try:
        resolve_rag_index_dir("test-user", "nonexistent-matter", require_matter_scope=True)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    print("ok: require_matter_scope")


def test_schema_tables():
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from backend.app.core.database import connect_sqlite

    conn = connect_sqlite()
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    for t in (
        "matter_timeline_suggestions",
        "matter_audit_log",
        "matter_members",
    ):
        assert t in tables, f"missing {t}"
    print("ok: enhancement tables")


def test_timeline_suggestion_flow():
    from backend.app.core.matter_repo import create_matter, delete_matter
    from backend.app.core.matter_enhancements import (
        add_timeline_suggestion,
        approve_timeline_suggestion,
        list_timeline_suggestions,
    )
    from backend.app.core.matter_workflow import list_timeline

    uid = "test-user-matter-ws"
    m = create_matter(uid, matter_name="Test Matter WS")
    mid = m["matter_id"]
    sid = add_timeline_suggestion(mid, title="Test event", event_date="2024-01-01")
    pending = list_timeline_suggestions(uid, mid)
    assert any(p["suggestion_id"] == sid for p in pending)
    assert approve_timeline_suggestion(uid, mid, sid)
    assert list_timeline(uid, mid)
    delete_matter(uid, mid)
    print("ok: timeline suggestions")


if __name__ == "__main__":
    test_resolve_rag_fail_closed()
    test_schema_tables()
    test_timeline_suggestion_flow()
    print("All matter workspace tests passed.")
