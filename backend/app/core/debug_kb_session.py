"""NDJSON debug logger for KB follow-up / routing (session 4f89f0)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

_LOG = Path(__file__).resolve().parents[2] / "debug-4f89f0.log"
_SESSION = "4f89f0"


def dbg_kb(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    *,
    run_id: str = "pre-fix",
) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": _SESSION,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
            "runId": run_id,
        }
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion
