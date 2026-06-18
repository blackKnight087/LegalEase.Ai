"""Trust account ledger API."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.saas_schema import ensure_saas_schema
from ....core.trust_service import (
    get_or_create_trust_account,
    list_trust_transactions,
    post_trust_transaction,
)

router = APIRouter(tags=["trust"])


class TrustTxnCreate(BaseModel):
    matter_id: str
    ledger_type: str = Field(..., description="TRUST or OPERATING")
    txn_type: str = Field(..., description="DEPOSIT, DISBURSEMENT, TRANSFER_TO_OPERATING")
    amount: float = Field(..., gt=0)
    narrative: str = Field(..., min_length=3)
    reference_id: str = ""


@router.get("/account")
def trust_account(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_saas_schema()
    out = get_or_create_trust_account(user["id"], matter_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/transactions")
def trust_transactions(
    matter_id: str,
    limit: int = 50,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return {"transactions": list_trust_transactions(user["id"], matter_id, limit=limit)}


@router.post("/transactions")
def trust_post_transaction(
    body: TrustTxnCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = post_trust_transaction(
        user["id"],
        body.matter_id,
        ledger_type=body.ledger_type,
        txn_type=body.txn_type,
        amount=body.amount,
        narrative=body.narrative,
        reference_id=body.reference_id,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out
