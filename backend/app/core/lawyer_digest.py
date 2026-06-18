"""Daily cause list and hearing digest across all matters."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.matter_hearings_intel import list_hearings
from backend.app.core.matter_repo import list_matters


def _parse_hearing_date(raw: str) -> Optional[date]:
    s = (raw or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    m2 = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if m2:
        mon = months.get(m2.group(2).lower()[:3])
        if mon:
            try:
                return date(int(m2.group(3)), mon, int(m2.group(1)))
            except ValueError:
                return None
    return None


def get_hearing_digest(
    user_id: str,
    *,
    days_ahead: int = 14,
    days_back: int = 1,
) -> Dict[str, Any]:
    """Aggregate hearings across matters — today, this week, upcoming."""
    today = date.today()
    end = today + timedelta(days=max(1, days_ahead))
    start = today - timedelta(days=max(0, days_back))

    matters = list_matters(user_id, include_archived=False)
    matter_names = {m["matter_id"]: m.get("matter_name", "") for m in matters}

    today_items: List[Dict[str, Any]] = []
    week_items: List[Dict[str, Any]] = []
    upcoming: List[Dict[str, Any]] = []

    for mid in matter_names:
        for h in list_hearings(user_id, mid):
            hd = _parse_hearing_date(h.get("hearing_date") or "")
            nh = _parse_hearing_date(h.get("next_hearing_date") or "")
            for label, d in (("hearing", hd), ("next", nh)):
                if not d or d < start or d > end:
                    continue
                item = {
                    "matter_id": mid,
                    "matter_name": matter_names.get(mid, ""),
                    "hearing_id": h.get("hearing_id"),
                    "hearing_date": h.get("hearing_date") or str(d),
                    "court_name": h.get("court_name", ""),
                    "purpose": h.get("purpose", ""),
                    "judge": h.get("judge", ""),
                    "status": h.get("status", ""),
                    "date_sort": d.isoformat(),
                    "date_kind": label,
                }
                upcoming.append(item)
                if d == today:
                    today_items.append(item)
                if today <= d <= today + timedelta(days=7):
                    week_items.append(item)

    upcoming.sort(key=lambda x: x.get("date_sort", ""))
    today_items.sort(key=lambda x: x.get("date_sort", ""))
    week_items.sort(key=lambda x: x.get("date_sort", ""))

    return {
        "today": today_items,
        "this_week": week_items,
        "upcoming": upcoming[:50],
        "today_count": len(today_items),
        "week_count": len(week_items),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
