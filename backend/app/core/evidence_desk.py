"""Litigation Evidence Desk — firm-wide contradictions across matters."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from backend.app.core.matter_enhancements import extract_and_persist_contradictions, list_contradictions
from backend.app.core.matter_repo import list_matters, list_matter_documents


def get_evidence_desk(user_id: str) -> Dict[str, Any]:
    """Aggregate contradictions and blind spots across all matters."""
    matters = list_matters(user_id, limit=200, include_archived=False)
    items: List[Dict[str, Any]] = []
    blind_spots: List[Dict[str, Any]] = []
    matters_with_cx = 0

    for m in matters:
        mid = str(m.get("matter_id") or "")
        mname = str(m.get("matter_name") or "")
        if not mid:
            continue

        pairs = list_contradictions(user_id, mid)
        if pairs:
            matters_with_cx += 1
            for p in pairs:
                items.append(
                    {
                        "matter_id": mid,
                        "matter_name": mname,
                        "contradiction_id": p.get("contradiction_id"),
                        "contradiction_type": p.get("contradiction_type"),
                        "topic": p.get("topic"),
                        "statement_a": p.get("statement_a"),
                        "statement_b": p.get("statement_b"),
                        "confidence": p.get("confidence"),
                        "source_hint": p.get("source_hint"),
                        "created_at": p.get("created_at"),
                    }
                )
        else:
            docs = list_matter_documents(user_id, mid)
            if docs:
                blind_spots.append(
                    {
                        "matter_id": mid,
                        "matter_name": mname,
                        "document_count": len(docs),
                        "reason": "Documents uploaded but no contradictions scanned yet",
                    }
                )

    items.sort(
        key=lambda x: (
            -(float(x.get("confidence") or 0)),
            x.get("matter_name") or "",
        )
    )

    return {
        "ok": True,
        "summary": {
            "total_matters": len(matters),
            "matters_with_contradictions": matters_with_cx,
            "contradiction_count": len(items),
            "blind_spot_count": len(blind_spots),
        },
        "contradictions": items[:100],
        "blind_spots": blind_spots[:30],
    }


def export_evidence_desk_markdown(user_id: str) -> str:
    """Firm-wide contradictions report for counsel review."""
    desk = get_evidence_desk(user_id)
    lines = [
        "# Litigation Evidence Desk — Firm Report",
        "",
        f"**Matters scanned:** {desk.get('summary', {}).get('total_matters', 0)}  ",
        f"**With contradictions:** {desk.get('summary', {}).get('matters_with_contradictions', 0)}  ",
        f"**Total pairs:** {desk.get('summary', {}).get('contradiction_count', 0)}",
        "",
        "## Contradictions",
        "",
    ]
    for c in desk.get("contradictions") or []:
        lines.append(f"### {c.get('matter_name')} — {c.get('topic') or c.get('contradiction_type')}")
        lines.append(f"- **A:** {c.get('statement_a', '')[:300]}")
        lines.append(f"- **B:** {c.get('statement_b', '')[:300]}")
        lines.append(f"- Confidence: {c.get('confidence', '')}")
        lines.append("")
    blind = desk.get("blind_spots") or []
    if blind:
        lines.append("## Needs scan (documents, no contradictions yet)")
        for b in blind[:20]:
            lines.append(f"- {b.get('matter_name')} ({b.get('document_count')} docs)")
    return "\n".join(lines).strip()


def scan_all_matters(
    user_id: str,
    *,
    max_matters: int = 10,
    scan_all: bool = False,
) -> Dict[str, Any]:
    """Run contradiction extraction on matters with documents (capped)."""
    default_cap = 50 if scan_all else 8
    cap = max(1, min(max_matters, int(os.getenv("EVIDENCE_DESK_SCAN_MAX", str(default_cap)))))
    matters = list_matters(user_id, limit=200, include_archived=False)
    scanned: List[Dict[str, Any]] = []
    errors: List[str] = []

    candidates = []
    for m in matters:
        mid = str(m.get("matter_id") or "")
        if not mid:
            continue
        docs = list_matter_documents(user_id, mid)
        if docs:
            candidates.append(m)

    batch = candidates if scan_all else candidates[:cap]
    for m in batch:
        mid = str(m.get("matter_id") or "")
        try:
            result = extract_and_persist_contradictions(user_id, mid)
            scanned.append(
                {
                    "matter_id": mid,
                    "matter_name": m.get("matter_name"),
                    "pairs_found": len(result.get("pairs") or []),
                }
            )
        except Exception as exc:
            errors.append(f"{m.get('matter_name')}: {exc}"[:120])

    return {
        "ok": True,
        "scanned": scanned,
        "scan_cap": cap,
        "candidates_total": len(candidates),
        "errors": errors,
        "desk": get_evidence_desk(user_id),
    }
