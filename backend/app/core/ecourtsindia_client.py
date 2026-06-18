"""eCourtsIndia partner API client."""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

ECOURTSINDIA_API_BASE = os.getenv(
    "ECOURTSINDIA_API_BASE", "https://webapi.ecourtsindia.com"
).rstrip("/")


class ECourtsIndiaError(Exception):
    def __init__(self, message: str, *, status_code: int = 0, code: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def normalize_cnr(cnr: str) -> str:
    return re.sub(r"\s+", "", (cnr or "").strip()).upper()


def mask_api_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 8:
        return "••••" if k else ""
    return f"{k[:7]}…{k[-4:]}"


def _partner_request(
    method: str,
    path: str,
    api_key: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    require_key: bool = True,
) -> Dict[str, Any]:
    key = (api_key or "").strip()
    if require_key and not key:
        raise ECourtsIndiaError("eCourtsIndia API key required")

    path = path if path.startswith("/") else f"/{path}"
    url = f"{ECOURTSINDIA_API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None and v != ''})}"

    import httpx

    headers: Dict[str, str] = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        with httpx.Client(timeout=45.0) as client:
            res = client.request(method.upper(), url, headers=headers, json=json_body)
    except httpx.HTTPError as exc:
        raise ECourtsIndiaError(f"Network error contacting eCourtsIndia: {exc}") from exc

    if res.status_code == 402:
        raise ECourtsIndiaError(
            "eCourtsIndia credits exhausted (402). Use paste mode or buy more credits.",
            status_code=402,
            code="CREDITS_EXHAUSTED",
        )
    if res.status_code == 401:
        raise ECourtsIndiaError("Invalid eCourtsIndia API key (401)", status_code=401, code="INVALID_TOKEN")
    if res.status_code == 404:
        raise ECourtsIndiaError("Case or resource not found (404)", status_code=404, code="NOT_FOUND")
    if res.status_code >= 400:
        detail = res.text[:240]
        raise ECourtsIndiaError(
            f"eCourtsIndia API error ({res.status_code}): {detail}",
            status_code=res.status_code,
        )

    if not res.content:
        return {}
    payload = res.json()
    return payload if isinstance(payload, dict) else {"data": payload}


def search_cause_list(
    api_key: str,
    *,
    date: str = "",
    state: str = "",
    q: str = "",
    advocate: str = "",
    litigant: str = "",
    district_code: str = "",
    court_complex_code: str = "",
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """GET /api/partner/causelist/search — billed per successful request."""
    params: Dict[str, Any] = {
        "limit": max(1, min(int(limit or 50), 100)),
        "offset": max(0, int(offset or 0)),
    }
    if date:
        params["date"] = date
    if state:
        params["state"] = state.strip().upper()
    if q:
        params["q"] = q.strip()
    if advocate:
        params["advocate"] = advocate.strip()
    if litigant:
        params["litigant"] = litigant.strip()
    if district_code:
        params["districtCode"] = district_code.strip()
    if court_complex_code:
        params["courtComplexCode"] = court_complex_code.strip()

    if not any(params.get(k) for k in ("date", "state", "q", "advocate", "litigant", "districtCode")):
        raise ECourtsIndiaError(
            "Provide at least one filter: date, state, case query, advocate, or litigant"
        )

    payload = _partner_request("GET", "/api/partner/causelist/search", api_key, params=params)
    data = payload.get("data") if isinstance(payload, dict) else {}
    results = (data or {}).get("results") or []
    if not isinstance(results, list):
        results = []
    return {
        "results": results,
        "returned_count": int((data or {}).get("returnedCount") or len(results)),
        "limit": params["limit"],
        "offset": params["offset"],
        "query_params": params,
        "request_id": (payload.get("meta") or {}).get("request_id", ""),
    }


def get_case_by_cnr(api_key: str, cnr: str) -> Dict[str, Any]:
    """GET /api/partner/case/{cnr}"""
    normalized = normalize_cnr(cnr)
    if len(normalized) < 10:
        raise ECourtsIndiaError("Invalid CNR — provide the full Case Number Record")
    payload = _partner_request("GET", f"/api/partner/case/{normalized}", api_key)
    return {
        "cnr": normalized,
        "data": payload.get("data") or payload,
        "request_id": (payload.get("meta") or {}).get("request_id", ""),
    }


def search_cases(api_key: str, **filters: Any) -> Dict[str, Any]:
    """GET /api/partner/search"""
    param_map = {
        "page": "Page",
        "page_size": "PageSize",
        "pageSize": "PageSize",
        "q": "Query",
        "query": "Query",
        "advocates": "advocates",
        "advocate": "advocates",
        "litigant": "litigant",
        "court_codes": "courtCodes",
        "courtCodes": "courtCodes",
        "filing_date_from": "filingDateFrom",
        "filingDateFrom": "filingDateFrom",
        "filing_date_to": "filingDateTo",
        "filingDateTo": "filingDateTo",
        "case_statuses": "caseStatuses",
        "caseStatuses": "caseStatuses",
        "case_types": "caseTypes",
        "caseTypes": "caseTypes",
    }
    params: Dict[str, Any] = {}
    for key, val in filters.items():
        if val is None or val == "":
            continue
        api_key_name = param_map.get(key, key)
        params[api_key_name] = val
    if "PageSize" in params:
        params["PageSize"] = max(1, min(int(params["PageSize"]), 100))
    payload = _partner_request("GET", "/api/partner/search", api_key, params=params)
    data = payload.get("data") if isinstance(payload, dict) else {}
    results = (data or {}).get("results") or (data or {}).get("items") or []
    if not isinstance(results, list):
        results = []
    return {
        "results": results,
        "returned_count": len(results),
        "page": int(params.get("Page", 1) or 1),
        "request_id": (payload.get("meta") or {}).get("request_id", ""),
        "raw": data,
    }


def refresh_case(api_key: str, cnr: str) -> Dict[str, Any]:
    """POST /api/partner/case/{cnr}/refresh"""
    normalized = normalize_cnr(cnr)
    payload = _partner_request("POST", f"/api/partner/case/{normalized}/refresh", api_key)
    return {
        "cnr": normalized,
        "data": payload.get("data") or payload,
        "request_id": (payload.get("meta") or {}).get("request_id", ""),
    }


def get_enums(api_key: str, types: str = "") -> Dict[str, Any]:
    """GET /api/partner/enums — free tier."""
    params = {"types": types} if types else None
    payload = _partner_request(
        "GET", "/api/partner/enums", api_key, params=params, require_key=bool((api_key or "").strip())
    )
    return {"enums": payload.get("data") or payload}


def list_court_states(api_key: str) -> Dict[str, Any]:
    """GET /api/partner/causelist/court-structure/states"""
    payload = _partner_request("GET", "/api/partner/causelist/court-structure/states", api_key)
    data = payload.get("data") or payload
    states = data if isinstance(data, list) else (data.get("states") or data.get("results") or [])
    return {"states": states if isinstance(states, list) else []}


def list_court_districts(api_key: str, state: str) -> Dict[str, Any]:
    """GET /api/partner/causelist/court-structure/states/{state}/districts"""
    st = (state or "").strip().upper()
    payload = _partner_request(
        "GET", f"/api/partner/causelist/court-structure/states/{st}/districts", api_key
    )
    data = payload.get("data") or payload
    districts = data if isinstance(data, list) else (data.get("districts") or data.get("results") or [])
    return {"state": st, "districts": districts if isinstance(districts, list) else []}


def get_available_cause_dates(api_key: str, state: str, **filters: Any) -> Dict[str, Any]:
    """GET /api/partner/causelist/available-dates"""
    params: Dict[str, Any] = {"state": (state or "").strip().upper()}
    for key in ("districtCode", "courtComplexCode", "court", "courtNo"):
        val = filters.get(key) or filters.get(key.lower()) or filters.get(
            key.replace("Code", "_code").lower(), ""
        )
        if val:
            params[key] = val
    payload = _partner_request("GET", "/api/partner/causelist/available-dates", api_key, params=params)
    data = payload.get("data") or payload
    dates = data if isinstance(data, list) else (data.get("dates") or data.get("availableDates") or [])
    return {"state": params["state"], "dates": dates if isinstance(dates, list) else [], "raw": data}


def cause_list_results_to_text(results: List[Dict[str, Any]], *, default_date: str = "") -> str:
    """Convert API rows into cause-list-like text for the existing parser."""
    if not results:
        return ""
    lines: List[str] = []
    header_date = default_date or str(results[0].get("date") or "")
    if header_date:
        lines.append(header_date)
    for row in results:
        case_nums = row.get("caseNumber") or []
        case = case_nums[0] if case_nums else ""
        party = str(row.get("party") or "").strip()
        judges = ", ".join(row.get("judge") or [])
        court = str(row.get("courtName") or row.get("courtDescription") or "").strip()
        status = str(row.get("status") or "").strip()
        hdate = str(row.get("date") or header_date or "")
        parts = [p for p in (case, party, f"before {judges}" if judges else "", court, status) if p]
        line = " ".join(parts).strip()
        if hdate and hdate not in line:
            line = f"{hdate} {line}"
        if line:
            lines.append(line)
    return "\n".join(lines)
