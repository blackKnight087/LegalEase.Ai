"""Onboarding progress — upload, index, matter, plan."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.core.database import connect_data_db
from backend.app.core.p2_saas_schema import ensure_p2_saas_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_count(user_id: str) -> int:
    from backend.app.core.sql_compat import table_exists

    conn = connect_data_db()
    try:
        if not table_exists(conn, "documents"):
            return 0
        r = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE uploader_id = ?",
            (str(user_id),),
        ).fetchone()
        return int(r[0] if r else 0)
    except Exception:
        return 0
    finally:
        conn.close()


def _matter_count(user_id: str) -> int:
    conn = connect_data_db()
    try:
        r = conn.execute(
            "SELECT COUNT(*) FROM matters WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        return int(r[0] if r else 0)
    except Exception:
        return 0
    finally:
        conn.close()


def _kb_ready(user_id: str) -> bool:
    try:
        from backend.app.core.document_db import get_knowledge_base_status

        st = get_knowledge_base_status(str(user_id)) or {}
        return bool(st.get("ready") or st.get("indexed") or int(st.get("chunks") or 0) > 0)
    except Exception:
        return _doc_count(user_id) > 0


def get_onboarding_state(user_id: str, membership: str = "Free") -> Dict[str, Any]:
    ensure_p2_saas_schema()
    uid = str(user_id)
    steps: List[Dict[str, Any]] = [
        {
            "id": "account",
            "title": "Create account",
            "done": True,
            "href": "/settings",
        },
        {
            "id": "upload",
            "title": "Upload your first document",
            "done": _doc_count(uid) > 0,
            "href": "/documents",
        },
        {
            "id": "index",
            "title": "Build knowledge base index",
            "done": _kb_ready(uid),
            "href": "/documents",
        },
        {
            "id": "matter",
            "title": "Create a matter workspace",
            "done": _matter_count(uid) > 0,
            "href": "/matters/new",
        },
        {
            "id": "plan",
            "title": "Choose a plan (optional)",
            "done": (membership or "Free") != "Free",
            "href": "/settings",
        },
        {
            "id": "chat",
            "title": "Ask your first question",
            "done": False,
            "href": "/",
        },
    ]
    conn = connect_data_db()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM chat_history WHERE user_id = ?",
            (uid,),
        ).fetchone()
        steps[-1]["done"] = int(n[0] if n else 0) > 0
    except Exception:
        pass
    finally:
        conn.close()

    done_count = sum(1 for s in steps if s["done"])
    dismissed = _is_dismissed(uid)
    return {
        "steps": steps,
        "completed": done_count,
        "total": len(steps),
        "percent": int(100 * done_count / max(len(steps), 1)),
        "dismissed": dismissed,
        "complete": done_count >= len(steps),
    }


def _is_dismissed(user_id: str) -> bool:
    conn = connect_data_db()
    try:
        row = conn.execute(
            "SELECT dismissed FROM user_onboarding WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        return bool(row and row[0])
    except Exception:
        return False
    finally:
        conn.close()


def dismiss_onboarding(user_id: str) -> None:
    from backend.app.core.sql_compat import upsert_user_onboarding

    ensure_p2_saas_schema()
    now = _utc()
    conn = connect_data_db()
    upsert_user_onboarding(conn, str(user_id), 1, now)
    conn.commit()
    conn.close()
