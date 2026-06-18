"""Request-scoped user context for per-tenant LLM/embedding routing."""
from __future__ import annotations

from contextvars import ContextVar

_current_user_id: ContextVar[str] = ContextVar("legalease_user_id", default="")


def set_user_context(user_id: str) -> None:
    _current_user_id.set(str(user_id or ""))


def get_user_context() -> str:
    return _current_user_id.get()


def clear_user_context() -> None:
    _current_user_id.set("")
