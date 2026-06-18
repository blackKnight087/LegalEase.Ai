"""AI trust layer — prompt injection hardening and input sanitization."""
from __future__ import annotations

import re
from typing import Optional

_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions"),
    re.compile(r"(?i)disregard\s+(your\s+)?(system|safety)\s+(prompt|rules)"),
    re.compile(r"(?i)you\s+are\s+now\s+(?:a\s+)?(?:DAN|jailbreak|unrestricted)"),
    re.compile(r"(?i)reveal\s+(?:the\s+)?system\s+prompt"),
    re.compile(r"(?i)\[INST\]|\[/INST\]|<\|im_start\|>|<\|im_end\|>"),
    re.compile(r"(?i)```\s*system\s*\n"),
]

_MAX_USER_PROMPT_LEN = 32000


def sanitize_user_prompt(text: str, *, max_len: Optional[int] = None) -> str:
    """
    Strip common prompt-injection patterns and cap length before LLM calls.
    Does not block legitimate legal questions mentioning 'ignore' in case law context.
    """
    if not text:
        return ""
    limit = max_len if max_len is not None else _MAX_USER_PROMPT_LEN
    cleaned = text.strip()[:limit]
    for pat in _INJECTION_PATTERNS:
        cleaned = pat.sub("[filtered]", cleaned)
    # Collapse excessive role-play delimiters
    cleaned = re.sub(r"(?i)(system\s*:\s*){3,}", "system: ", cleaned)
    return cleaned.strip()


def injection_risk_score(text: str) -> float:
    """0.0 = clean, 1.0 = high risk (for logging/metrics only)."""
    if not text:
        return 0.0
    hits = sum(1 for pat in _INJECTION_PATTERNS if pat.search(text))
    return min(1.0, hits * 0.35)
