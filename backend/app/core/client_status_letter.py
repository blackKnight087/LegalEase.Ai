"""Client status letter from matter dashboard state."""
from __future__ import annotations

from typing import Any, Dict

from backend.app.core.matter_workflow import get_matter_dashboard


def draft_client_status_letter(user_id: str, matter_id: str) -> Dict[str, Any]:
    dash = get_matter_dashboard(user_id, matter_id)
    if not dash.get("matter"):
        return {"ok": False, "error": "Matter not found", "letter": ""}

    m = dash["matter"]
    timeline = dash.get("timeline") or []
    hearings = dash.get("hearings") or []
    tasks = [t for t in (dash.get("tasks") or []) if t.get("status") == "open"]
    deadlines = [d for d in (dash.get("deadlines") or []) if d.get("status") == "pending"]

    lines = [
        f"Dear {m.get('client_name') or 'Client'},",
        "",
        f"We are writing to update you on your matter **{m.get('matter_name', '')}** "
        f"({m.get('case_number') or 'reference on file'}).",
        "",
        "## Current status",
        f"The matter is listed as **{m.get('status_tier', 'active')}** before **{m.get('venue') or 'the court'}**.",
        "",
    ]

    if hearings:
        lines.append("## Upcoming hearings")
        for h in hearings[:3]:
            lines.append(
                f"- {h.get('hearing_date', '—')}: {h.get('purpose') or 'Court appearance'} "
                f"({h.get('court_name') or m.get('venue') or ''})"
            )
        lines.append("")

    if timeline:
        lines.append("## Recent developments")
        for ev in timeline[-5:]:
            lines.append(f"- {ev.get('event_date', '')}: {ev.get('title', '')}")
        lines.append("")

    if tasks or deadlines:
        lines.append("## Our next steps")
        for t in tasks[:5]:
            lines.append(f"- {t.get('title', 'Task')}")
        for d in deadlines[:5]:
            lines.append(f"- Deadline {d.get('due_date', '')}: {d.get('title', '')}")
        lines.append("")

    lines.extend([
        "Please contact us if you have questions or documents to share.",
        "",
        "Regards,",
        "[Advocate / Firm name]",
        "",
        "---",
        "*This draft is for your review — not legal advice to third parties without your sign-off.*",
    ])

    return {"ok": True, "letter": "\n".join(lines), "matter_id": matter_id}
