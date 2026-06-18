"""Firm Chat realtime hub — WebSocket fan-out for messages, typing, presence, notifications."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, DefaultDict, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("legalease.collab.realtime")

_hub: Optional["CollabRealtimeHub"] = None
_broadcast_queue: Optional[asyncio.Queue] = None


class CollabRealtimeHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._by_room: DefaultDict[str, Set[WebSocket]] = defaultdict(set)
        self._by_user: DefaultDict[str, Set[WebSocket]] = defaultdict(set)
        self._meta: Dict[WebSocket, Dict[str, str]] = {}

    async def connect(self, ws: WebSocket, user_id: str, org_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self._by_user[user_id].add(ws)
            self._meta[ws] = {"user_id": user_id, "org_id": org_id, "room_id": ""}

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            meta = self._meta.pop(ws, None)
            if not meta:
                return
            uid = meta.get("user_id", "")
            rid = meta.get("room_id", "")
            self._by_user.get(uid, set()).discard(ws)
            if rid:
                self._by_room.get(rid, set()).discard(ws)

    async def subscribe_room(self, ws: WebSocket, room_id: str) -> None:
        async with self._lock:
            meta = self._meta.get(ws)
            if not meta:
                return
            old = meta.get("room_id", "")
            if old and old != room_id:
                self._by_room.get(old, set()).discard(ws)
            meta["room_id"] = room_id
            if room_id:
                self._by_room[room_id].add(ws)

    async def _send(self, ws: WebSocket, payload: Dict[str, Any]) -> bool:
        try:
            await ws.send_text(json.dumps(payload, default=str))
            return True
        except Exception:
            return False

    async def broadcast_room(self, room_id: str, payload: Dict[str, Any]) -> int:
        if not room_id:
            return 0
        async with self._lock:
            targets = list(self._by_room.get(room_id, set()))
        sent = 0
        dead: list[WebSocket] = []
        for ws in targets:
            if await self._send(ws, payload):
                sent += 1
            else:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
        return sent

    async def notify_user(self, user_id: str, payload: Dict[str, Any]) -> int:
        async with self._lock:
            targets = list(self._by_user.get(user_id, set()))
        sent = 0
        for ws in targets:
            if await self._send(ws, payload):
                sent += 1
        return sent

    def stats(self) -> Dict[str, Any]:
        return {
            "rooms": len(self._by_room),
            "connections": len(self._meta),
            "users": len(self._by_user),
        }


def get_hub() -> CollabRealtimeHub:
    global _hub
    if _hub is None:
        _hub = CollabRealtimeHub()
    return _hub


def enqueue_broadcast(room_id: str, payload: Dict[str, Any]) -> None:
    """Thread-safe enqueue from sync route handlers."""
    q = _broadcast_queue
    if q is None:
        return
    try:
        q.put_nowait((room_id, payload))
    except asyncio.QueueFull:
        logger.warning("collab broadcast queue full, dropping event")


def enqueue_user_notify(user_id: str, payload: Dict[str, Any]) -> None:
    q = _broadcast_queue
    if q is None:
        return
    try:
        q.put_nowait(("", payload, user_id))
    except asyncio.QueueFull:
        pass


async def start_broadcast_worker() -> None:
    global _broadcast_queue
    _broadcast_queue = asyncio.Queue(maxsize=2000)
    hub = get_hub()
    while True:
        item = await _broadcast_queue.get()
        try:
            if len(item) == 3:
                _, payload, user_id = item
                await hub.notify_user(str(user_id), payload)
            else:
                room_id, payload = item
                if room_id:
                    await hub.broadcast_room(str(room_id), payload)
        except Exception as exc:
            logger.debug("broadcast worker error: %s", exc)


def publish_message(room_id: str, message: Dict[str, Any]) -> None:
    enqueue_broadcast(
        room_id,
        {"type": "message", "room_id": room_id, "payload": message, "ts": time.time()},
    )


def publish_typing(room_id: str, typing: list) -> None:
    enqueue_broadcast(
        room_id,
        {"type": "typing", "room_id": room_id, "typing": typing, "ts": time.time()},
    )


def publish_read(room_id: str, user_id: str, seen_by: Optional[list] = None) -> None:
    enqueue_broadcast(
        room_id,
        {
            "type": "read",
            "room_id": room_id,
            "user_id": user_id,
            "seen_by": seen_by or [],
            "ts": time.time(),
        },
    )


def publish_notification(user_id: str, notification: Dict[str, Any]) -> None:
    enqueue_user_notify(
        user_id,
        {"type": "notification", "payload": notification, "ts": time.time()},
    )
