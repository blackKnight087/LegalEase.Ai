"""Court Day Command Center — cause list parsing, matter matching, prep."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.cause_list_import import parse_cause_list_text
from backend.app.core.lawyer_digest import get_hearing_digest
from backend.app.core.matter_hearings_intel import schedule_hearing
from backend.app.core.matter_repo import list_matters


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().strip())


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]{3,}", _norm(text))


def _score_matter(line: str, matter: Dict[str, Any]) -> Tuple[float, str]:
    """Return (score 0-1, confidence label)."""
    line_l = _norm(line)
    if not line_l:
        return 0.0, "none"

    case_no = _norm(str(matter.get("case_number") or ""))
    if case_no and len(case_no) >= 4 and case_no in line_l:
        return 0.95, "high"

    scores: List[float] = []
    for field in ("matter_name", "client_name", "opposing_party", "venue"):
        val = _norm(str(matter.get(field) or ""))
        if not val or len(val) < 4:
            continue
        if val in line_l:
            scores.append(0.85)
            continue
        vt = _tokens(val)
        lt = set(_tokens(line))
        if not vt:
            continue
        overlap = len(set(vt) & lt) / max(len(vt), 1)
        if overlap >= 0.6:
            scores.append(0.5 + overlap * 0.35)

    if not scores:
        return 0.0, "none"
    best = max(scores)
    if best >= 0.8:
        return best, "high"
    if best >= 0.55:
        return best, "medium"
    return best, "low"


def parse_and_match_cause_list(user_id: str, text: str) -> Dict[str, Any]:
    """Parse cause list and suggest matter matches per row."""
    rows = parse_cause_list_text(text)
    parser_used = "heuristic"
    if len(rows) < 1 and (text or "").strip():
        from backend.app.core.court_day_llm import parse_cause_list_with_llm

        llm_rows = parse_cause_list_with_llm(text)
        if llm_rows:
            rows = llm_rows
            parser_used = "llm"
    matters = list_matters(user_id, limit=200, include_archived=False)
    parsed: List[Dict[str, Any]] = []

    for i, row in enumerate(rows):
        line = row.get("purpose") or ""
        best_mid = ""
        best_name = ""
        best_score = 0.0
        best_conf = "none"
        alts: List[Dict[str, Any]] = []

        for m in matters:
            sc, conf = _score_matter(line, m)
            if sc > best_score:
                best_score = sc
                best_conf = conf
                best_mid = str(m.get("matter_id") or "")
                best_name = str(m.get("matter_name") or "")
            if sc >= 0.45:
                alts.append(
                    {
                        "matter_id": m.get("matter_id"),
                        "matter_name": m.get("matter_name"),
                        "score": round(sc, 2),
                        "confidence": conf,
                    }
                )

        alts.sort(key=lambda x: -float(x.get("score") or 0))
        parsed.append(
            {
                "row_index": i,
                "hearing_date": row.get("hearing_date", ""),
                "court_name": row.get("court_name", ""),
                "purpose": line[:400],
                "suggested_matter_id": best_mid if best_score >= 0.45 else "",
                "suggested_matter_name": best_name,
                "match_score": round(best_score, 2),
                "confidence": best_conf,
                "alternatives": alts[:4],
                "selected": best_score >= 0.55,
            }
        )

    return {
        "ok": True,
        "parsed_count": len(parsed),
        "parser": parser_used,
        "rows": parsed,
        "matters": [
            {"matter_id": m.get("matter_id"), "matter_name": m.get("matter_name")}
            for m in matters
        ],
    }


def import_matched_rows(
    user_id: str,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Import selected rows into matched matters."""
    inserted = 0
    skipped = 0
    errors: List[str] = []

    for row in rows:
        if not row.get("selected"):
            skipped += 1
            continue
        mid = str(row.get("matter_id") or row.get("suggested_matter_id") or "")
        if not mid:
            skipped += 1
            continue
        try:
            schedule_hearing(
                user_id,
                mid,
                hearing_date=str(row.get("hearing_date") or ""),
                court_name=str(row.get("court_name") or ""),
                purpose=str(row.get("purpose") or "Cause list")[:200],
                notes="Imported from Court Day cause list",
            )
            inserted += 1
        except Exception as exc:
            errors.append(str(exc)[:120])

    return {
        "ok": True,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }


def get_court_day_today(user_id: str, *, days_ahead: int = 14) -> Dict[str, Any]:
    """Today's board + Mission Control KPIs when litigation_os is available."""
    try:
        from backend.app.core.litigation_os import get_litigation_dashboard

        dash = get_litigation_dashboard(user_id)
        digest = get_hearing_digest(user_id, days_ahead=days_ahead)
        return {
            "ok": True,
            **dash,
            "digest": digest,
            "summary": {
                "today_count": dash.get("today_hearings", 0),
                "week_count": dash.get("this_week_hearings", 0),
                "upcoming_count": dash.get("upcoming_hearings", 0),
            },
        }
    except Exception:
        pass
    digest = get_hearing_digest(user_id, days_ahead=days_ahead)
    return {
        "ok": True,
        "digest": digest,
        "summary": {
            "today_count": len(digest.get("today") or []),
            "week_count": len(digest.get("this_week") or []),
            "upcoming_count": len(digest.get("upcoming") or []),
        },
    }


def get_prep_pack(user_id: str, matter_id: str, *, use_ai: bool = True) -> Dict[str, Any]:
    from backend.app.core.hearing_prep_pack import build_hearing_prep_pack

    return build_hearing_prep_pack(user_id, matter_id, use_ai=use_ai)
