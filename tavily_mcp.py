"""Tavily remote MCP client for strict legal web intelligence."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TAVILY_API_KEY = (os.getenv("TAVILY_API_KEY") or "").strip().strip("\"'")
TAVILY_MCP_BASE = os.getenv("TAVILY_MCP_URL", "https://mcp.tavily.com/mcp").rstrip("/")
TAVILY_MCP_URL = os.getenv(
    "TAVILY_MCP_FULL_URL",
    f"{TAVILY_MCP_BASE}/?{urlencode({'tavilyApiKey': TAVILY_API_KEY})}" if TAVILY_API_KEY else TAVILY_MCP_BASE,
)
TAVILY_SEARCH_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "advanced")
TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "8"))

LEGAL_ONLY_WEB = os.getenv("LEGAL_ONLY_WEB", "1").lower() in {"1", "true", "yes"}
LEGAL_QUERY_HINTS = (
    "law", "legal", "act", "section", "article", "ipc", "bns", "crpc", "court",
    "judgment", "statute", "contract", "tort", "petition", "fir", "bail", "appeal",
    "precedent", "india", "supreme", "high court", "tribunal", "arbitration",
    "cji", "chief justice", "justice", "judiciary", "judge",
    "compliance", "litigation", "plaintiff", "defendant", "verdict", "ruling",
    "ordinance", "regulation", "constitution", "penal", "civil", "criminal",
)

LEGAL_SOURCE_HINTS = LEGAL_QUERY_HINTS + (
    "indiankanoon", "scconline", "manupatra", "livelaw", "barandbench",
    "legislative", "gov.in", "lawcommission", "ncdrc", "nclt", "nclat",
)

# Tavily MCP: open web search (no include_domains). Set TAVILY_RESTRICT_DOMAINS=1 to re-enable.
TAVILY_RESTRICT_DOMAINS = os.getenv("TAVILY_RESTRICT_DOMAINS", "0").lower() in {"1", "true", "yes"}
LEGAL_INCLUDE_DOMAINS = (
    [
        d.strip()
        for d in os.getenv("TAVILY_LEGAL_DOMAINS", "").split(",")
        if d.strip()
    ]
    if TAVILY_RESTRICT_DOMAINS
    else []
)

_initialized = False


def _looks_legal_query(query: str) -> bool:
    q = (query or "").lower()
    return any(term in q for term in LEGAL_QUERY_HINTS)


def _legal_search_query(query: str) -> str:
    """Bias Tavily toward Indian legal sources."""
    q = (query or "").strip()
    if not q:
        return q
    if "india" in q.lower() or "indian" in q.lower():
        return f"{q} Indian law statute judgment"
    return f"{q} India law legal statute court judgment"


def _parse_sse_json(text: str) -> Optional[Dict[str, Any]]:
    for line in (text or "").splitlines():
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    continue
    return None


def _mcp_request(method: str, params: Optional[Dict[str, Any]] = None, req_id: int = 1) -> Dict[str, Any]:
    if not TAVILY_API_KEY:
        return {}
    try:
        import requests
    except ImportError:
        return {}

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "DEFAULT_PARAMETERS": json.dumps({
            "search_depth": TAVILY_SEARCH_DEPTH,
            "max_results": TAVILY_MAX_RESULTS,
            "include_images": False,
            "include_raw_content": False,
        }),
    }
    body = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    try:
        mcp_timeout = float(os.getenv("TAVILY_MCP_TIMEOUT", "8"))
        response = requests.post(TAVILY_MCP_URL, json=body, headers=headers, timeout=mcp_timeout)
        if response.status_code != 200:
            logger.warning("Tavily MCP HTTP %s for %s", response.status_code, method)
            return {}
        data = _parse_sse_json(response.text)
        return (data or {}).get("result") or {}
    except Exception as exc:
        logger.warning("Tavily MCP request failed (%s): %s", method, exc)
        return {}


def _ensure_mcp_session() -> None:
    global _initialized
    if _initialized or not TAVILY_API_KEY:
        return
    _mcp_request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "LegalEase.AI", "version": "1.0"},
        },
        req_id=0,
    )
    _initialized = True


def _filter_legal_results(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not LEGAL_ONLY_WEB or not rows:
        return rows
    filtered = []
    for row in rows:
        blob = " ".join(str(row.get(k, "") or "") for k in ("title", "body", "href")).lower()
        if any(h in blob for h in LEGAL_SOURCE_HINTS):
            filtered.append(row)
    return filtered if filtered else rows[: max(1, len(rows) // 2)]


def search_legal_mcp(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Strict legal search via Tavily remote MCP (tavily_search tool).
    Returns [] if blocked, misconfigured, or on error.
    """
    if LEGAL_ONLY_WEB and not _looks_legal_query(query):
        return [{
            "title": "Legal-only web intelligence",
            "href": "",
            "body": (
                "Open Law Intelligence accepts legal questions only. "
                "Include legal context: statute, section, case name, court, contract, FIR, etc."
            ),
            "date": datetime.now(timezone.utc).date().isoformat(),
            "provider": "LegalEase",
        }]

    if not TAVILY_API_KEY:
        return []

    _ensure_mcp_session()
    legal_query = _legal_search_query(query)
    arguments: Dict[str, Any] = {
        "query": legal_query,
        "max_results": max(1, min(max_results, TAVILY_MAX_RESULTS)),
        "search_depth": TAVILY_SEARCH_DEPTH,
    }
    if LEGAL_INCLUDE_DOMAINS:
        arguments["include_domains"] = LEGAL_INCLUDE_DOMAINS[:12]

    result = _mcp_request(
        "tools/call",
        {"name": "tavily_search", "arguments": arguments},
        req_id=2,
    )
    rows: List[Dict[str, Any]] = []
    content = result.get("content") or []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        raw = block.get("text") or ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in payload.get("results", [])[:max_results]:
            rows.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("content", "") or item.get("snippet", ""),
                "date": datetime.now(timezone.utc).date().isoformat(),
                "provider": "Tavily MCP",
            })

    return _filter_legal_results(rows)


def mcp_status() -> Dict[str, Any]:
    return {
        "mcp_url": TAVILY_MCP_BASE,
        "api_key_configured": bool(TAVILY_API_KEY),
        "legal_only": LEGAL_ONLY_WEB,
        "legal_domains": LEGAL_INCLUDE_DOMAINS,
        "domain_restricted": bool(LEGAL_INCLUDE_DOMAINS),
        "search_depth": TAVILY_SEARCH_DEPTH,
    }
