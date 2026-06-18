"""Strip chat routing prefixes before KB retrieval / memory."""
from __future__ import annotations

import re

_USER_QUESTION_RE = re.compile(r"User question:\s*(.+)$", re.I | re.S)
_MATTER_RULES_RE = re.compile(r"^MATTER AI RULES:", re.I)
_LEARNER_RE = re.compile(r"^LEARNER MODE:", re.I)


def strip_chat_routing_prefix(query: str) -> str:
    """Return the user's actual question without matter/learner routing wrappers."""
    text = (query or "").strip()
    if not text:
        return text
    text = re.sub(r"^[\s:;,.]+", "", text)
    text = re.sub(r"^(?:#+\s+[^\n]+\n+)+", "", text).strip()
    m = _USER_QUESTION_RE.search(text)
    if m:
        return m.group(1).strip()
    if _MATTER_RULES_RE.match(text):
        return ""
    if _LEARNER_RE.match(text):
        parts = re.split(r"\n\n+", text, maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else text
    return text
