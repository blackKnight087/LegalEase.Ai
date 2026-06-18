"""Rate limiting for SaaS API protection — Redis-backed when available."""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Callable, DefaultDict, List, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("legalease.rate_limit")

_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1").lower() in ("1", "true", "yes")
_MAX_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "180"))
_CHAT_MAX = int(os.getenv("RATE_LIMIT_CHAT_PER_MINUTE", "80"))
_MESSAGE_SEND_MAX = int(os.getenv("RATE_LIMIT_COLLAB_MESSAGE_PER_MINUTE", "100"))
_PROMOTION_MAX = int(os.getenv("RATE_LIMIT_SCOPE_PROMOTION_PER_MINUTE", "12"))
_REDIS_PREFIX = os.getenv("RATE_LIMIT_REDIS_PREFIX", "legalease:rl:")
_LOG_429 = os.getenv("RATE_LIMIT_LOG_429", "1").lower() in ("1", "true", "yes")

# Firm Chat + voice — unlimited (real-time polling/WebSocket exceeds global caps).
_MESSAGING_PATH_MARKERS = (
    "/api/v1/collaboration",
    "/api/v1/speech",
)

# Auth / account abuse protection (always limited when rate limiting is on).
_AUTH_SENSITIVE_MARKERS = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/account/forgot-password",
    "/api/v1/account/reset-password",
    "/api/v1/orgs/invite",
)

_AUTH_SENSITIVE_LIMIT = int(os.getenv("RATE_LIMIT_AUTH_PER_MINUTE", "20"))

_READ_MAX = int(os.getenv("RATE_LIMIT_READ_PER_MINUTE", "400"))

# Saved chats, health polls, engine status — high-frequency authenticated reads.
_READ_PATH_MARKERS = (
    "/api/v1/sessions/",
    "/api/v1/health/stability",
    "/api/v1/engines/",
    "/api/v1/learning/progress",
    "/api/v1/documents/kb/health",
)

_memory_buckets: DefaultDict[str, List[float]] = defaultdict(list)
_redis_client = None
_redis_unavailable = False
_last_429_log: DefaultDict[str, float] = defaultdict(float)


def rate_limit_audit_report() -> dict:
    """Active limiter rules for diagnostics / docs."""
    return {
        "enabled": _ENABLED,
        "global_per_minute": _MAX_PER_MINUTE,
        "read_per_minute": _READ_MAX,
        "ai_chat_per_minute": _CHAT_MAX,
        "auth_sensitive_per_minute": _AUTH_SENSITIVE_LIMIT,
        "collab_message_cap_per_minute": _MESSAGE_SEND_MAX,
        "scope_promotion_per_minute": _PROMOTION_MAX,
        "chat_exempt": _chat_unlimited(),
        "collab_exempt": _collab_unlimited(),
        "messaging_exempt_paths": list(_MESSAGING_PATH_MARKERS),
        "auth_sensitive_paths": list(_AUTH_SENSITIVE_MARKERS),
        "redis_prefix": _REDIS_PREFIX,
    }


def _get_redis():
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        _redis_unavailable = True
        return None
    try:
        import redis

        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_unavailable = True
        return None


def _client_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if len(token) >= 16:
            import hashlib

            return f"user:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
        return f"user:{token[:16]}"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    if request.client:
        return f"ip:{request.client.host}"
    return "ip:unknown"


def _allow_memory(key: str, limit: int) -> Tuple[bool, int]:
    now = time.time()
    window_start = now - 60.0
    hits = [t for t in _memory_buckets[key] if t >= window_start]
    count = len(hits)
    if count >= limit:
        _memory_buckets[key] = hits
        return False, count
    hits.append(now)
    _memory_buckets[key] = hits
    return True, count + 1


def _allow_redis(key: str, limit: int) -> Optional[Tuple[bool, int]]:
    r = _get_redis()
    if not r:
        return None
    try:
        bucket = f"{_REDIS_PREFIX}{key}"
        now = time.time()
        pipe = r.pipeline()
        pipe.zremrangebyscore(bucket, 0, now - 60.0)
        pipe.zcard(bucket)
        pipe.zadd(bucket, {str(now): now})
        pipe.expire(bucket, 120)
        results = pipe.execute()
        count = int(results[1]) if results[1] is not None else 0
        return count < limit, count + 1
    except Exception:
        return None


def _allow(key: str, limit: int) -> Tuple[bool, int]:
    redis_result = _allow_redis(key, limit)
    if redis_result is not None:
        return redis_result
    return _allow_memory(key, limit)


def _is_ai_chat_api_path(path: str) -> bool:
    return path.startswith("/api/v1/chat") or "/api/v1/chat/" in path


def _chat_unlimited() -> bool:
    return os.getenv("RATE_LIMIT_CHAT_EXEMPT", "1").lower() in ("1", "true", "yes")


def _collab_unlimited() -> bool:
    return os.getenv("RATE_LIMIT_COLLAB_EXEMPT", "1").lower() in ("1", "true", "yes")


def _is_firm_chat_path(path: str) -> bool:
    p = path.split("?")[0].rstrip("/")
    for marker in _MESSAGING_PATH_MARKERS:
        if p.startswith(marker) or marker in p:
            return True
    return False


def _is_auth_sensitive(path: str) -> bool:
    p = path.split("?")[0]
    return any(p.startswith(m) or m in p for m in _AUTH_SENSITIVE_MARKERS)


def _is_read_heavy(path: str, method: str) -> bool:
    if method.upper() != "GET":
        return False
    p = path.split("?")[0]
    return any(marker in p for marker in _READ_PATH_MARKERS)


def _is_collab_message_post(path: str, method: str) -> bool:
    if method.upper() != "POST":
        return False
    p = path.split("?")[0]
    return "/collaboration/rooms/" in p and p.endswith("/messages")


def _skip_rate_limit(path: str, method: str = "GET") -> bool:
    if method.upper() == "OPTIONS":
        return True
    if (
        path.endswith("/health/live")
        or path.endswith("/health/llm")
        or path.endswith("/health/public")
        or path.endswith("/health/embeddings")
        or path.endswith("/health/stability")
    ):
        return True
    if "/documents/jobs/" in path:
        return True
    if "/documents/kb/" in path or path.endswith("/kb/health"):
        return True
    if _is_firm_chat_path(path):
        return True
    if _collab_unlimited() and _is_firm_chat_path(path):
        return True
    if _chat_unlimited() and _is_ai_chat_api_path(path):
        return True
    if "/learning/tuning/neural/train" in path:
        return False
    return False


def _limit_for_path(path: str, method: str = "GET") -> Tuple[int, str]:
    if _is_auth_sensitive(path):
        return _AUTH_SENSITIVE_LIMIT, "auth_sensitive"
    if _is_read_heavy(path, method):
        return _READ_MAX, "read"
    if "/learning/tuning/scope/promote" in path:
        return _PROMOTION_MAX, "scope_promotion"
    if _is_ai_chat_api_path(path):
        return _CHAT_MAX, "ai_chat"
    if _is_collab_message_post(path, method) and not _collab_unlimited():
        return _MESSAGE_SEND_MAX, "collab_message_post"
    return _MAX_PER_MINUTE, "global"


def _log_rate_limit_hit(
    *,
    path: str,
    method: str,
    client_key: str,
    limit: int,
    rule: str,
    count: int,
) -> None:
    if not _LOG_429:
        return
    dedupe_key = f"{client_key}:{path}:{rule}"
    now = time.time()
    if now - _last_429_log[dedupe_key] < 5.0:
        return
    _last_429_log[dedupe_key] = now
    logger.warning(
        "rate_limit_429 path=%s method=%s client=%s count=%s limit=%s rule=%s",
        path,
        method,
        client_key[:24],
        count,
        limit,
        rule,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method

        if not _ENABLED or _skip_rate_limit(path, method):
            return await call_next(request)

        key = _client_key(request)
        limit, rule = _limit_for_path(path, method)
        allowed, count = _allow(f"{rule}:{key}", limit)
        if not allowed:
            _log_rate_limit_hit(
                path=path,
                method=method,
                client_key=key,
                limit=limit,
                rule=rule,
                count=count,
            )
            return Response(
                content='{"detail":"Rate limit exceeded. Try again in a minute."}',
                status_code=429,
                media_type="application/json",
                headers={"X-RateLimit-Rule": rule, "X-RateLimit-Limit": str(limit)},
            )
        return await call_next(request)
