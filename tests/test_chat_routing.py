"""Unified chat route resolution tests."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.ci_gate

from backend.app.services.chat_service import resolve_chat_route


def test_kb_aliases():
    assert resolve_chat_route("kb") == "knowledge_base"
    assert resolve_chat_route("matter_only") == "knowledge_base"


def test_open_law_aliases():
    assert resolve_chat_route("open_law") == "open_law"
    assert resolve_chat_route("web_search") == "web_search"


def test_matter_mode_research():
    assert resolve_chat_route("knowledge_base", matter_mode="research") == "web_search"


def test_free_plan_blocks_hybrid():
    assert resolve_chat_route("hybrid", membership="Free") == "knowledge_base"
    assert resolve_chat_route("hybrid", membership="Pro") == "hybrid"


def test_extended_modes():
    assert resolve_chat_route("drafting") == "drafting"
    assert resolve_chat_route("discovery") == "discovery"
    assert resolve_chat_route("crm") == "crm"
