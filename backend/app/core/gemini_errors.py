"""Classify Gemini API failures for robust fallback routing."""
from __future__ import annotations

import time

_quota_cooldown_until: float = 0.0
_DEFAULT_COOLDOWN_SEC = 3600


def is_gemini_quota_error(exc: BaseException | str) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "429",
            "resource_exhausted",
            "quota exceeded",
            "quota_exceeded",
            "rate limit",
            "rate_limit",
            "daily limit",
        )
    )


def mark_gemini_quota_exhausted(cooldown_sec: int = _DEFAULT_COOLDOWN_SEC) -> None:
    global _quota_cooldown_until
    _quota_cooldown_until = time.time() + max(60, cooldown_sec)


def gemini_quota_cooldown_active() -> bool:
    return time.time() < _quota_cooldown_until


def gemini_error_user_hint(exc: BaseException | str) -> str:
    if is_gemini_quota_error(exc):
        return (
            "Gemini free-tier daily limit reached for this API key. "
            "LegalEase is switching to backup web search (DuckDuckGo). "
            "For unlimited Open Law, add billing on Google AI Studio or set `TAVILY_API_KEY` in `.env`."
        )
    return (
        "Gemini web research is temporarily unavailable. "
        "LegalEase will try backup web search."
    )
