"""NDJSON debug logging for agent debug sessions (session c6a094)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

_LOG_PATH = Path(__file__).resolve().parents[3] / "debug-c6a094.log"
_SESSION = "c6a094"


def debug_log(
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
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion
