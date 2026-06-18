"""Bridge Firm Chat activity into matter timelines."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("legalease.collab_timeline")


def log_collab_timeline(
    user_id: str,
    matter_id: str,
    *,
    title: str,
    description: str = "",
    event_type: str = "collab",
) -> None:
    if not matter_id or not (title or "").strip():
        return
    try:
        from backend.app.core.matter_workflow import add_timeline_event

        add_timeline_event(
            user_id,
            matter_id,
            title=title.strip()[:200],
            description=(description or "").strip()[:2000],
            event_type=event_type,
        )
    except Exception as exc:
        logger.debug("collab timeline skip matter=%s: %s", matter_id, exc)
