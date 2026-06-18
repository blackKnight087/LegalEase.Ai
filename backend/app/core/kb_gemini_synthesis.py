"""KB answers use local Ollama/LM Studio only — Gemini is not used in Knowledge Base mode.

For Settings-only Ollama tuning via feedback analysis, see gemini_ollama_coach.py
(GEMINI_OLLAMA_TUNING=1, triggered manually from Settings — never during chat).

Optional retrieval-only helpers: kb_gemini_enhancer.py (GEMINI_KB_RETRIEVAL_HINTS / RERANK).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.core.kb_gemini_safety import GEMINI_KB_SYNTHESIS as _SAFETY_KB_SYNTHESIS

logger = logging.getLogger(__name__)

# Re-export — single source of truth in kb_gemini_safety.py
GEMINI_KB_SYNTHESIS = _SAFETY_KB_SYNTHESIS


def synthesize_kb_with_gemini(
    question: str,
    chunks: List[Dict[str, Any]],
    messages: Optional[List[Dict]] = None,
    *,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> str:
    """Forbidden in production — always returns empty; use local RAG + Ollama."""
    if GEMINI_KB_SYNTHESIS:
        logger.error(
            "[KB SAFETY] synthesize_kb_with_gemini blocked (user=%s)", (user_id or "")[:8]
        )
        raise RuntimeError("Gemini cannot synthesize Knowledge Base answers.")
    _ = (question, chunks, messages, user_id, thread_id)
    return ""
