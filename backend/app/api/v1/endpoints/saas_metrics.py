"""SaaS product KPI endpoints."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from ....core.auth import get_current_user
from ....core.saas_metrics import get_product_kpis

router = APIRouter(tags=["saas-metrics"])


@router.get("/kpi")
def product_kpi(user: Dict[str, Any] = Depends(get_current_user)):
    """North-star KPIs for analytics dashboard."""
    _ = user
    return get_product_kpis()
