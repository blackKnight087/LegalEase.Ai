from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

_DEBUG_LOG = Path(__file__).resolve().parents[5] / "debug-cf6ca9.log"


def _agent_log(location: str, message: str, data: Dict[str, Any], hypothesis_id: str) -> None:
    try:
        payload = {
            "sessionId": "cf6ca9",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....services.speech_service import (
    SpeechTranscriptionError,
    polish_legal_text,
    stt_status,
    transcribe_audio,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["speech"])


class PolishRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50000)


class PolishResponse(BaseModel):
    text: str
    engine: str = "llm_polish"


@router.get("/status")
async def speech_status(_user: Dict[str, Any] = Depends(get_current_user)):
    cfg = stt_status()
    return {
        "enabled": cfg["enabled"],
        "engine": cfg["engine"],
        "model": cfg["model"],
        "device": cfg["device"],
        "compute_type": cfg["compute_type"],
        "supported_languages": ["en", "hi", "ta", "mr", "bn", "gu"],
        "fallback_browser": cfg["fallback_browser"],
        "preload": cfg.get("preload", False),
    }


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Form("en"),
    matter_id: Optional[str] = Form(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    _ = user
    if matter_id:
        logger.debug("STT matter_id=%s", matter_id)

    t0 = time.perf_counter()
    try:
        data = await audio.read()
        _agent_log(
            "speech.py:transcribe",
            "stt_request_received",
            {
                "bytes": len(data),
                "language": language,
                "filename": audio.filename or "audio.webm",
            },
            "H3",
        )
        result = await run_in_threadpool(
            transcribe_audio,
            data,
            language=language,
            filename=audio.filename or "audio.webm",
        )
        logger.debug("STT transcribe ok in %.0fms", (time.perf_counter() - t0) * 1000)
        _agent_log(
            "speech.py:transcribe",
            "stt_ok",
            {"text_len": len((result or {}).get("text") or "")},
            "H3",
        )
        return result
    except SpeechTranscriptionError as exc:
        _agent_log(
            "speech.py:transcribe",
            "stt_speech_error",
            {"msg": str(exc)[:300], "fallback": exc.fallback_browser},
            "H3",
        )
        detail: Dict[str, Any] = {"message": str(exc)}
        if exc.fallback_browser:
            detail["fallback"] = "browser"
            raise HTTPException(status_code=503, detail=detail) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _agent_log(
            "speech.py:transcribe",
            "stt_unexpected_error",
            {"type": type(exc).__name__, "msg": str(exc)[:300]},
            "H3",
        )
        from ....services.speech_service import browser_fallback_allowed, normalize_language_code

        if browser_fallback_allowed(normalize_language_code(language)):
            raise HTTPException(
                status_code=503,
                detail={"message": str(exc), "fallback": "browser"},
            ) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/polish", response_model=PolishResponse)
async def polish(
    body: PolishRequest,
    _user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        polished = await run_in_threadpool(polish_legal_text, body.text)
        return PolishResponse(text=polished or body.text)
    except Exception as exc:
        logger.exception("Speech polish failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
