"""
Memory efficiency middleware — tune heavy work under pressure, never return 503 to block users.
"""
from __future__ import annotations

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class MemoryEfficiencyMiddleware(BaseHTTPMiddleware):
    """
    Adds response headers hinting at memory mode; all requests proceed normally.
    Indexing jobs adapt batch size via memory_efficiency.py (not blocked here).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        try:
            from backend.app.core.memory_efficiency import adaptive_index_embed_batch, pressure_level

            response.headers["X-Memory-Pressure"] = pressure_level()
            response.headers["X-Embed-Batch-Hint"] = str(adaptive_index_embed_batch())
        except Exception:
            pass
        return response
