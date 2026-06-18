"""Rest schema — practice, CRM, ops (Day 5).

Revision ID: 002_rest_schema
Revises: 001_core_legacy
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "002_rest_schema"
down_revision: Union[str, None] = "001_core_legacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

    ensure_pg_rest_schema()


def downgrade() -> None:
    pass
