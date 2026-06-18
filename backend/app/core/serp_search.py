"""SerpAPI (Google results) — fast fallback when Tavily returns nothing."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SERP_API_KEY = (os.getenv("SERP_API_KEY") or "").strip().strip("\"'")
SERP_API_URL = os.getenv("SERP_API_URL", "https://serpapi.com/search.json")
SERP_TIMEOUT = float(os.getenv("SERP_TIMEOUT", "10"))
SERP_ENGINE = os.getenv("SERP_ENGINE", "google")


def serp_configured() -> bool:
    return bool(SERP_API_KEY)


def search_serp(query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    """
    Query SerpAPI (Google organic results). Returns rows compatible with legal_web_engine:
    {title, href, body, date, provider}.
    """
    if not SERP_API_KEY:
        return []

    q = (query or "").strip()[:480]
    if not q:
        return []

    try:
        import requests
    except ImportError:
        return []

    cap = max(1, min(max_results, 10))
    params = {
        "engine": SERP_ENGINE,
        "q": q,
        "api_key": SERP_API_KEY,
        "num": cap,
        "hl": "en",
        "gl": "in",
    }

    try:
        resp = requests.get(SERP_API_URL, params=params, timeout=SERP_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("SerpAPI HTTP %s: %s", resp.status_code, resp.text[:200])
            return []
        data = resp.json()
        if data.get("error"):
            logger.warning("SerpAPI error: %s", data.get("error"))
            return []

        rows: List[Dict[str, Any]] = []
        today = datetime.now(timezone.utc).date().isoformat()

        for item in (data.get("organic_results") or [])[:cap]:
            link = (item.get("link") or item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            body = (
                item.get("snippet")
                or item.get("description")
                or item.get("rich_snippet", {}).get("top", {}).get("detected_extensions", {}).get("description", "")
                or ""
            )
            if isinstance(body, dict):
                body = str(body)
            body = str(body).strip()
            if not title and not body:
                continue
            rows.append(
                {
                    "title": title or link,
                    "href": link,
                    "body": body,
                    "date": today,
                    "provider": "SerpAPI",
                }
            )

        # Answer box / knowledge graph one-liner as extra context
        answer = data.get("answer_box") or {}
        if answer and rows:
            ab_text = (
                answer.get("answer")
                or answer.get("snippet")
                or answer.get("result")
                or ""
            )
            ab_text = str(ab_text).strip()
            ab_link = (answer.get("link") or answer.get("source") or {}).get("link", "") if isinstance(answer.get("source"), dict) else answer.get("link", "")
            if ab_text:
                rows.insert(
                    0,
                    {
                        "title": answer.get("title") or "Featured answer",
                        "href": str(ab_link or ""),
                        "body": ab_text,
                        "date": today,
                        "provider": "SerpAPI",
                    },
                )

        return rows[:cap]
    except Exception as exc:
        logger.warning("SerpAPI search failed: %s", exc)
        return []
