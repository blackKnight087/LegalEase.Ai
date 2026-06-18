"""Import cause list text into matter hearings."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.core.matter_hearings_intel import schedule_hearing


def parse_cause_list_text(text: str) -> List[Dict[str, str]]:
    """Parse pasted cause list / court bulletin text into hearing rows."""
    items: List[Dict[str, str]] = []
    if not (text or "").strip():
        return items

    date_pat = re.compile(
        r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
        re.I,
    )
    court_pat = re.compile(
        r"(?:before|hon'ble|justice)\s+([^\n,]{5,60})",
        re.I,
    )

    blocks = re.split(r"\n\s*\n", text)
    for block in blocks:
        dm = date_pat.search(block)
        if not dm:
            continue
        court = ""
        cm = court_pat.search(block)
        if cm:
            court = cm.group(1).strip()
        purpose = block.strip()[:300]
        items.append(
            {
                "hearing_date": dm.group(1),
                "court_name": court,
                "purpose": purpose,
            }
        )

    if not items:
        for line in text.splitlines():
            dm = date_pat.search(line)
            if dm:
                items.append(
                    {
                        "hearing_date": dm.group(1),
                        "court_name": "",
                        "purpose": line.strip()[:200],
                    }
                )
    return items


def import_cause_list_to_matter(
    user_id: str,
    matter_id: str,
    text: str,
) -> Dict[str, Any]:
    parsed = parse_cause_list_text(text)
    inserted = 0
    errors: List[str] = []
    for row in parsed:
        try:
            schedule_hearing(
                user_id,
                matter_id,
                hearing_date=row.get("hearing_date", ""),
                court_name=row.get("court_name", ""),
                purpose=row.get("purpose", "Cause list")[:200],
                notes="Imported from cause list",
            )
            inserted += 1
        except Exception as exc:
            errors.append(str(exc)[:120])
    return {"ok": True, "parsed": len(parsed), "inserted": inserted, "errors": errors}
