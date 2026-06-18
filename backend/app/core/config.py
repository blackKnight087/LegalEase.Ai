"""Application configuration."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "Data"
FAISS_BASE_DIR = DATA_DIR / "faiss_indexes"

API_PREFIX = "/api/v1"


def production_mode() -> bool:
    from backend.app.core.production_config import production_mode as _prod

    return _prod()


CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if o.strip()
]
# Allow any local dev port (Next.js, Vite, etc.) — disabled in production unless opted in
CORS_ORIGIN_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
)

_PROD_CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_PROD_CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "X-Request-ID",
    "X-CSRF-Token",
]
_PROD_EXPOSE_HEADERS = ["X-Request-ID"]


def cors_middleware_kwargs() -> Dict[str, Any]:
    """CORSMiddleware settings — strict allowlist in production."""
    strict_prod = production_mode() and os.getenv("CORS_ALLOW_LOCALHOST_REGEX", "0").lower() not in (
        "1",
        "true",
        "yes",
    )
    if strict_prod:
        return {
            "allow_origins": CORS_ORIGINS,
            "allow_origin_regex": None,
            "allow_credentials": True,
            "allow_methods": _PROD_CORS_METHODS,
            "allow_headers": _PROD_CORS_HEADERS,
            "expose_headers": _PROD_EXPOSE_HEADERS,
        }
    regex: Optional[str] = CORS_ORIGIN_REGEX or None
    return {
        "allow_origins": CORS_ORIGINS,
        "allow_origin_regex": regex,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
        "expose_headers": ["*"],
    }
