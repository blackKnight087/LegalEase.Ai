"""Lightweight follow-up suggestions — no Streamlit dependency."""
from __future__ import annotations

import re
from typing import List


def suggest_follow_ups(question: str, answer: str, mode: str) -> List[str]:
    q = (question or "").lower()
    if mode == "web_search":
        return ["Latest court position", "Practical next steps", "Related sections"]
    if "section" in q or re.search(r"\b\d{3}\b", q):
        return ["Explain in simple language", "What is the punishment?", "Compare related sections"]
    return ["Summarize key points", "Explain for a non-lawyer", "What should I do next?"]
