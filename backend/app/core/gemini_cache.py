"""Short-lived cache for Gemini Open Law / jurisprudence responses (same API key, same query)."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

_CACHE_TTL_SEC = int(os.getenv("GEMINI_CACHE_TTL_SEC", "3600"))
_MAX_ENTRIES = int(os.getenv("GEMINI_CACHE_MAX_ENTRIES", "64"))

_lock = threading.Lock()
_store: Dict[str, Tuple[float, Any]] = {}


def _normalize_query(query: str) -> str:
    return " ".join((query or "").lower().split())


def _cache_key(kind: str, query: str, user_id: str = "") -> str:
    raw = f"{kind}|{user_id}|{_normalize_query(query)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_gemini_result(
    kind: str,
    query: str,
    *,
    user_id: str = "",
) -> Optional[Any]:
    if _CACHE_TTL_SEC <= 0:
        return None
    key = _cache_key(kind, query, user_id=user_id)
    now = time.time()
    with _lock:
        row = _store.get(key)
        if not row:
            return None
        ts, value = row
        if now - ts > _CACHE_TTL_SEC:
            _store.pop(key, None)
            return None
        return value


def set_cached_gemini_result(
    kind: str,
    query: str,
    value: Any,
    *,
    user_id: str = "",
) -> None:
    if _CACHE_TTL_SEC <= 0:
        return
    key = _cache_key(kind, query, user_id=user_id)
    with _lock:
        if len(_store) >= _MAX_ENTRIES:
            oldest = min(_store.items(), key=lambda item: item[1][0])
            _store.pop(oldest[0], None)
        _store[key] = (time.time(), value)


def clear_gemini_cache() -> int:
    with _lock:
        n = len(_store)
        _store.clear()
        return n
