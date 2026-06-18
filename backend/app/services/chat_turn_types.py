"""Typed chat turn results — prevents tuple unpack mismatches across sync/stream paths."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class ChatTurnResult:
    """Standard 4-field chat turn payload used by KB, Open Law, and feedback ack paths."""

    content: str
    similar_cases: List[dict] = field(default_factory=list)
    web_sources: List[dict] = field(default_factory=list)
    follow_ups: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_content(self) -> bool:
        return bool((self.content or "").strip())

    def as_tuple(self) -> Tuple[str, List[dict], List[dict], List[str]]:
        return (self.content, self.similar_cases, self.web_sources, self.follow_ups)

    @classmethod
    def from_tuple(cls, value: Tuple[str, List[dict], List[dict], List[str]]) -> "ChatTurnResult":
        if len(value) != 4:
            raise ValueError(f"ChatTurnResult expects 4 values, got {len(value)}")
        content, similar_cases, web_sources, follow_ups = value
        return cls(content, similar_cases, web_sources, follow_ups)
