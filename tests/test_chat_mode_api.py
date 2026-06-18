"""Chat API mode normalization — Open Law / Hybrid must not fall back to KB."""
from __future__ import annotations

import pytest

from backend.app.core.chat_mode import normalize_api_chat_mode


class TestChatModeNormalization:
    def test_open_law_alias_not_kb(self):
        assert normalize_api_chat_mode("open_law", "Free") == "open_law"

    def test_web_search_preserved(self):
        assert normalize_api_chat_mode("web_search", "Free") == "web_search"

    def test_hybrid_alias_for_pro(self):
        assert normalize_api_chat_mode("hybrid", "Pro") == "hybrid"
        assert normalize_api_chat_mode("deep_case", "Pro") == "deep_case"

    def test_hybrid_blocked_for_free(self):
        assert normalize_api_chat_mode("hybrid", "Free") == "knowledge_base"
        assert normalize_api_chat_mode("deep_case", "Free") == "knowledge_base"

    def test_unknown_mode_defaults_kb(self):
        assert normalize_api_chat_mode("invalid_mode", "Free") == "knowledge_base"
