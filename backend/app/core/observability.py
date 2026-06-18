from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any, Dict

_log = logging.getLogger("legalease.observability")

OBSERVABILITY_WEBHOOK_URL = os.getenv("OBSERVABILITY_WEBHOOK_URL", "").strip()
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "").strip() or os.getenv(
    "NEXT_PUBLIC_POSTHOG_KEY", ""
).strip()
POSTHOG_HOST = (
    os.getenv("POSTHOG_HOST", "").strip()
    or os.getenv("NEXT_PUBLIC_POSTHOG_HOST", "https://us.i.posthog.com").strip()
).rstrip("/")


def emit_event(name: str, **data: Any) -> None:
    payload: Dict[str, Any] = {
        "event": name,
        "ts_ms": int(time.time() * 1000),
        **data,
    }
    try:
        _log.info(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass
    _ship_webhook(payload)
    _ship_posthog(name, data)


def _ship_posthog(event: str, data: Dict[str, Any]) -> None:
    if not POSTHOG_API_KEY:
        return
    try:
        distinct = str(data.get("user_id") or data.get("request_user_id") or "server")
        body = {
            "api_key": POSTHOG_API_KEY,
            "event": event,
            "properties": {"distinct_id": distinct, **data, "$lib": "legalease-api"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        req = urllib.request.Request(
            f"{POSTHOG_HOST}/capture/",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def _ship_webhook(payload: Dict[str, Any]) -> None:
    url = OBSERVABILITY_WEBHOOK_URL
    if not url:
        return
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass
