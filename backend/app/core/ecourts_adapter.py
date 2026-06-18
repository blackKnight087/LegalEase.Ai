"""eCourts / cause-list integration adapter (Phase 6).



Modes:

- `paste` — free; user pastes cause list text or PDF (via court-day)

- `ecourtsindia` — live cause list via eCourtsIndia partner API (~₹3/call PAYG)

- `ecourts_api` — legacy government stub (partnership)

"""

from __future__ import annotations



import os

import re

from datetime import datetime

from typing import Any, Dict, List, Optional



ECOURTS_API_ENABLED = os.getenv("ECOURTS_API_ENABLED", "0").lower() in {"1", "true", "yes"}

ECOURTS_API_BASE = os.getenv("ECOURTS_API_BASE", "https://hcservices.ecourts.gov.in").strip()



_DATE_PATTERNS = [

    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b"),

    re.compile(

        r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b",

        re.I,

    ),

]





def integration_status(user_id: str = "") -> Dict[str, Any]:

    from backend.app.core.court_sync_settings import get_court_sync_settings



    settings = get_court_sync_settings(user_id) if user_id else {}

    api_configured = bool(settings.get("api_configured"))

    return {

        "live_api_enabled": api_configured,

        "api_provider": "ecourtsindia",

        "api_configured": api_configured,

        "api_key_masked": settings.get("api_key_masked", ""),

        "api_key_source": settings.get("api_key_source", ""),

        "preferred_mode": settings.get("preferred_mode", "paste"),

        "modes": [

            {

                "id": "paste",

                "label": "Paste / PDF",

                "cost_note": "Free — unlimited",

                "recommended_for": "Daily cause lists, demos, saving API credits",

            },

            {

                "id": "ecourtsindia",

                "label": "eCourtsIndia API",

                "cost_note": "~₹3 per sync on PAYG (₹200 free signup credits)",

                "recommended_for": "Quick lookup by date/state/case without copying text",

            },

        ],

        "supported_sources": ["paste", "ecourtsindia", "ecourts_api_stub"],

        "sync_status": "ready",

        "note": (

            "Hybrid sync: upload/paste PDF is free and unlimited. eCourtsIndia API uses credits "

            "(~₹3/cause-list sync, ~₹1.50/CNR). Use paste for daily bulletins; API for targeted lookups."

        ),

    }





def parse_hearing_dates_from_text(text: str) -> List[Dict[str, str]]:

    """Extract hearing dates from pasted cause-list lines."""

    found: List[Dict[str, str]] = []

    seen: set[str] = set()

    for line in (text or "").splitlines():

        line = line.strip()

        if not line:

            continue

        for pat in _DATE_PATTERNS:

            for m in pat.finditer(line):

                raw = m.group(0)

                if raw in seen:

                    continue

                seen.add(raw)

                iso = _normalize_date(raw)

                found.append(

                    {

                        "raw": raw,

                        "iso_date": iso,

                        "line_preview": line[:120],

                    }

                )

    return found[:200]





def _normalize_date(raw: str) -> str:

    raw = raw.strip()

    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y", "%d.%m.%y"):

        try:

            return datetime.strptime(raw, fmt).date().isoformat()

        except ValueError:

            continue

    try:

        return datetime.strptime(raw, "%d %b %Y").date().isoformat()

    except ValueError:

        return raw





def _finish_paste_sync(

    user_id: str,

    text: str,

    *,

    auto_schedule: bool,

    sync_status: Dict[str, Any],

    api_meta: Optional[Dict[str, Any]] = None,

) -> Dict[str, Any]:

    hearing_dates = parse_hearing_dates_from_text(text)

    sync_status["hearing_dates_parsed"] = len(hearing_dates)

    from backend.app.core.court_day import import_matched_rows, parse_and_match_cause_list



    parsed = parse_and_match_cause_list(user_id, text)

    sync_status["rows_matched"] = len(parsed.get("rows") or [])

    sync_status["phase"] = "parsed"

    scheduled: List[Dict[str, Any]] = []

    if auto_schedule:

        imp = import_matched_rows(user_id, parsed.get("rows") or [])

        scheduled = [imp]

        sync_status["phase"] = "scheduled"

    sync_status["phase"] = "complete"

    out: Dict[str, Any] = {

        "ok": True,

        "parsed": parsed,

        "hearing_dates": hearing_dates,

        "scheduled_hearings": scheduled,

        "sync_status": sync_status,

    }

    if api_meta:

        out["api"] = api_meta

    _record_sync_log(user_id, out.get("source") or "paste", out)

    return out





def _record_sync_log(user_id: str, source: str, out: Dict[str, Any]) -> None:
    try:
        from backend.app.core.court_sync_log import append_court_sync_log

        parsed = out.get("parsed") or {}
        rows = parsed.get("rows") or []
        parsed_count = int(parsed.get("parsed_count") or len(rows))
        matched_count = sum(
            1
            for r in rows
            if r.get("selected") and (r.get("suggested_matter_id") or r.get("matter_id"))
        )
        unmatched_count = max(0, parsed_count - matched_count)
        scheduled = (out.get("scheduled_hearings") or [{}])[0]
        inserted = int(scheduled.get("inserted", 0)) if isinstance(scheduled, dict) else 0
        skipped = int(scheduled.get("skipped", 0)) if isinstance(scheduled, dict) else 0
        errors = list(scheduled.get("errors") or []) if isinstance(scheduled, dict) else []
        if out.get("error"):
            errors.append(str(out["error"]))
        confidences = {r.get("confidence") for r in rows if r.get("confidence")}
        confidence = next(iter(confidences)) if len(confidences) == 1 else ("mixed" if confidences else "")
        status = "ok" if out.get("ok") else "error"
        append_court_sync_log(
            user_id,
            source=source,
            status=status,
            parsed_count=parsed_count,
            matched_count=matched_count,
            inserted_count=inserted,
            skipped_count=skipped,
            errors=errors,
            confidence=confidence or "",
            detail=f"unmatched={unmatched_count}",
        )
    except Exception:
        pass


def sync_cause_list(

    user_id: str,

    *,

    source: str = "paste",

    text: str = "",

    court_code: str = "",

    bench_id: str = "",

    hearing_date: str = "",

    auto_schedule: bool = False,

    api_date: str = "",

    api_state: str = "",

    api_query: str = "",

    api_advocate: str = "",

    api_litigant: str = "",

    api_limit: int = 50,

    api_key_override: str = "",

    api_district_code: str = "",

    api_court_complex_code: str = "",

) -> Dict[str, Any]:

    src = (source or "paste").strip().lower()

    sync_status: Dict[str, Any] = {

        "phase": "started",

        "source": src,

        "hearing_dates_parsed": 0,

        "rows_matched": 0,

    }

    if src == "paste":

        if not (text or "").strip():

            err_out = {"ok": False, "error": "Cause list text required for paste source", "sync_status": sync_status}

            _record_sync_log(user_id, "paste", err_out)

            return err_out

        out = _finish_paste_sync(user_id, text, auto_schedule=auto_schedule, sync_status=sync_status)

        out["source"] = "paste"

        return out



    if src == "ecourtsindia":

        from backend.app.core.court_sync_settings import resolve_ecourtsindia_api_key

        from backend.app.core.ecourtsindia_client import (

            ECourtsIndiaError,

            cause_list_results_to_text,

            search_cause_list,

        )



        api_key = resolve_ecourtsindia_api_key(user_id, api_key_override)

        if not api_key:

            err_out = {

                "ok": False,

                "error": (

                    "eCourtsIndia API key not configured. Add ECOURTSINDIA_API_KEY in .env "

                    "or save your key in Court Sync settings."

                ),

                "sync_status": sync_status,

            }

            _record_sync_log(user_id, "ecourtsindia", err_out)

            return err_out

        sync_status["phase"] = "fetching_api"

        try:

            api_out = search_cause_list(

                api_key,

                date=api_date or hearing_date,

                state=api_state,

                q=api_query,

                advocate=api_advocate,

                litigant=api_litigant,

                district_code=api_district_code,

                court_complex_code=api_court_complex_code,

                limit=api_limit,

            )

        except ECourtsIndiaError as exc:

            err_out = {

                "ok": False,

                "error": str(exc),

                "sync_status": {**sync_status, "phase": "api_error", "code": exc.code},

            }

            _record_sync_log(user_id, "ecourtsindia", err_out)

            return err_out

        results = api_out.get("results") or []

        api_meta = {

            "provider": "ecourtsindia",

            "billed_calls": 1,

            "returned_count": api_out.get("returned_count", len(results)),

            "request_id": api_out.get("request_id", ""),

            "cost_note": "One API call per sync (~₹3 PAYG). Use paste mode to save credits.",

        }

        if not results:

            err_out = {

                "ok": False,

                "error": "API returned no cause list entries for those filters. Try paste mode or adjust date/state/query.",

                "api": api_meta,

                "sync_status": {**sync_status, "phase": "empty"},

            }

            _record_sync_log(user_id, "ecourtsindia", err_out)

            return err_out

        cause_text = cause_list_results_to_text(results, default_date=api_date or hearing_date)

        sync_status["api_results"] = len(results)

        out = _finish_paste_sync(

            user_id,

            cause_text,

            auto_schedule=auto_schedule,

            sync_status=sync_status,

            api_meta=api_meta,

        )

        out["source"] = "ecourtsindia"

        out["api_raw_count"] = len(results)

        return out



    if src in {"ecourts_api", "ecourts_api_stub"}:

        sync_status["phase"] = "blocked"

        if not ECOURTS_API_ENABLED:

            return {

                "ok": False,

                "error": "Government eCourts API not enabled. Use paste or ecourtsindia mode instead.",

                "stub": True,

                "requested": {

                    "court_code": court_code,

                    "bench_id": bench_id,

                    "hearing_date": hearing_date,

                },

                "sync_status": sync_status,

            }

        raise NotImplementedError("eCourts HTTP client ships with government API credentials.")

    return {"ok": False, "error": f"Unknown source: {source}", "sync_status": sync_status}


