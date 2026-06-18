"""User memory & persona API — CRUD facts, profile, reindex chats."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.user_memory import (
    add_fact,
    build_memory_context,
    delete_fact,
    ensure_user_memory_schema,
    extract_facts_from_message,
    get_or_create_profile,
    list_facts,
    update_fact,
    update_profile,
)

router = APIRouter(tags=["memory"])


class ProfileUpdate(BaseModel):
    persona: Optional[str] = None
    practice_area: Optional[str] = None
    preferred_language: Optional[str] = None
    communication_notes: Optional[str] = None
    memory_enabled: Optional[bool] = None


class FactCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    value: str = Field(..., min_length=1, max_length=500)


class FactUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    value: str = Field(..., min_length=1, max_length=500)


@router.get("/profile")
def memory_profile(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_user_memory_schema()
    prof = get_or_create_profile(user["id"])
    prof["facts"] = list_facts(user["id"])
    return prof


@router.patch("/profile")
def memory_profile_update(
    body: ProfileUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_user_memory_schema()
    fields = body.model_dump(exclude_none=True)
    return update_profile(user["id"], **fields)


@router.post("/facts")
def memory_add_fact(
    body: FactCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_user_memory_schema()
    return add_fact(user["id"], body.key, body.value, source="user", confidence=1.0)


@router.patch("/facts/{fact_id}")
def memory_update_fact(
    fact_id: str,
    body: FactUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if not update_fact(user["id"], fact_id, body.key, body.value):
        raise HTTPException(404, "Fact not found")
    return {"ok": True}


@router.delete("/facts/{fact_id}")
def memory_delete_fact(
    fact_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if not delete_fact(user["id"], fact_id):
        raise HTTPException(404, "Fact not found")
    return {"ok": True}


@router.post("/facts/reindex-chats")
def memory_reindex_chats(user: Dict[str, Any] = Depends(get_current_user)):
    """Vectorize all past chat threads for RAG search."""
    from backend.app.core.chat_persistence import list_chat_threads
    from backend.app.core.chat_conversation_rag import index_thread_from_db

    threads = list_chat_threads(user["id"], limit=100)
    total = 0
    for row in threads:
        tid = row[0]
        total += index_thread_from_db(user["id"], tid)
    return {"threads_indexed": len(threads), "chunks_added": total}


@router.get("/context")
def memory_context(
    thread_id: str = "",
    mode: str = "knowledge_base",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_user_memory_schema()
    return build_memory_context(user["id"], thread_id or None, mode)
