"""SaaS infrastructure tests."""
from __future__ import annotations

import os
from unittest.mock import patch

from backend.app.core.legacy_db import check_legacy_db_split_brain


def test_split_brain_warning_when_postgres_without_legacy():
    with patch.dict(
        os.environ,
        {"DATABASE_URL": "postgresql://u:p@localhost/db", "SAAS_USE_POSTGRES_LEGACY": "0"},
        clear=False,
    ):
        msg = check_legacy_db_split_brain()
        assert msg is not None
        assert "SAAS_USE_POSTGRES_LEGACY" in msg


def test_no_split_brain_when_legacy_enabled():
    with patch.dict(
        os.environ,
        {"DATABASE_URL": "postgresql://u:p@localhost/db", "SAAS_USE_POSTGRES_LEGACY": "1"},
        clear=False,
    ):
        assert check_legacy_db_split_brain() is None


def test_product_kpis_returns_expected_keys():
    from backend.app.core.saas_metrics import get_product_kpis

    kpi = get_product_kpis()
    for key in ("users_total", "dau", "mau", "ai", "plans"):
        assert key in kpi
