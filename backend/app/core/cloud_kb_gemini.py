"""Knowledge Base synthesis via Gemini when Ollama is unavailable (AWS / cloud deploy)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def cloud_kb_gemini_enabled() -> bool:
    """True only on cloud deploy (AWS): CLOUD_GEMINI_KB=1 + LLM_BACKEND=gemini. Laptop stays Ollama."""
    if (os.getenv("CLOUD_GEMINI_KB") or "0").lower() not in {"1", "true", "yes", "on"}:
        return False
    if (os.getenv("LLM_BACKEND") or "ollama").strip().lower() != "gemini":
        return False
    try:
        from backend.app.core.web_intelligence import gemini_configured

        return gemini_configured()
    except Exception:
        return False


def synthesize_kb_cloud_gemini(
    question: str,
    chunks: List[Dict[str, Any]],
    *,
    user_id: str = "",
    max_tokens: int = 900,
) -> str:
    """Answer from uploaded chunks only — used when local Ollama is not on the server."""
    if not cloud_kb_gemini_enabled() or not chunks:
        return ""
    q = (question or "").strip()
    if not q:
        return ""

    parts: List[str] = []
    for i, ch in enumerate(chunks[:8], 1):
        text = (ch.get("text") or ch.get("content") or "").strip()
        if not text:
            continue
        fname = ch.get("filename") or ch.get("source") or "document"
        parts.append(f"[{i}] ({fname})\n{text[:2400]}")

    if not parts:
        return ""

    context = "\n\n".join(parts)
    system = (
        "You are LegalEase Knowledge Base assistant for Indian law. "
        "Answer ONLY using the document excerpts below. "
        "If the excerpts do not contain enough information, say clearly that it is not in the documents. "
        "Do not invent statutes, cases, or section numbers. Cite source filenames when possible."
    )
    user = f"Question: {q}\n\nDocument excerpts:\n{context}"

    try:
        from google.genai import types

        from backend.app.core.web_intelligence import _get_client, GEMINI_FREE_MODEL

        if user_id:
            try:
                from backend.app.core.gemini_usage import assert_gemini_allowed, record_gemini_call

                assert_gemini_allowed(str(user_id), "Free")
                record_gemini_call(str(user_id))
            except RuntimeError:
                raise
            except Exception:
                pass

        client = _get_client()
        response = client.models.generate_content(
            model=GEMINI_FREE_MODEL,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,
                max_output_tokens=min(max(int(max_tokens), 256), 2048),
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if text:
            logger.info("[cloud_kb_gemini] answer_len=%s user=%s", len(text), str(user_id)[:8])
        return text
    except Exception as exc:
        logger.warning("[cloud_kb_gemini] failed: %s", exc)
        return ""
