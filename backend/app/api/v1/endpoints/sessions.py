from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from ....core.auth import get_current_user
from ....core.chat_persistence import (
    delete_chat_history_for_matter,
    delete_chat_thread,
    ensure_chat_schema,
    list_chat_threads,
    load_chat_thread,
)
from ....core.conversation_memory import get_or_create_session, get_session_state, get_session_history
from ....core.thread_attachments import (
    delete_thread_attachment,
    load_thread_attachment,
    save_thread_attachment,
)
from ....models.response_models import ChatThreadDetailResponse, SessionStateResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sessions"])

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _extract_file_text(filename: str, data: bytes, use_ocr: bool) -> tuple[str, str]:
    """Returns (text, method)."""
    name = (filename or "file").lower()
    ext = Path(name).suffix

    if ext in _IMAGE_EXT:
        from ocr_engine import extract_text_from_image_bytes, ocr_status

        text, method = extract_text_from_image_bytes(data, filename)
        if not text.strip():
            st = ocr_status()
            if not st.get("enabled"):
                raise ValueError("OCR is disabled. Set OCR_ENABLED=1 in .env.")
            if st.get("reader_failed"):
                raise ValueError(
                    "Image OCR failed (EasyOCR could not start). "
                    "Run: py -m pip install easyocr pymupdf — then restart the backend."
                )
            raise ValueError("No text detected in image.")
        return text, method or "ocr_image"

    if ext == ".pdf" or name.endswith(".pdf"):
        from app import extract_text_from_file, MAX_UPLOAD_MB

        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            raise ValueError(f"PDF exceeds {MAX_UPLOAD_MB} MB limit.")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            from backend.app.core.pdf_extraction import extract_pdf_production

            text, _method = extract_pdf_production(
                tmp_path,
                force_ocr=use_ocr,
                allow_ocr=True,
            )
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        if not (text or "").strip():
            raise ValueError(
                "No text extracted from PDF. Enable OCR for scanned documents or upload a text-based PDF."
            )
        return text.strip(), "pdf_ocr" if use_ocr else "pdf_native"

    raise ValueError("Supported types: PDF, PNG, JPG, WEBP")


@router.get("/history")
def chat_history(
    limit: int = 50,
    matter_id: str = Query("", description="Filter threads by matter"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List saved chat threads for sidebar."""
    ensure_chat_schema()
    mid = (matter_id or "").strip() or None
    rows = list_chat_threads(user["id"], limit=limit, matter_id=mid) or []
    matter_names: Dict[str, str] = {}
    if rows:
        from backend.app.core.matter_repo import get_matter

        for r in rows:
            mcol = r[6] if len(r) > 6 else ""
            if mcol and mcol not in matter_names:
                m = get_matter(user["id"], mcol)
                if m:
                    matter_names[mcol] = m.get("matter_name") or ""
    sessions: List[Dict[str, str]] = []
    for row in rows:
        thread_id, question, answer, mode, language, created = row[:6]
        mid_row = row[6] if len(row) > 6 else ""
        sessions.append({
            "thread_id": str(thread_id),
            "id": str(thread_id),
            "question": (question or "")[:80],
            "preview": (answer or "")[:120],
            "mode": mode or "knowledge_base",
            "language": language or "English",
            "created_at": created or "",
            "matter_id": str(mid_row or ""),
            "matter_name": matter_names.get(str(mid_row or ""), ""),
        })
    logger.info("[CHAT HISTORY] user=%s count=%s", user["id"], len(sessions))
    return {"sessions": sessions, "count": len(sessions)}


@router.delete("/history")
def delete_matter_chat_history(
    matter_id: str = Query(..., description="Delete all chat threads for this matter"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete all saved chats linked to a matter."""
    mid = (matter_id or "").strip()
    if not mid:
        raise HTTPException(400, "matter_id is required")
    deleted = delete_chat_history_for_matter(str(user["id"]), mid)
    return {"ok": True, "matter_id": mid, "deleted_rows": deleted}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Delete a saved chat thread and all its messages."""
    ensure_chat_schema()
    deleted = delete_chat_thread(user["id"], thread_id)
    delete_thread_attachment(user["id"], thread_id)
    if deleted < 1:
        raise HTTPException(404, "Chat thread not found")
    logger.info("[CHAT DELETE] user=%s thread=%s", user["id"], thread_id)
    return {"status": "deleted", "thread_id": thread_id, "deleted_rows": deleted}


@router.get("/threads/{thread_id}/attachment")
def get_thread_attachment(thread_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    att = load_thread_attachment(user["id"], thread_id)
    if not att:
        return {"has_attachment": False}
    content = att.get("content") or ""
    return {
        "has_attachment": True,
        "filename": att.get("filename", "file"),
        "file_kind": att.get("file_kind", "file"),
        "char_count": len(content),
        "preview": content[:240],
        "created_at": att.get("created_at"),
    }


@router.post("/threads/{thread_id}/attachment")
async def upload_thread_attachment(
    thread_id: str,
    file: UploadFile = File(...),
    ocr: str = Query("0", description="1=OCR for scanned PDFs/images"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Attach PDF/image to this chat only (not global Knowledge Base)."""
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    use_ocr = (ocr or "0").strip().lower() in ("1", "true", "yes")

    try:
        text, method = await run_in_threadpool(
            _extract_file_text, file.filename, data, use_ocr
        )
        saved = save_thread_attachment(
            user["id"],
            thread_id,
            file.filename,
            text,
            file_kind=Path(file.filename).suffix.lower().lstrip(".") or "file",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("Thread attachment failed: %s", e)
        raise HTTPException(500, f"Attachment failed: {e}") from e

    return {
        "status": "ok",
        "thread_id": saved["thread_id"],
        "filename": saved["filename"],
        "char_count": len(text),
        "preview": text[:280],
        "method": method,
        "message": "Attached to this chat only. Ask questions in Knowledge Base mode.",
    }


@router.delete("/threads/{thread_id}/attachment")
def remove_thread_attachment(thread_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    if not delete_thread_attachment(user["id"], thread_id):
        raise HTTPException(404, "No attachment on this chat")
    return {"status": "removed", "thread_id": thread_id}


@router.get("/threads/{thread_id}", response_model=ChatThreadDetailResponse)
def get_thread(thread_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Load full saved conversation for reopening in the UI."""
    ensure_chat_schema()
    rows = load_chat_thread(user["id"], thread_id)
    if not rows:
        raise HTTPException(404, "Chat thread not found")

    messages = []
    mode = "knowledge_base"
    language = "English"
    matter_id_val = ""
    for row in rows:
        _cid, question, answer, msg_mode, lang, _created = row[:6]
        if len(row) > 6 and not matter_id_val:
            matter_id_val = str(row[6] or "")
        mode = msg_mode or mode
        language = lang or language
        if question:
            messages.append({"role": "user", "content": question})
        if answer:
            messages.append({"role": "assistant", "content": answer})

    return ChatThreadDetailResponse(
        thread_id=thread_id,
        mode=mode,
        language=language,
        messages=messages,
        matter_id=matter_id_val or None,
    )


@router.get("/by-id/{session_id}", response_model=SessionStateResponse)
def get_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    _ = user
    sid = get_or_create_session(session_id)
    hist = get_session_history(sid)
    return SessionStateResponse(
        session_id=sid,
        state=get_session_state(sid),
        history_length=len(hist),
    )
