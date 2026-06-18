"""eCourtsIndia case lookup and matter sync."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from backend.app.core.court_sync_settings import resolve_ecourtsindia_api_key
from backend.app.core.litigation_os import save_court_order
from backend.app.core.matter_hearings_intel import schedule_hearing
from backend.app.core.matter_repo import get_matter, update_matter


def _require_api_key(user_id: str) -> str:
    from backend.app.core.ecourtsindia_client import ECourtsIndiaError

    key = resolve_ecourtsindia_api_key(user_id)
    if not key:
        raise ECourtsIndiaError(
            "eCourtsIndia API key not configured. Add ECOURTSINDIA_API_KEY in .env "
            "or save your key in Court Sync settings."
        )
    return key


def _case_blob(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") or payload
    if isinstance(data, dict) and isinstance(data.get("courtCaseData"), dict):
        return data["courtCaseData"]
    if isinstance(data, dict):
        return data
    return {}


def _first_str(*vals: Any) -> str:
    for v in vals:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _parties_label(case: Dict[str, Any]) -> str:
    petitioners = case.get("petitioners") or []
    respondents = case.get("respondents") or []
    if isinstance(petitioners, list) and isinstance(respondents, list):
        p = ", ".join(str(x).strip() for x in petitioners if str(x).strip())
        r = ", ".join(str(x).strip() for x in respondents if str(x).strip())
        if p or r:
            return f"{p} v {r}".strip(" v")
    entries = case.get("businessOnDateEntries") or []
    if entries and isinstance(entries[0], dict):
        p = _first_str(entries[0].get("petitioner"))
        r = _first_str(entries[0].get("respondent"))
        if p or r:
            return f"{p} v {r}".strip(" v")
    return _first_str(case.get("party"), case.get("parties"))


def _hearing_rows(case: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    court = _first_str(case.get("courtName"))
    for item in case.get("historyOfCaseHearings") or []:
        if not isinstance(item, dict):
            continue
        hdate = _first_str(item.get("hearingDate"), item.get("businessOnDate"))
        if not hdate:
            continue
        rows.append(
            {
                "hearing_date": hdate,
                "court_name": court,
                "purpose": _first_str(item.get("purposeOfListing"), item.get("purpose")),
                "judge": _first_str(item.get("judge")),
            }
        )
    next_date = _first_str(case.get("nextHearingDate"))
    if next_date and not any(r["hearing_date"] == next_date for r in rows):
        rows.append(
            {
                "hearing_date": next_date,
                "court_name": court,
                "purpose": _first_str(case.get("purpose"), "Next hearing"),
                "judge": "",
            }
        )
    return rows


def _order_rows(case: Dict[str, Any], cnr: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    court = _first_str(case.get("courtName"))
    for item in case.get("interimOrders") or []:
        if not isinstance(item, dict):
            continue
        fname = _first_str(item.get("orderUrl"), item.get("filename"), item.get("fileName"))
        rows.append(
            {
                "order_id_seed": f"{cnr}:{fname or item.get('orderDate', '')}",
                "title": _first_str(item.get("description"), fname, "Court order"),
                "order_date": _first_str(item.get("orderDate")),
                "court_name": court,
                "summary": fname,
            }
        )
    for item in case.get("files") or []:
        if not isinstance(item, dict):
            continue
        fname = _first_str(item.get("filename"), item.get("fileName"), item.get("name"))
        if not fname:
            continue
        rows.append(
            {
                "order_id_seed": f"{cnr}:{fname}",
                "title": _first_str(item.get("description"), fname),
                "order_date": _first_str(item.get("orderDate"), item.get("date")),
                "court_name": court,
                "summary": _first_str(item.get("markdownContent"), fname)[:500],
            }
        )
    return rows


def fetch_case_preview(user_id: str, cnr: str) -> Dict[str, Any]:
    from backend.app.core.ecourtsindia_client import get_case_by_cnr, normalize_cnr

    key = _require_api_key(user_id)
    normalized = normalize_cnr(cnr)
    out = get_case_by_cnr(key, normalized)
    case = _case_blob(out)
    hearings = _hearing_rows(case)
    orders = _order_rows(case, normalized)
    order_count = max(len(orders), int(case.get("orderCount") or 0))
    return {
        "ok": True,
        "cnr": normalized,
        "case_number": _first_str(case.get("registrationNumber"), case.get("caseNumber")),
        "status": _first_str(case.get("caseStatus")),
        "court": _first_str(case.get("courtName")),
        "state": _first_str(case.get("state")),
        "parties": _parties_label(case),
        "filing_date": _first_str(case.get("filingDate")),
        "next_hearing_date": _first_str(case.get("nextHearingDate")),
        "last_hearing_date": _first_str(case.get("lastHearingDate")),
        "hearing_count": len(hearings),
        "order_count": order_count,
        "hearing_preview": hearings[-5:],
        "orders_preview": orders[:5],
        "request_id": out.get("request_id", ""),
    }


def search_ecourts(user_id: str, **filters: Any) -> Dict[str, Any]:
    from backend.app.core.ecourtsindia_client import search_cases

    key = _require_api_key(user_id)
    if filters.get("litigants") and not filters.get("litigant"):
        filters["litigant"] = filters.pop("litigants")
    out = search_cases(key, **filters)
    results = []
    for row in out.get("results") or []:
        if not isinstance(row, dict):
            continue
        results.append(
            {
                "cnr": _first_str(row.get("cnr"), row.get("CNR")),
                "case_number": _first_str(row.get("registrationNumber"), row.get("caseNumber")),
                "registration_number": _first_str(row.get("registrationNumber")),
                "parties": _parties_label(row) if isinstance(row, dict) else "",
                "court_name": _first_str(row.get("courtName")),
                "case_status": _first_str(row.get("caseStatus"), row.get("status")),
                "filing_date": _first_str(row.get("filingDate")),
                "next_hearing_date": _first_str(row.get("nextHearingDate")),
            }
        )
    raw = out.get("raw") or {}
    total = int(out.get("total_hits") or raw.get("totalHits") or raw.get("total") or len(results))
    page = int(filters.get("page") or filters.get("Page") or out.get("page") or 1)
    page_size = int(filters.get("pageSize") or filters.get("page_size") or 20)
    return {
        "ok": True,
        "results": results,
        "total_hits": total,
        "returned_count": len(results),
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if page_size else 1,
        "has_next_page": page * page_size < total,
        "request_id": out.get("request_id", ""),
    }


def sync_case_to_matter(
    user_id: str,
    cnr: str,
    matter_id: str,
    *,
    import_hearings: bool = True,
    import_orders: bool = True,
) -> Dict[str, Any]:
    from backend.app.core.ecourtsindia_client import get_case_by_cnr, normalize_cnr

    key = _require_api_key(user_id)
    normalized = normalize_cnr(cnr)
    if not get_matter(user_id, matter_id):
        return {"ok": False, "error": "Matter not found"}

    out = get_case_by_cnr(key, normalized)
    case = _case_blob(out)
    if not case:
        return {"ok": False, "error": "No case data returned for this CNR"}

    matter = get_matter(user_id, matter_id) or {}
    if not (matter.get("case_number") or "").strip():
        reg = _first_str(case.get("registrationNumber"), case.get("caseNumber"))
        if reg:
            update_matter(user_id, matter_id, case_number=reg)

    hearings_imported = 0
    hearings_errors: List[str] = []
    if import_hearings:
        for row in _hearing_rows(case)[-30:]:
            try:
                schedule_hearing(
                    user_id,
                    matter_id,
                    hearing_date=row["hearing_date"],
                    court_name=row.get("court_name", ""),
                    purpose=row.get("purpose", ""),
                    judge_name=row.get("judge", ""),
                    notes=f"Imported from eCourtsIndia CNR {normalized}",
                )
                hearings_imported += 1
            except Exception as exc:
                hearings_errors.append(str(exc))

    orders_imported = 0
    orders_errors: List[str] = []
    if import_orders:
        for row in _order_rows(case, normalized):
            seed = row.get("order_id_seed") or row.get("title", "")
            oid = hashlib.sha256(seed.encode()).hexdigest()[:32]
            try:
                saved = save_court_order(
                    user_id,
                    {
                        "matter_id": matter_id,
                        "title": row.get("title") or "Court order",
                        "order_date": row.get("order_date") or "",
                        "court_name": row.get("court_name") or "",
                        "summary": row.get("summary") or "",
                        "order_type": "order",
                        "tags": f"ecourts,{normalized}",
                    },
                    order_id=oid,
                )
                if saved.get("saved"):
                    orders_imported += 1
                elif saved.get("error"):
                    orders_errors.append(str(saved["error"]))
            except Exception as exc:
                orders_errors.append(str(exc))

    return {
        "ok": True,
        "cnr": normalized,
        "matter_id": matter_id,
        "hearings_imported": hearings_imported,
        "orders_imported": orders_imported,
        "hearings_errors": hearings_errors[:5],
        "orders_errors": orders_errors[:5],
        "request_id": out.get("request_id", ""),
    }
