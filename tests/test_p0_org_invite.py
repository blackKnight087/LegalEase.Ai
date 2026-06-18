"""Org invite preview + accept flow."""
from __future__ import annotations

import pytest


def test_org_invite_accept_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "inv.db"))
    from backend.app.core.p0_saas_schema import ensure_p0_saas_schema
    from backend.app.core.org_service import (
        accept_invite,
        create_invite,
        create_org_for_user,
        get_invite_by_token,
        list_org_members,
        user_in_org,
    )
    from legalease_auth import authenticate_user, create_user, ensure_db

    ensure_db()
    ensure_p0_saas_schema()
    assert create_user("owner_inv", "pass12345")
    assert create_user("teammate", "pass12345")
    owner = authenticate_user("owner_inv", "pass12345")
    member = authenticate_user("teammate", "pass12345")
    assert owner and member
    org_id = create_org_for_user(owner["id"], owner["username"])
    from backend.app.core.database import connect_sqlite

    conn = connect_sqlite()
    conn.execute("UPDATE organizations SET seat_limit = 5 WHERE org_id = ?", (org_id,))
    conn.commit()
    conn.close()
    inv = create_invite(org_id, owner["id"], "teammate@firm.com", "member")
    token = inv["token"]
    preview = get_invite_by_token(token)
    assert preview
    assert preview["org_name"]
    assert preview["status"] == "pending"

    with pytest.raises(PermissionError):
        accept_invite(token, owner["id"], owner["username"])

    result = accept_invite(token, member["id"], member["username"])
    assert result["ok"]
    assert user_in_org(member["id"], org_id)
    members = list_org_members(org_id, owner["id"])
    assert len(members) == 2
    preview2 = get_invite_by_token(token)
    assert preview2["status"] == "accepted"
