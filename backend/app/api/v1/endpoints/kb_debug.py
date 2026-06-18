"""KB retrieval diagnostics — debug mode for grounded RAG."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from ....core.auth import get_current_user
from ....core.kb_query_diagnostics import run_kb_debug_batch, run_kb_debug_query

router = APIRouter(tags=["kb-debug"])


@router.get("/debug-query")
async def kb_debug_query(
    q: str = Query(..., min_length=1, description="Query to diagnose"),
    session_id: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Retrieval diagnostics: full orchestrator pipeline trace + chunk rejections.

    Example: GET /api/v1/kb/debug-query?q=Fundamental+Rights
    """
    user_id = str(current_user.get("id") or current_user.get("user_id") or "")
    result = run_kb_debug_query(user_id, q.strip(), session_id=session_id)
    console = result.get("debug_console") or {}
    if console:
        result.update(console)
    return result


@router.get("/debug-batch")
async def kb_debug_batch(
    session_id: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Run the standard KB retrieval test set (Article 14/19/21/32, IPC 302/304/320, etc.).

    Example: GET /api/v1/kb/debug-batch
    """
    user_id = str(current_user.get("id") or current_user.get("user_id") or "")
    return run_kb_debug_batch(user_id, session_id=session_id)
