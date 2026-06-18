#!/usr/bin/env python3
"""Full matter API integration test (no HTTP — direct imports)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = ROOT / "debug-cf6ca9.log"


def _log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    import time

    line = json.dumps(
        {
            "sessionId": "cf6ca9",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
            "runId": "api-full",
        }
    )
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    from backend.app.core.practice_schema import ensure_practice_schema
    from backend.app.core.matter_repo import create_matter, delete_matter, list_matter_documents
    from backend.app.core.matter_workflow import get_matter_dashboard
    from backend.app.core.matter_enhancements import (
        add_timeline_suggestion,
        get_matter_notifications,
        list_matter_audit,
        list_timeline_suggestions,
        log_matter_audit,
    )

    ensure_practice_schema()
    uid = "matter-api-full-test"
    m = create_matter(uid, matter_name="API Full Test Matter")
    mid = m["matter_id"]
    _log("H1", "test_matter_api_full:created", "matter_created", {"matter_id": mid})

    docs = list_matter_documents(uid, mid)
    _log("H1", "test_matter_api_full:docs", "list_matter_documents", {"count": len(docs), "sample": docs[:1]})

    dash = get_matter_dashboard(uid, mid)
    assert dash.get("matter"), "dashboard missing matter"
    _log("H2", "test_matter_api_full:dash", "dashboard_keys", {"keys": list(dash.keys())})

    sid = add_timeline_suggestion(mid, title="Evt", event_date="2024-06-01")
    pending = list_timeline_suggestions(uid, mid)
    assert any(p["suggestion_id"] == sid for p in pending), "suggestion missing"
    _log("H3", "test_matter_api_full:suggestions", "suggestions_ok", {"count": len(pending)})

    notifs = get_matter_notifications(uid)
    _log("H4", "test_matter_api_full:notifs", "notifications", {"count": len(notifs)})

    log_matter_audit(uid, mid, "test", "integration")
    audit = list_matter_audit(uid, mid)
    assert audit, "audit empty"
    _log("H5", "test_matter_api_full:audit", "audit_ok", {"count": len(audit)})

    delete_matter(uid, mid)
    _log("H5", "test_matter_api_full:cleanup", "deleted", {"matter_id": mid})
    print("All matter API full tests passed.")


if __name__ == "__main__":
    main()
