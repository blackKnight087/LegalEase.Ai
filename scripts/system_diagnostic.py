#!/usr/bin/env python3
"""Runtime system diagnostic — writes NDJSON to debug-cf6ca9.log (session cf6ca9)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LEGACY = ROOT / "legacy_saas"
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))

LOG_PATH = ROOT / "debug-cf6ca9.log"
SESSION = "cf6ca9"


def _log(hypothesis_id: str, location: str, message: str, data: dict | None = None, run_id: str = "diag") -> None:
    # region agent log
    try:
        payload = {
            "sessionId": SESSION,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion


def _run_sqlite_mode(tmp: Path) -> None:
    os.environ["LEGALEASE_DB_PATH"] = str(tmp / "diag.db")
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SAAS_USE_POSTGRES_LEGACY", None)
    _log("A", "diag:sqlite", "env", {"db": str(tmp / "diag.db")})

    from backend.app.core.core_db import ensure_app_schemas
    from backend.app.core.legacy_db import use_postgres_legacy

    ensure_app_schemas()
    _log("A", "diag:sqlite", "postgres_legacy", {"value": use_postgres_legacy()})

    import app as app_module

    bridged = getattr(app_module.run_query, "__name__", "") == "_bridged_app_run_query"
    _log("A", "diag:sqlite", "app_run_query_bridged", {"bridged": bridged})

    from legalease_auth import create_user, authenticate_user

    uname = f"diag_{uuid.uuid4().hex[:8]}"
    create_user(uname, "testpass123", "Free", "user")
    user = authenticate_user(uname, "testpass123")
    uid = str(user["id"])
    _log("B", "diag:sqlite", "user_created", {"uid": uid[:8]})

    class _F:
        name = "test.pdf"
        def getbuffer(self):
            return memoryview(b"%PDF-1.4 minimal")

    fid, path, pages, dup = app_module.save_uploaded_pdf(_F(), uid, matter_id="")
    _log("B", "diag:sqlite", "upload", {"file_id": fid[:8], "dup": dup, "pages": pages})

    rows = app_module.run_query(
        "SELECT id, matter_id, org_id FROM documents WHERE id = ?",
        (fid,),
        fetch=True,
    )
    _log("B", "diag:sqlite", "doc_row", {"row": str(rows[0]) if rows else None})

    from backend.app.core.onboarding_service import dismiss_onboarding, get_onboarding_state

    dismiss_onboarding(uid)
    st = get_onboarding_state(uid)
    _log("C", "diag:sqlite", "onboarding", {"dismissed": st.get("dismissed")})

    from backend.app.core.kb_status_sync import sync_kb_status_from_faiss

    kb = sync_kb_status_from_faiss(uid)
    _log("D", "diag:sqlite", "kb_sync", {"ok": kb.get("ok"), "status": kb.get("status")})


def main() -> int:
    if LOG_PATH.is_file():
        LOG_PATH.unlink()
    _log("INIT", "diag:main", "start", {"root": str(ROOT)})
    tmp = Path(tempfile.mkdtemp(prefix="legalease_diag_"))
    try:
        _run_sqlite_mode(tmp)
        _log("INIT", "diag:main", "complete", {"mode": "sqlite"})
    except Exception as exc:
        _log("ERR", "diag:main", "failed", {"error": str(exc)[:500]})
        raise
    print(f"Diagnostic complete — see {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
