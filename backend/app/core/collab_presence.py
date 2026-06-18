"""Collaboration presence — Redis or in-memory heartbeats."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

_PRESENCE_TTL_SEC = int(os.getenv("COLLAB_PRESENCE_TTL_SEC", "90"))
_lock = threading.Lock()
_memory: Dict[str, Dict[str, Any]] = {}
_typing: Dict[str, float] = {}
_TYPING_TTL_SEC = 8


def _redis_client():
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _key(org_id: str, user_id: str) -> str:
    return f"collab:presence:{org_id}:{user_id}"


def heartbeat(
    user_id: str,
    org_id: str,
    *,
    room_id: str = "",
    display_name: str = "",
) -> Dict[str, Any]:
    now = time.time()
    payload = {
        "user_id": user_id,
        "org_id": org_id,
        "room_id": room_id,
        "display_name": display_name,
        "last_seen": now,
    }
    r = _redis_client()
    if r:
        try:
            r.setex(
                _key(org_id, user_id),
                _PRESENCE_TTL_SEC,
                json.dumps(payload),
            )
            return {"ok": True, "backend": "redis"}
        except Exception:
            pass
    with _lock:
        _memory[_key(org_id, user_id)] = payload
    return {"ok": True, "backend": "memory"}


def list_online(org_id: str, *, room_id: str = "") -> List[Dict[str, Any]]:
    cutoff = time.time() - _PRESENCE_TTL_SEC
    out: List[Dict[str, Any]] = []
    r = _redis_client()
    if r:
        try:
            pattern = f"collab:presence:{org_id}:*"
            for key in r.scan_iter(match=pattern, count=100):
                raw = r.get(key)
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if float(item.get("last_seen", 0)) >= cutoff:
                    if room_id and item.get("room_id") != room_id:
                        continue
                    out.append(
                        {
                            "user_id": item.get("user_id"),
                            "display_name": item.get("display_name", ""),
                            "room_id": item.get("room_id", ""),
                            "online": True,
                        }
                    )
            return out
        except Exception:
            pass
    prefix = f"collab:presence:{org_id}:"
    with _lock:
        for key, item in list(_memory.items()):
            if not key.startswith(prefix):
                continue
            if float(item.get("last_seen", 0)) < cutoff:
                _memory.pop(key, None)
                continue
            if room_id and item.get("room_id") != room_id:
                continue
            out.append(
                {
                    "user_id": item.get("user_id"),
                    "display_name": item.get("display_name", ""),
                    "room_id": item.get("room_id", ""),
                    "online": True,
                }
            )
    return out


def _typing_key(org_id: str, room_id: str, user_id: str) -> str:
    return f"{org_id}:{room_id}:{user_id}"


def set_typing(
    user_id: str,
    org_id: str,
    *,
    room_id: str,
    display_name: str = "",
    typing: bool = True,
) -> Dict[str, Any]:
    if not room_id:
        return {"ok": False}
    key = _typing_key(org_id, room_id, user_id)
    now = time.time()
    r = _redis_client()
    if r and typing:
        try:
            r.setex(
                f"collab:typing:{key}",
                _TYPING_TTL_SEC,
                json.dumps({"display_name": display_name, "t": now}),
            )
            return {"ok": True}
        except Exception:
            pass
    with _lock:
        if typing:
            _typing[key] = now
        else:
            _typing.pop(key, None)
    return {"ok": True}


def list_typing(org_id: str, room_id: str, *, exclude_user_id: str = "") -> List[Dict[str, Any]]:
    cutoff = time.time() - _TYPING_TTL_SEC
    out: List[Dict[str, Any]] = []
    r = _redis_client()
    if r:
        try:
            for key in r.scan_iter(match=f"collab:typing:{org_id}:{room_id}:*", count=50):
                uid = key.split(":")[-1]
                if uid == exclude_user_id:
                    continue
                raw = r.get(key)
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if float(item.get("t", 0)) >= cutoff:
                    out.append({"user_id": uid, "display_name": item.get("display_name", uid[:8])})
            return out
        except Exception:
            pass
    with _lock:
        stale: List[str] = []
        for key, ts in list(_typing.items()):
            if not key.startswith(f"{org_id}:{room_id}:"):
                continue
            if ts < cutoff:
                stale.append(key)
                continue
            uid = key.split(":")[-1]
            if uid == exclude_user_id:
                continue
            out.append({"user_id": uid, "display_name": uid[:8]})
        for k in stale:
            _typing.pop(k, None)
    return out


def presence_for_users(org_id: str, user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    online_ids = {str(o["user_id"]) for o in list_online(org_id)}
    snap: Dict[str, Dict[str, Any]] = {}
    for uid in user_ids:
        snap[str(uid)] = {"online": str(uid) in online_ids, "last_seen": 0}
    prefix = f"collab:presence:{org_id}:"
    with _lock:
        for key, item in _memory.items():
            if not key.startswith(prefix):
                continue
            uid = str(item.get("user_id", ""))
            if uid in snap:
                snap[uid]["last_seen"] = float(item.get("last_seen", 0))
                snap[uid]["display_name"] = item.get("display_name", "")
    return snap
