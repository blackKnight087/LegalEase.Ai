"""LLM-assisted cause list parsing when heuristic parser finds few rows."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def llm_parse_enabled() -> bool:
    return os.getenv("LITIGATION_LLM_PARSE", "1").lower() in {"1", "true", "yes"}


def parse_cause_list_with_llm(text: str) -> List[Dict[str, str]]:
    """
    Extract hearing rows from messy cause-list text via local Ollama.
    Returns list of {hearing_date, court_name, purpose}.
    """
    if not llm_parse_enabled() or len((text or "").strip()) < 30:
        return []

    snippet = (text or "").strip()[:12000]
    prompt = (
        "Extract court cause-list entries from the text below. "
        "Return ONLY a JSON array. Each object must have keys: "
        "hearing_date (DD-MM-YYYY or DD Mon YYYY), court_name, purpose (one line summary). "
        "If no entries, return [].\n\nTEXT:\n"
        f"{snippet}"
    )
    try:
        from llms import get_generator

        client = get_generator()
        if not client:
            return []
        raw = client.generate(prompt, max_tokens=2048, temperature=0.1)
        if not raw:
            return []
        m = re.search(r"\[[\s\S]*\]", raw)
        if not m:
            return []
        data = json.loads(m.group(0))
        if not isinstance(data, list):
            return []
        out: List[Dict[str, str]] = []
        for item in data[:80]:
            if not isinstance(item, dict):
                continue
            purpose = str(item.get("purpose") or item.get("listing") or "").strip()
            if not purpose:
                continue
            out.append(
                {
                    "hearing_date": str(item.get("hearing_date") or item.get("date") or ""),
                    "court_name": str(item.get("court_name") or item.get("court") or ""),
                    "purpose": purpose[:400],
                }
            )
        return out
    except Exception as exc:
        logger.warning("[court_day_llm] parse failed: %s", exc)
        return []
