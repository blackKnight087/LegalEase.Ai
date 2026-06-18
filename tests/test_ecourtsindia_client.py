"""Unit tests for eCourtsIndia partner API client."""
from __future__ import annotations

import json

import pytest

from backend.app.core.ecourtsindia_client import (
    ECourtsIndiaError,
    get_case_by_cnr,
    normalize_cnr,
    search_cases,
    search_cause_list,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | str):
        self.status_code = status_code
        self._payload = payload

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    @property
    def text(self) -> str:
        if isinstance(self._payload, str):
            return self._payload
        return json.dumps(self._payload)

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.last_request = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def request(self, method, url, headers=None, json=None):
        self.last_request = {"method": method, "url": url, "headers": headers or {}, "json": json}
        return self._response


def test_normalize_cnr():
    assert normalize_cnr(" dlhc01 000123 2024 ") == "DLHC010001232024"


def test_search_cause_list_requires_key():
    with pytest.raises(ECourtsIndiaError, match="API key required"):
        search_cause_list("", date="2025-03-15", state="DL")


def test_get_case_by_cnr_mock(monkeypatch):
    payload = {
        "data": {
            "courtCaseData": {
                "cnr": "DLHC010001232024",
                "caseStatus": "PENDING",
                "petitioners": ["ABC"],
                "respondents": ["XYZ"],
            }
        },
        "meta": {"request_id": "req-1"},
    }
    fake = _FakeClient(_FakeResponse(200, payload))
    monkeypatch.setattr("httpx.Client", lambda timeout=45.0: fake)

    out = get_case_by_cnr("eci_live_test_key", "dlhc010001232024")
    assert out["cnr"] == "DLHC010001232024"
    assert out["data"]["courtCaseData"]["cnr"] == "DLHC010001232024"
    assert "DLHC010001232024" in fake.last_request["url"]
    assert fake.last_request["headers"]["Authorization"] == "Bearer eci_live_test_key"


def test_search_cases_mock(monkeypatch):
    payload = {
        "data": {
            "results": [{"cnr": "DLHC010001232024", "caseStatus": "PENDING"}],
            "totalHits": 1,
            "page": 1,
            "pageSize": 20,
            "totalPages": 1,
            "hasNextPage": False,
        },
        "meta": {"request_id": "req-2"},
    }
    fake = _FakeClient(_FakeResponse(200, payload))
    monkeypatch.setattr("httpx.Client", lambda timeout=45.0: fake)

    out = search_cases("eci_live_test_key", advocates="Sharma", page=1, pageSize=10)
    assert out["results"][0]["cnr"] == "DLHC010001232024"
    assert "advocates=Sharma" in fake.last_request["url"]


def test_partner_request_402(monkeypatch):
    fake = _FakeClient(_FakeResponse(402, "credits gone"))
    monkeypatch.setattr("httpx.Client", lambda timeout=45.0: fake)

    with pytest.raises(ECourtsIndiaError) as exc:
        get_case_by_cnr("eci_live_test_key", "DLHC010001232024")
    assert exc.value.status_code == 402
    assert exc.value.code == "CREDITS_EXHAUSTED"
