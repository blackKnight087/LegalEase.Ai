"""HTTP security headers for SaaS deployment (TLS assumed at reverse proxy)."""
from __future__ import annotations

import os
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_ENABLED = os.getenv("SECURITY_HEADERS_ENABLED", "1").lower() in ("1", "true", "yes")
_HSTS_MAX_AGE = int(os.getenv("HSTS_MAX_AGE", "31536000"))
_PRODUCTION = os.getenv("SAAS_PRODUCTION", "0").lower() in ("1", "true", "yes")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        if not _ENABLED:
            return response

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(self), geolocation=(), payment=()"
        )
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"

        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
        if _PRODUCTION and proto == "https":
            response.headers["Strict-Transport-Security"] = (
                f"max-age={_HSTS_MAX_AGE}; includeSubDomains"
            )

        csp = os.getenv("CONTENT_SECURITY_POLICY", "").strip()
        if csp:
            response.headers["Content-Security-Policy"] = csp

        return response
