"""
Optional Gemini helpers for KB — retrieval accuracy and chunk ordering ONLY.

Does NOT synthesize answers. See kb_gemini_safety.py and kb_gemini_synthesis.py.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.kb_gemini_safety import (
    GEMINI_KB_RERANK,
    GEMINI_KB_RETRIEVAL_HINTS,
    assert_kb_enhance_quota,
    chunk_snippet_for_gemini,
    kb_gemini_enhancement_allowed,
    record_kb_enhance_call,
    sanitize_rerank_indices,
    validate_retrieval_hints,
)

logger = logging.getLogger(__name__)

_RETRIEVAL_HINT_TIMEOUT_SEC = 10
_RERANK_TIMEOUT_SEC = 12
_MIN_CHUNKS_FOR_HINT_SKIP = 6
_WEAK_TOP_SCORE = 1.85


def _gemini_json_call(system: str, user: str, *, max_tokens: int = 256) -> Optional[Dict[str, Any]]:
    try:
        from backend.app.core.web_intelligence import GEMINI_FREE_MODEL, _get_client
        from google.genai import types
    except Exception as exc:
        logger.debug("KB Gemini client unavailable: %s", exc)
        return None

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=GEMINI_FREE_MODEL,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.0,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            ),
        )
        raw = (getattr(response, "text", None) or "").strip()
        if not raw:
            return None
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("KB Gemini JSON call failed: %s", exc)
        return None


def gemini_suggest_retrieval_queries(
    query: str,
    *,
    user_id: str = "",
    query_class: str = "",
) -> List[str]:
    """
    Return search phrases only — never a legal answer.
    """
    if not GEMINI_KB_RETRIEVAL_HINTS or not kb_gemini_enhancement_allowed():
        return []
    if user_id and not assert_kb_enhance_quota(user_id):
        return []

    q = (query or "").strip()[:400]
    if not q:
        return []

    system = (
        "You are a document search assistant for a legal knowledge base. "
        "Given a user question, output JSON only: "
        '{"search_phrases":["phrase1","phrase2"]}. '
        "Rules: 1) Provide 1-3 short search phrases to find relevant PDF chunks. "
        "2) Do NOT answer the legal question. "
        "3) Do NOT state punishments, holdings, or legal conclusions. "
        "4) Phrases may include section numbers and keywords from the question. "
        "5) Max 12 words per phrase."
    )
    user = json.dumps(
        {"user_question": q, "query_class": query_class or "general"},
        ensure_ascii=False,
    )
    data = _gemini_json_call(system, user, max_tokens=200)
    if not data:
        return []

    phrases = data.get("search_phrases") or data.get("hints") or data.get("queries") or []
    if not isinstance(phrases, list):
        return []

    validated = validate_retrieval_hints([str(p) for p in phrases], original_query=q)
    if validated and user_id:
        record_kb_enhance_call(user_id)
    return validated


def gemini_rerank_chunks(query: str, chunks: List[Dict[str, Any]], *, user_id: str = "") -> List[Dict[str, Any]]:
    """
    Reorder chunks by relevance using Gemini scores on snippets only.
  Does not change chunk text or generate an answer.
    """
    if not GEMINI_KB_RERANK or not kb_gemini_enhancement_allowed() or not chunks:
        return chunks
    if len(chunks) < 2:
        return chunks
    if user_id and not assert_kb_enhance_quota(user_id):
        return chunks

    n = min(len(chunks), 12)
    pool = chunks[:n]
    lines = []
    for i, ch in enumerate(pool):
        lines.append(f"{i}: {chunk_snippet_for_gemini(ch)}")

    system = (
        "Rank document snippets by relevance to the user question. "
        'Output JSON only: {"ranking":[0,2,1,...]} using each index exactly once. '
        "Do NOT answer the question. Do NOT add legal analysis."
    )
    user = json.dumps(
        {"question": (query or "")[:400], "snippets": lines},
        ensure_ascii=False,
    )
    data = _gemini_json_call(system, user, max_tokens=120)
    if not data:
        return chunks

    ranking = sanitize_rerank_indices(data.get("ranking") or data.get("order") or [], n)
    reordered = [pool[i] for i in ranking if i < len(pool)]
    if len(reordered) < len(pool):
        reordered.extend(pool[len(reordered) :])
    tail = chunks[n:]
    if user_id:
        record_kb_enhance_call(user_id)
    return reordered + tail


def _merge_chunks(primary: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []

    def _key(c: Dict[str, Any]) -> str:
        return (c.get("content") or "")[:96]

    for group in (primary, extra):
        for c in group or []:
            k = _key(c)
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(c)
    return out


def enhance_kb_retrieval_pipeline(
    query: str,
    chunks: List[Dict[str, Any]],
    *,
    user_id: str = "",
    index_dir: Any = None,
    scope: Optional[Dict[str, Any]] = None,
    query_class: str = "",
    parsed_sections: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Post-retrieval enhancement: optional Gemini hint queries + rerank.
    Never modifies answer text — only retrieval pool ordering/content.
    """
    meta: Dict[str, Any] = {"hints": [], "reranked": False, "extra_chunks": 0}
    if not kb_gemini_enhancement_allowed():
        return chunks, meta

    current = list(chunks or [])
    top_score = 0.0
    if current:
        top_score = float(current[0].get("final_score") or current[0].get("score") or 0)

    need_hints = (
        GEMINI_KB_RETRIEVAL_HINTS
        and index_dir is not None
        and (
            len(current) < _MIN_CHUNKS_FOR_HINT_SKIP
            or top_score > _WEAK_TOP_SCORE
            or (parsed_sections and not _chunks_match_sections(current, parsed_sections))
        )
    )

    if need_hints:
        hints = gemini_suggest_retrieval_queries(
            query, user_id=user_id, query_class=query_class
        )
        meta["hints"] = hints
        if hints:
            extra: List[Dict[str, Any]] = []
            try:
                from backend.app.core.kb_retrieval_robust import robust_kb_retrieve

                for phrase in hints[:3]:
                    extra.extend(
                        robust_kb_retrieve(
                            phrase,
                            index_dir,
                            scope=scope or {},
                            k=6,
                        )
                        or []
                    )
            except Exception as exc:
                logger.debug("KB hint retrieval failed: %s", exc)
            if extra:
                merged = _merge_chunks(current, extra)
                meta["extra_chunks"] = max(0, len(merged) - len(current))
                current = merged

    if GEMINI_KB_RERANK and current:
        reranked = gemini_rerank_chunks(query, current, user_id=user_id)
        if reranked != current:
            meta["reranked"] = True
            current = reranked

    return current, meta


def _chunks_match_sections(chunks: List[Dict[str, Any]], sections: List[str]) -> bool:
    if not sections:
        return True
    want = {str(s).lower() for s in sections}
    blob = " ".join((c.get("content") or "")[:500] for c in chunks[:6]).lower()
    return any(re.search(rf"\bsection\s*{re.escape(sec)}\b", blob) or sec in blob for sec in want)
