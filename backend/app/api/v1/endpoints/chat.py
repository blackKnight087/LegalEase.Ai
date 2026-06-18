from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ....core.auth import get_current_user
from ....models.request_models import ChatRequest, ExportReportRequest, StreamChatRequest
from ....models.response_models import ChatResponse
from ....core.chat_mode import normalize_api_chat_mode
from ....core.matter_policy import validate_chat_scope
from ....core.observability import emit_event
from ....services.chat_service import run_chat_turn, stream_chat_response

router = APIRouter(tags=["chat"])


def _validated_scope(user_id: str, mode: str, matter_id: str | None) -> str | None:
    scoped = validate_chat_scope(user_id, mode, matter_id)
    emit_event(
        "chat_scope_decision",
        user_id=str(user_id),
        mode=str(mode),
        matter_id=(matter_id or ""),
        scoped_matter_id=(scoped or ""),
        index_scope=("matter" if scoped else "global"),
    )
    return scoped


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: Dict[str, Any] = Depends(get_current_user)):
    if not req.message.strip():
        raise HTTPException(400, "message is required")
    membership = str(user.get("membership") or "Free")
    mode = normalize_api_chat_mode(req.mode, membership)
    history = [{"role": m.role, "content": m.content} for m in req.history]
    # #region agent log
    try:
        with open(Path(__file__).resolve().parents[5] / "debug-cf6ca9.log", "a", encoding="utf-8") as lf:
            lf.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "runId": "matter-separation",
                        "hypothesisId": "H1",
                        "location": "chat.py:chat",
                        "message": "chat_request_scope",
                        "data": {
                            "mode": mode,
                            "matter_id": req.matter_id or "",
                            "matter_mode": req.matter_mode or "",
                            "thread_id": req.thread_id or "",
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion

    try:

        def _run():
            scoped_matter_id = _validated_scope(user["id"], mode, req.matter_id)
            return run_chat_turn(
                user["id"],
                req.message.strip(),
                mode,
                lang=req.lang,
                conversation_history=history,
                attachment=req.attachment,
                session_id=req.session_id,
                thread_id=req.thread_id,
                matter_id=scoped_matter_id,
                matter_mode=req.matter_mode,
                membership=membership,
            )

        content, similar_cases, web_sources, follow_ups, state, sid, saved = await run_in_threadpool(_run)
        safe = content if content and str(content).strip() not in ("{}", "[]") else (
            "I could not find this information in the uploaded legal documents."
        )
        return ChatResponse(
            content=safe,
            similar_cases=similar_cases,
            web_sources=web_sources,
            follow_ups=follow_ups,
            session_id=sid,
            conversation_state=state,
            chat_id=saved.get("chat_id"),
            thread_id=saved.get("thread_id"),
            interaction_id=saved.get("interaction_id"),
        )
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/stream")
async def chat_stream(req: StreamChatRequest, user: Dict[str, Any] = Depends(get_current_user)):
    if not req.message.strip():
        raise HTTPException(400, "message is required")
    membership = str(user.get("membership") or "Free")
    mode = normalize_api_chat_mode(req.mode, membership)
    history = [{"role": m.role, "content": m.content} for m in req.history]
    # #region agent log
    try:
        with open(Path(__file__).resolve().parents[5] / "debug-cf6ca9.log", "a", encoding="utf-8") as lf:
            lf.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "runId": "matter-separation",
                        "hypothesisId": "H1",
                        "location": "chat.py:chat_stream",
                        "message": "stream_request_scope",
                        "data": {
                            "mode": mode,
                            "matter_id": req.matter_id or "",
                            "matter_mode": req.matter_mode or "",
                            "thread_id": req.thread_id or "",
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion

    chunk_q: queue.Queue[str | None] = queue.Queue(maxsize=256)
    loop = asyncio.get_event_loop()

    def producer():
        try:
            scoped_matter_id = _validated_scope(user["id"], mode, req.matter_id)
            for chunk in stream_chat_response(
                user["id"],
                req.message.strip(),
                mode,
                lang=req.lang,
                conversation_history=history,
                attachment=req.attachment,
                session_id=req.session_id,
                thread_id=req.thread_id,
                matter_id=scoped_matter_id,
                matter_mode=req.matter_mode,
                membership=membership,
            ):
                chunk_q.put(chunk)
        except Exception as exc:
            chunk_q.put(f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n")
            chunk_q.put("data: [DONE]\n\n")
        finally:
            chunk_q.put(None)

    threading.Thread(target=producer, daemon=True).start()

    async def event_gen():
        while True:
            item = await loop.run_in_executor(None, chunk_q.get)
            if item is None:
                break
            yield item

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/export-report")
async def export_report(req: ExportReportRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """Export assistant research report as DOCX or PDF."""
    _ = user
    if not (req.content or "").strip():
        raise HTTPException(400, "content is required")
    fmt = (req.format or "docx").lower().strip()
    if fmt not in ("docx", "pdf", "md"):
        raise HTTPException(400, "format must be docx, pdf, or md")

    from backend.app.core.report_export import export_report_bytes

    try:
        data, filename, media_type = export_report_bytes(
            req.content, req.title, fmt, client_safe=bool(req.client_safe)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
