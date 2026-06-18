"""Request hardening — method filter, HTTPS enforcement in production."""
from __future__ import annotations

import os
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_PRODUCTION = os.getenv("SAAS_PRODUCTION", "0").lower() in ("1", "true", "yes")
_FORCE_HTTPS = os.getenv("FORCE_HTTPS", "1").lower() in ("1", "true", "yes")
_BLOCKED_METHODS = frozenset({"TRACE", "TRACK", "CONNECT"})


class RequestGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in _BLOCKED_METHODS:
            return JSONResponse(status_code=405, content={"detail": "Method not allowed"})

        if _PRODUCTION and _FORCE_HTTPS:
            proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
            if proto and proto != "https":
                host = request.headers.get("host") or request.url.netloc
                path = request.url.path
                qs = request.url.query
                target = f"https://{host}{path}"
                if qs:
                    target += f"?{qs}"
                from starlette.responses import RedirectResponse

                return RedirectResponse(url=target, status_code=308)

        return await call_next(request)
