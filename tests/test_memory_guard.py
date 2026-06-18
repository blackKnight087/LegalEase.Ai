"""Memory efficiency helpers — no request blocking."""
from __future__ import annotations

from backend.app.core.memory_efficiency import adaptive_index_embed_batch, pressure_level


def test_pressure_level_returns_string():
    assert pressure_level() in ("low", "medium", "high", "critical")


def test_adaptive_batch_is_positive():
    assert adaptive_index_embed_batch() >= 4
