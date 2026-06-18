"""Matter-type defaults for AI reasoning and document classification."""
from __future__ import annotations

from typing import Any, Dict, List

MATTER_TYPES: List[str] = [
    "Criminal",
    "Civil",
    "Family",
    "Divorce",
    "Property",
    "Corporate",
    "Contract",
    "Constitutional",
    "Employment",
    "Medical",
    "Cyber Crime",
    "Tax",
    "Immigration",
    "Consumer Dispute",
    "Arbitration",
    "Personal Documents",
    "General Research",
]

STATUS_TIERS: List[str] = [
    "Open",
    "In Hearing",
    "Pending",
    "Appeal",
    "Closed",
    "Archived",
    "ACTIVE",
]

PRIORITIES: List[str] = ["Low", "Medium", "High", "Critical"]

MATTER_AI_MODES: List[str] = [
    "matter_only",
    "hybrid",
    "research",
    "chronology",
    "hearing_prep",
    "evidence",
]

_TYPE_HINTS: Dict[str, Dict[str, Any]] = {
    "Criminal": {"default_chat_mode": "deep_case", "timeline_types": ["fir", "chargesheet", "hearing"]},
    "Civil": {"default_chat_mode": "knowledge_base", "timeline_types": ["filing", "hearing", "order"]},
    "Family": {"default_chat_mode": "knowledge_base", "timeline_types": ["petition", "hearing"]},
    "Divorce": {"default_chat_mode": "knowledge_base", "timeline_types": ["petition", "mediation", "hearing"]},
    "Property": {"default_chat_mode": "knowledge_base", "timeline_types": ["agreement", "notice", "suit"]},
    "Corporate": {"default_chat_mode": "hybrid", "timeline_types": ["contract", "board", "filing"]},
    "General Research": {"default_chat_mode": "knowledge_base", "timeline_types": ["general"]},
}


def hints_for_matter_type(matter_type: str) -> Dict[str, Any]:
    return dict(_TYPE_HINTS.get(matter_type or "General Research", _TYPE_HINTS["General Research"]))
