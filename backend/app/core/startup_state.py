"""Background startup progress — safe to import from any module."""
from __future__ import annotations

from typing import Any, Dict

STARTUP_SNAPSHOT: Dict[str, Any] = {
    "startup_complete": False,
    "embeddings_ok": False,
    "embeddings_error": "",
    "embeddings_model": "",
    "embeddings_device": "cpu",
}


def get_startup_snapshot() -> Dict[str, Any]:
    return dict(STARTUP_SNAPSHOT)


def update_startup_snapshot(**fields: Any) -> None:
    STARTUP_SNAPSHOT.update(fields)
