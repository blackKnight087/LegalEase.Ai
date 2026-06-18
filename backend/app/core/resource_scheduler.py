"""
Resource scheduler — 60% legal answering / 40% learning & tuning.

Prevents OOM by serializing heavy jobs and pausing low-priority work when RAM is high.
Learning stays enabled but never blocks KB chat, smoke tests, or retrieval.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from enum import IntEnum
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("legalease.scheduler")

RAM_PAUSE_PCT = float(os.getenv("LEGALEEASE_RAM_PAUSE_PCT", "85"))
RAM_RESUME_PCT = float(os.getenv("LEGALEEASE_RAM_RESUME_PCT", "75"))


class Priority(IntEnum):
    """Lower number = higher priority (runs first, not paused)."""
    KB_ANSWER = 10      # 60% — chat, retrieval, section mapping
    FEEDBACK = 25       # 25% — store signals, light memory
    SMOKE_TEST = 30
    INDEXING = 35
    TUNING = 50         # 15% — neural train, holdout, export, coach pipeline


# Singleton lock — only one heavy job at a time besides KB_ANSWER readers
_heavy_lock = threading.RLock()
_active_heavy: Optional[str] = None
_kb_readers = 0
_kb_lock = threading.Lock()
_paused_low = False
_pause_reason = ""


def memory_snapshot() -> Dict[str, Any]:
    """Best-effort RAM stats (Windows + Linux)."""
    out: Dict[str, Any] = {"percent": 0.0, "available_mb": 0, "ok": True}
    try:
        import psutil

        vm = psutil.virtual_memory()
        out["percent"] = float(vm.percent)
        out["available_mb"] = int(vm.available / (1024 * 1024))
        out["total_mb"] = int(vm.total / (1024 * 1024))
    except ImportError:
        out["note"] = "psutil not installed"
    except Exception as exc:
        out["error"] = str(exc)[:80]
    return out


def _should_pause_low_priority() -> bool:
    global _paused_low, _pause_reason
    snap = memory_snapshot()
    pct = float(snap.get("percent") or 0)
    if pct >= RAM_PAUSE_PCT:
        _paused_low = True
        _pause_reason = f"ram_{pct:.0f}pct"
        return True
    if _paused_low and pct <= RAM_RESUME_PCT:
        _paused_low = False
        _pause_reason = ""
    return _paused_low


def is_low_priority_paused() -> bool:
    return _should_pause_low_priority()


def scheduler_status() -> Dict[str, Any]:
    with _kb_lock:
        readers = _kb_readers
    return {
        "kb_readers": readers,
        "active_heavy": _active_heavy,
        "low_priority_paused": is_low_priority_paused(),
        "pause_reason": _pause_reason,
        "memory": memory_snapshot(),
        "priorities": {
            "kb_answer": int(Priority.KB_ANSWER),
            "feedback": int(Priority.FEEDBACK),
            "tuning": int(Priority.TUNING),
        },
    }


def can_run(priority: Priority) -> bool:
    if priority <= Priority.FEEDBACK:
        return True
    if priority == Priority.SMOKE_TEST:
        with _kb_lock:
            if _active_heavy and _active_heavy not in ("smoke_test",):
                return False
        return not is_low_priority_paused()
    if priority >= Priority.TUNING:
        if is_low_priority_paused():
            return False
        with _kb_lock:
            if _kb_readers > 0:
                return False
        return _active_heavy is None
    if priority == Priority.INDEXING:
        # Indexing always allowed — memory_efficiency.py adapts batch size instead of blocking.
        return _active_heavy is None or _active_heavy == "indexing"
    return True


@contextmanager
def acquire(priority: Priority, label: str = "") -> Iterator[Dict[str, Any]]:
    """
    Context manager for scheduled work.
    KB_ANSWER: concurrent readers allowed.
    Others: exclusive heavy lock when permitted.
    """
    global _active_heavy, _kb_readers
    tag = label or priority.name
    meta: Dict[str, Any] = {"ok": True, "label": tag, "priority": priority.name}

    if not can_run(priority):
        meta["ok"] = False
        meta["skipped"] = True
        meta["reason"] = _pause_reason or "busy"
        yield meta
        return

    if priority <= Priority.KB_ANSWER:
        with _kb_lock:
            _kb_readers += 1
        try:
            yield meta
        finally:
            with _kb_lock:
                _kb_readers = max(0, _kb_readers - 1)
        return

    acquired = _heavy_lock.acquire(timeout=float(os.getenv("SCHEDULER_HEAVY_WAIT_SEC", "2")))
    if not acquired:
        meta["ok"] = False
        meta["skipped"] = True
        meta["reason"] = "heavy_lock_busy"
        yield meta
        return

    try:
        with _kb_lock:
            if _kb_readers > 0 and priority >= Priority.INDEXING:
                meta["ok"] = False
                meta["skipped"] = True
                meta["reason"] = "kb_active"
                yield meta
                return
            _active_heavy = tag
        yield meta
    finally:
        with _kb_lock:
            _active_heavy = None
        _heavy_lock.release()


def defer_low_priority(fn, *, label: str = "background") -> None:
    """Run tuning/training in a daemon thread when scheduler allows."""

    def _runner() -> None:
        time.sleep(0.5)
        if not can_run(Priority.TUNING):
            logger.info("[SCHEDULER] Deferred %s — %s", label, _pause_reason or "busy")
            return
        with acquire(Priority.TUNING, label) as slot:
            if not slot.get("ok"):
                return
            try:
                fn()
            except Exception:
                logger.exception("[SCHEDULER] %s failed", label)

    threading.Thread(target=_runner, daemon=True, name=f"sched-{label[:24]}").start()
