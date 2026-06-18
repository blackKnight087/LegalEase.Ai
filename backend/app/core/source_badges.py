"""Source trust tier badges for web results."""
from __future__ import annotations

from typing import Any, Dict, List


def badge_for_url(href: str) -> str:
    try:
        from legal_web_engine import source_trust_tier

        tier = source_trust_tier(href or "")
    except ImportError:
        tier = 3
    if tier == 1:
        return "Official"
    if tier == 2:
        return "Legal Media"
    if tier == 3:
        return "Scholarly"
    if tier == 4:
        return "General"
    return "Web"


def enrich_web_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in sources or []:
        row = dict(s)
        href = str(row.get("href") or "")
        row["trust_badge"] = badge_for_url(href)
        if "gov.in" in href or "sci.gov.in" in href:
            row["trust_badge"] = "Official"
        elif "wikipedia" in href:
            row["trust_badge"] = "Wiki"
        date = str(row.get("date") or row.get("published") or "")
        if date:
            row["freshness"] = date[:10]
        elif "gov.in" in href or "indiankanoon" in href:
            row["freshness"] = "Official archive"
        else:
            row["freshness"] = "Live"
        out.append(row)
    return out
