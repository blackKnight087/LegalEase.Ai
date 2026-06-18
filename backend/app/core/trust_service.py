"""Trust vs operating ledger — Indian practice compliance separation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import get_matter
from backend.app.core.saas_schema import ensure_saas_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_or_create_trust_account(
    user_id: str,
    matter_id: str,
    *,
    client_name: str = "",
) -> Dict[str, Any]:
    ensure_saas_schema()
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    matter = get_matter(user_id, matter_id) or {}
    conn = connect_data_db()
    row = conn.execute(
        "SELECT account_id, operating_balance, trust_balance FROM trust_accounts WHERE user_id=? AND matter_id=?",
        (str(user_id), matter_id),
    ).fetchone()
    if row:
        conn.close()
        return {
            "account_id": row[0],
            "matter_id": matter_id,
            "client_name": client_name or matter.get("client_name", ""),
            "operating_balance": round(float(row[1]), 2),
            "trust_balance": round(float(row[2]), 2),
            "currency": "INR",
        }
    aid = str(uuid.uuid4())
    now = _utc()
    conn.execute(
        """
        INSERT INTO trust_accounts
        (account_id, user_id, matter_id, client_name, operating_balance, trust_balance, updated_at)
        VALUES (?, ?, ?, ?, 0, 0, ?)
        """,
        (aid, str(user_id), matter_id, client_name or matter.get("client_name", ""), now),
    )
    conn.commit()
    conn.close()
    return get_or_create_trust_account(user_id, matter_id, client_name=client_name)


def post_trust_transaction(
    user_id: str,
    matter_id: str,
    *,
    ledger_type: str,
    txn_type: str,
    amount: float,
    narrative: str,
    reference_id: str = "",
) -> Dict[str, Any]:
    """ledger_type: TRUST | OPERATING; txn_type: DEPOSIT | DISBURSEMENT | TRANSFER_TO_OPERATING"""
    ledger_type = ledger_type.upper()
    txn_type = txn_type.upper()
    if ledger_type not in ("TRUST", "OPERATING"):
        return {"error": "ledger_type must be TRUST or OPERATING"}
    acct = get_or_create_trust_account(user_id, matter_id)
    if acct.get("error"):
        return acct
    amt = abs(float(amount))
    if amt <= 0:
        return {"error": "amount must be positive"}
    conn = connect_data_db()
    row = conn.execute(
        "SELECT operating_balance, trust_balance FROM trust_accounts WHERE account_id=?",
        (acct["account_id"],),
    ).fetchone()
    op, tr = float(row[0]), float(row[1])
    if txn_type == "DEPOSIT":
        if ledger_type == "TRUST":
            tr += amt
        else:
            op += amt
    elif txn_type == "DISBURSEMENT":
        if ledger_type == "TRUST":
            if tr < amt:
                conn.close()
                return {"error": "Insufficient trust balance"}
            tr -= amt
        else:
            if op < amt:
                conn.close()
                return {"error": "Insufficient operating balance"}
            op -= amt
    elif txn_type == "TRANSFER_TO_OPERATING":
        if tr < amt:
            conn.close()
            return {"error": "Insufficient trust balance for transfer"}
        tr -= amt
        op += amt
        ledger_type = "TRUST"
    else:
        conn.close()
        return {"error": "Invalid txn_type"}
    now = _utc()
    tid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO trust_transactions
        (txn_id, account_id, ledger_type, txn_type, amount, narrative, reference_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tid, acct["account_id"], ledger_type, txn_type, amt, narrative[:500], reference_id, now),
    )
    conn.execute(
        "UPDATE trust_accounts SET operating_balance=?, trust_balance=?, updated_at=? WHERE account_id=?",
        (op, tr, now, acct["account_id"]),
    )
    conn.commit()
    conn.close()
    return {
        "txn_id": tid,
        "operating_balance": round(op, 2),
        "trust_balance": round(tr, 2),
        "ledger_type": ledger_type,
        "txn_type": txn_type,
        "amount": amt,
    }


def list_trust_transactions(user_id: str, matter_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    acct = get_or_create_trust_account(user_id, matter_id)
    if acct.get("error"):
        return []
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT txn_id, ledger_type, txn_type, amount, narrative, reference_id, created_at
        FROM trust_transactions WHERE account_id=?
        ORDER BY created_at DESC LIMIT ?
        """,
        (acct["account_id"], limit),
    ).fetchall()
    conn.close()
    return [
        {
            "txn_id": r[0],
            "ledger_type": r[1],
            "txn_type": r[2],
            "amount": r[3],
            "narrative": r[4],
            "reference_id": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]
