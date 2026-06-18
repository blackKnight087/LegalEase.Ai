"""Core legacy tables (auth, chat, memory, learning).

Revision ID: 001_core_legacy
Revises:
Create Date: 2026-05-28

"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "001_core_legacy"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from backend.app.core.pg_core_schema import ensure_pg_core_schema

    ensure_pg_core_schema()


def downgrade() -> None:
    pass
