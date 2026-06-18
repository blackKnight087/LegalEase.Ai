"""Indian limitation / prescription deadline presets."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

PRESETS: List[Dict[str, Any]] = [
    {
        "id": "ni_138",
        "label": "NI Act Section 138 (cheque dishonour)",
        "days": 30,
        "description": "Complaint within 30 days from expiry of 15-day notice period (verify notice date).",
    },
    {
        "id": "consumer",
        "label": "Consumer forum complaint",
        "days": 730,
        "description": "Generally 2 years from cause of action (Consumer Protection Act).",
    },
    {
        "id": "cpc_appeal_60",
        "label": "First appeal (CPC)",
        "days": 60,
        "description": "60 days from decree/judgment (extendable).",
    },
    {
        "id": "cpc_appeal_90",
        "label": "First appeal (other)",
        "days": 90,
        "description": "90 days where 60-day period not applicable.",
    },
    {
        "id": "bail_anticipatory",
        "label": "Anticipatory bail urgency",
        "days": 7,
        "description": "Practical prep window — file before coercive steps.",
    },
    {
        "id": "fir_quashing_60",
        "label": "Quashing petition follow-up",
        "days": 60,
        "description": "Track court listing after filing (practice note).",
    },
    {
        "id": "arbitration_120",
        "label": "Arbitration statement of claim",
        "days": 120,
        "description": "Check limitation under Limitation Act + contract clause.",
    },
    {
        "id": "limitation_3yr",
        "label": "Limitation Act — 3 years (general)",
        "days": 1095,
        "description": "Many civil suits — 3 years from cause of action.",
    },
]


def list_limitation_presets() -> List[Dict[str, Any]]:
    return list(PRESETS)


def calculate_limitation(
    preset_id: str,
    start_date: str,
) -> Dict[str, Any]:
    preset = next((p for p in PRESETS if p["id"] == preset_id), None)
    if not preset:
        return {"ok": False, "error": "Unknown preset"}
    try:
        start = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return {"ok": False, "error": "Invalid start_date (use YYYY-MM-DD)"}
    days = int(preset.get("days", 30))
    due = start + timedelta(days=days)
    return {
        "ok": True,
        "preset_id": preset_id,
        "label": preset["label"],
        "description": preset["description"],
        "start_date": start.isoformat(),
        "due_date": due.isoformat(),
        "days": days,
        "days_remaining": (due - date.today()).days,
    }
