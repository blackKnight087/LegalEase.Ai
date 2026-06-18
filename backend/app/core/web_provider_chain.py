"""
Web legal intelligence provider chain with automatic fallback.

Priority: Gemini (grounded) → OpenRouter → DeepSeek → Qwen API → local Ollama legal model.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("legalease.web_chain")

LOCAL_ONLY_BANNER = "**Using local legal reasoning only.**\n\n"

OPENROUTER_API_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip()
OPENROUTER_MODEL = (os.getenv("OPENROUTER_MODEL") or "google/gemma-2-9b-it:free").strip()
OPENROUTER_BASE = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")

DEEPSEEK_API_KEY = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
DEEPSEEK_MODEL = (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()
DEEPSEEK_BASE = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")

QWEN_API_KEY = (
    os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY") or ""
).strip()
QWEN_MODEL = (os.getenv("QWEN_API_MODEL") or "qwen-turbo").strip()
QWEN_BASE = (os.getenv("QWEN_API_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")

_HTTP_TIMEOUT = float(os.getenv("WEB_PROVIDER_HTTP_TIMEOUT", "45"))


def _openai_compatible_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
) -> Optional[str]:
    if not api_key or not base_url:
        return None
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in base_url:
        headers["HTTP-Referer"] = os.getenv("PUBLIC_APP_URL", "https://legalease.local")
        headers["X-Title"] = "LegalEase AI"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=_HTTP_TIMEOUT)
        if r.status_code != 200:
            logger.info("Web provider HTTP %s @ %s", r.status_code, base_url)
            return None
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        return str(content).strip() or None
    except requests.RequestException as exc:
        logger.info("Web provider request failed %s: %s", base_url, exc)
        return None


def _local_legal_fallback(query: str, *, user_id: str = "") -> str:
    from backend.app.core.llm_orchestrator import legal_reason

    system = (
        "You are LegalEase AI. Live web search is unavailable. "
        "Answer using general Indian legal knowledge only. "
        "Do NOT invent IPC/BNS section numbers — use cautious phrasing. "
        "State clearly that live case law was not retrieved."
    )
    body = legal_reason(
        f"Legal research question (offline mode):\n\n{query}\n\nStructured answer:",
        system_prompt=system,
        user_id=user_id,
        max_tokens=1000,
        temperature=0.15,
    )
    if not body:
        body = (
            "Live web research is temporarily unavailable. "
            "Please try again later or use Knowledge Base mode with uploaded documents."
        )
    if LOCAL_ONLY_BANNER.strip() not in body:
        body = LOCAL_ONLY_BANNER + body
    return body


def run_legal_web_research(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    *,
    user_id: str = "",
    thread_id: str = "",
    membership: str = "Free",
) -> Tuple[str, List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """
    Full provider chain. Returns (answer, sources, follow_ups, meta).
    Never raises — degrades to local reasoning.
    """
    q = (query or "").strip()
    meta: Dict[str, Any] = {"provider": None, "chain": []}

    if not q:
        return ("### Open Law\n\nPlease enter a legal research question.", [], [], meta)

    # 1 — Gemini grounded
    try:
        from backend.app.core.web_intelligence import gemini_configured, run_grounded_legal_research

        if gemini_configured():
            meta["chain"].append("gemini")
            answer, sources, follow_ups = run_grounded_legal_research(
                q,
                conversation_history,
                user_id=user_id or None,
                thread_id=thread_id or None,
                membership=membership,
            )
            low = (answer or "").lower()
            kb_leak = "uploaded legal documents" in low or "from your documents" in low
            if (answer or "").strip() and not kb_leak:
                meta["provider"] = "gemini"
                return answer, sources, follow_ups, meta
            meta["chain"].append("gemini_empty_or_kb_leak")
    except RuntimeError:
        meta["chain"].append("gemini_denied")
    except Exception as exc:
        logger.warning("Gemini web research failed: %s", exc)
        meta["chain"].append(f"gemini_error:{type(exc).__name__}")

    # 1b — Tavily / Serp / DuckDuckGo snippets + compose (when Gemini unavailable or quota hit)
    try:
        from backend.app.services.open_law_executor import _from_legacy_web_search

        legacy = _from_legacy_web_search(
            q,
            conversation_history,
            user_id=user_id,
            fast_compose=True,
        )
        if legacy.has_content() and "uploaded legal documents" not in (legacy.content or "").lower():
            meta["chain"].append("tavily_serp")
            meta["provider"] = "tavily_serp"
            return legacy.content, legacy.web_sources or [], legacy.follow_ups or [], meta
    except Exception as exc:
        logger.warning("Tavily/Serp web fallback failed: %s", exc)
        meta["chain"].append(f"tavily_error:{type(exc).__name__}")

    system = (
        "You are an Indian legal research assistant. Answer with markdown headers. "
        "Cite public sources when known. Do not invent case citations. "
        "Note: live Google Search grounding is unavailable for this response."
    )
    user = q
    if conversation_history:
        hist = "\n".join(
            f"{m.get('role', 'user')}: {(m.get('content') or '')[:400]}"
            for m in conversation_history[-4:]
        )
        user = f"Prior context:\n{hist}\n\nCurrent question: {q}"

    # 2 — OpenRouter
    if OPENROUTER_API_KEY:
        meta["chain"].append("openrouter")
        text = _openai_compatible_chat(
            base_url=OPENROUTER_BASE,
            api_key=OPENROUTER_API_KEY,
            model=OPENROUTER_MODEL,
            system=system,
            user=user,
        )
        if text:
            meta["provider"] = "openrouter"
            return text, [], [], meta

    # 3 — DeepSeek
    if DEEPSEEK_API_KEY:
        meta["chain"].append("deepseek")
        text = _openai_compatible_chat(
            base_url=f"{DEEPSEEK_BASE}/v1" if not DEEPSEEK_BASE.endswith("/v1") else DEEPSEEK_BASE,
            api_key=DEEPSEEK_API_KEY,
            model=DEEPSEEK_MODEL,
            system=system,
            user=user,
        )
        if text:
            meta["provider"] = "deepseek"
            return text, [], [], meta

    # 4 — Qwen API (DashScope compatible)
    if QWEN_API_KEY:
        meta["chain"].append("qwen_api")
        text = _openai_compatible_chat(
            base_url=QWEN_BASE,
            api_key=QWEN_API_KEY,
            model=QWEN_MODEL,
            system=system,
            user=user,
        )
        if text:
            meta["provider"] = "qwen_api"
            return text, [], [], meta

    # 5 — Local Ollama legal model
    meta["chain"].append("local")
    meta["provider"] = "local"
    text = _local_legal_fallback(q, user_id=user_id)
    return text, [], [], meta
