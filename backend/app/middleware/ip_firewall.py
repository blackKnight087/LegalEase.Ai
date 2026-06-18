"""Optional IP allowlist — application-layer firewall (set FIREWALL_ALLOWED_IPS)."""
from __future__ import annotations

import os
from typing import Callable, FrozenSet

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_ENABLED = os.getenv("FIREWALL_ENABLED", "0").lower() in ("1", "true", "yes")
_PRODUCTION = os.getenv("SAAS_PRODUCTION", "0").lower() in ("1", "true", "yes")


def _allowed_ips() -> FrozenSet[str]:
    raw = os.getenv("FIREWALL_ALLOWED_IPS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _client_ip(request: Request) -> str:
    # When behind nginx, only trust X-Forwarded-For if explicitly enabled
    trust_proxy = os.getenv("FIREWALL_TRUST_PROXY", "1").lower() in ("1", "true", "yes")
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def _skip_path(path: str) -> bool:
    return (
        path.endswith("/health/live")
        or path.endswith("/health/public")
        or path.endswith("/health/security")
        or path == "/health"
    )


class IPFirewallMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _ENABLED:
            return await call_next(request)

        if _skip_path(request.url.path):
            return await call_next(request)

        allowed = _allowed_ips()
        # Fail closed in production when firewall is on but allowlist is empty
        if _PRODUCTION and not allowed:
            return JSONResponse(
                status_code=503,
                content={"detail": "Firewall enabled but FIREWALL_ALLOWED_IPS is not configured"},
            )

        if not allowed:
            return await call_next(request)

        ip = _client_ip(request)
        if ip in allowed or ip in ("127.0.0.1", "::1"):
            return await call_next(request)

        return JSONResponse(
            status_code=403,
            content={"detail": "Access denied by firewall policy"},
        )
