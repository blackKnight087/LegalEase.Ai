"""
Safety layer for Knowledge Base mode vs Gemini.

Gemini MUST NEVER (KB chat / retrieval / hybrid KB leg):
  - Answer user questions or generate legal advice
  - Inject knowledge into responses or modify RAG results
  - Override Ollama answers or read live chat for answer generation
  - Access KB retrieval context or participate in hybrid KB retrieval

Gemini MAY ONLY (Settings / offline):
  - Analyze thumbs up/down and feedback ("good answer", "bad", "short", "regenerate")
  - Train/tune Ollama via coach, neural finetuning, Modelfile export
  - Never supply answer text to Ollama at inference time
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Hard lock — must stay 0 in production KB chat.
GEMINI_KB_SYNTHESIS = os.getenv("GEMINI_KB_SYNTHESIS", "0").lower() in {"1", "true", "yes"}

# Legacy env flags — ignored for KB; kept for tests only.
GEMINI_KB_RETRIEVAL_HINTS = os.getenv("GEMINI_KB_RETRIEVAL_HINTS", "0").lower() in {
    "1",
    "true",
    "yes",
}
GEMINI_KB_RERANK = os.getenv("GEMINI_KB_RERANK", "0").lower() in {"1", "true", "yes"}
GEMINI_KB_ENHANCE_DAILY = int(os.getenv("GEMINI_KB_ENHANCE_DAILY", "12"))

_ANSWER_LEAK_RE = re.compile(
    r"\b("
    r"the answer is|you should say|tell the user|conclude that|held that|"
    r"punishment is|liable for|guilty of|murder is|section defines|means that the"
    r")\b",
    re.I,
)

_HINT_MAX_LEN = 120
_HINT_MAX_COUNT = 4


def enforce_kb_gemini_policy(*, mode: str = "knowledge_base") -> None:
    """Called at KB turn entry — blocks forbidden synthesis paths."""
    if mode != "knowledge_base":
        return
    if GEMINI_KB_SYNTHESIS:
        logger.error(
            "[KB SAFETY] GEMINI_KB_SYNTHESIS=1 is forbidden for KB chat; "
            "answers must come from indexed documents + local LLM only."
        )
        raise RuntimeError("GEMINI_KB_SYNTHESIS is disabled for Knowledge Base safety.")
    if GEMINI_KB_RETRIEVAL_HINTS or GEMINI_KB_RERANK:
        logger.warning(
            "[KB SAFETY] GEMINI_KB_RETRIEVAL_HINTS/RERANK are ignored — "
            "Gemini does not participate in KB retrieval."
        )


def kb_gemini_enhancement_allowed() -> bool:
    """Always False — Gemini must not modify KB retrieval or chunks."""
    return False


def assert_kb_enhance_quota(user_id: str) -> bool:
    return False


def record_kb_enhance_call(user_id: str) -> None:
    return None


def _clean_retrieval_hint(text: str) -> str:
    from backend.app.core.coach_guards import BIAS_INJECTION_RE, TRAINING_PAIR_RE

    t = re.sub(r"\s+", " ", (text or "").strip())[:_HINT_MAX_LEN]
    if not t:
        return ""
    if BIAS_INJECTION_RE.search(t) or _ANSWER_LEAK_RE.search(t) or TRAINING_PAIR_RE.search(t):
        return ""
    if len(t.split()) > 14:
        return ""
    return t


def validate_retrieval_hints(
    hints: List[str],
    *,
    original_query: str = "",
) -> List[str]:
    from backend.app.core.coach_guards import BIAS_INJECTION_RE

    out: List[str] = []
    seen: set[str] = set()
    oq = (original_query or "").strip().lower()
    for raw in hints or []:
        h = _clean_retrieval_hint(str(raw))
        if not h or BIAS_INJECTION_RE.search(h):
            continue
        key = h.lower()
        if key in seen or key == oq:
            continue
        seen.add(key)
        out.append(h)
        if len(out) >= _HINT_MAX_COUNT:
            break
    return out


def sanitize_rerank_indices(indices: List[Any], n: int) -> List[int]:
    valid: List[int] = []
    seen: set[int] = set()
    for x in indices or []:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if 0 <= i < n and i not in seen:
            valid.append(i)
            seen.add(i)
    for i in range(n):
        if i not in seen:
            valid.append(i)
    return valid[:n]


def chunk_snippet_for_gemini(chunk: Dict[str, Any], *, max_chars: int = 220) -> str:
    meta = chunk.get("metadata") or {}
    fn = str(meta.get("filename") or meta.get("source") or "")[:80]
    sec = str(meta.get("section") or meta.get("section_number") or "")
    head = (chunk.get("content") or "").strip()[:max_chars]
    prefix = f"[{fn}"
    if sec:
        prefix += f" §{sec}"
    prefix += "] "
    return (prefix + head).strip()
