"""
Shared session store — Redis when REDIS_URL is set, else in-process memory.

Enables multiple Uvicorn workers behind nginx without losing conversation state.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SESSION_TTL_SEC = int(os.getenv("SESSION_TTL_SEC", "86400"))
_MEMORY: Dict[str, Dict[str, Any]] = {}
_redis_client = None
_redis_checked = False


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "").strip()


def _get_redis():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    url = _redis_url()
    if not url:
        return None
    try:
        import redis  # type: ignore

        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        logger.info("Session store: Redis at %s", url.split("@")[-1])
        return _redis_client
    except Exception as e:
        logger.warning("Redis unavailable (%s); using in-memory sessions", e)
        _redis_client = None
        return None


def _key(session_id: str) -> str:
    return f"legalease:session:{session_id}"


def get_session(session_id: str) -> Dict[str, Any]:
    r = _get_redis()
    if r:
        raw = r.get(_key(session_id))
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return {"history": [], "state": {}}
    return _MEMORY.get(session_id, {"history": [], "state": {}})


def set_session(session_id: str, data: Dict[str, Any]) -> None:
    r = _get_redis()
    if r:
        r.setex(_key(session_id), _SESSION_TTL_SEC, json.dumps(data))
        return
    _MEMORY[session_id] = data


def delete_session(session_id: str) -> None:
    r = _get_redis()
    if r:
        r.delete(_key(session_id))
        return
    _MEMORY.pop(session_id, None)


def backend_name() -> str:
    return "redis" if _get_redis() else "memory"
