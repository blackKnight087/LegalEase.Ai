"""Export firm-wide hearings as ICS for calendar apps."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from backend.app.core.lawyer_digest import get_hearing_digest


def _escape_ics(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )[:800]


def _parse_date_for_ics(raw: str) -> date | None:
    from backend.app.core.lawyer_digest import _parse_hearing_date

    return _parse_hearing_date(raw)


def build_hearings_ics(user_id: str, *, days_ahead: int = 60) -> str:
    digest = get_hearing_digest(user_id, days_ahead=days_ahead)
    items: List[Dict[str, Any]] = []
    for bucket in ("today", "this_week", "upcoming"):
        items.extend(digest.get(bucket) or [])

    seen: set[str] = set()
    events: List[str] = []
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for h in items:
        key = f"{h.get('matter_id')}-{h.get('hearing_date')}-{h.get('purpose', '')[:40]}"
        if key in seen:
            continue
        seen.add(key)
        d = _parse_date_for_ics(str(h.get("hearing_date") or ""))
        if not d:
            continue
        start = d.strftime("%Y%m%d")
        end = (d + timedelta(days=1)).strftime("%Y%m%d")
        summary = _escape_ics(f"{h.get('matter_name', 'Hearing')} — {h.get('court_name', '')}")
        desc = _escape_ics(
            f"Matter: {h.get('matter_name', '')}\n"
            f"Court: {h.get('court_name', '')}\n"
            f"Purpose: {h.get('purpose', '')}\n"
            f"LegalEase Litigation Desk"
        )
        uid = f"legalease-{key.replace(' ', '-')[:80]}@legalease.ai"
        events.append(
            "\r\n".join(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{now}",
                    f"DTSTART;VALUE=DATE:{start}",
                    f"DTEND;VALUE=DATE:{end}",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{desc}",
                    "END:VEVENT",
                ]
            )
        )

    cal = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//LegalEase.AI//Litigation Desk//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            *events,
            "END:VCALENDAR",
        ]
    )
    return cal + "\r\n"
