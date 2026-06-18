"""RAG over past chat threads — searchable conversation memory."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PAST_QUERY_RE = re.compile(
    r"\b(what did we|last time|previous(?:ly)?|earlier|three weeks|last month|"
    r"conclude|concluded|said before|past (?:chat|session|conversation))\b",
    re.I,
)


def conversation_index_dir(user_id: str, matter_id: Optional[str] = None) -> Path:
    from app import get_user_index_dir
    from backend.app.core.matter_index import get_matter_index_dir, safe_id

    mid = (matter_id or "").strip()
    if mid:
        d = get_matter_index_dir(user_id, mid) / "conversations"
    else:
        d = get_user_index_dir(user_id) / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def should_search_past_chats(query: str) -> bool:
    return bool(_PAST_QUERY_RE.search(query or ""))


def index_chat_turn(
    user_id: str,
    thread_id: str,
    question: str,
    answer: str,
    chat_id: str = "",
    matter_id: Optional[str] = None,
) -> int:
    """Vectorize one Q&A pair into the user's conversation FAISS index."""
    if not (question or "").strip() or not (answer or "").strip():
        return 0
    ans = (answer or "").strip()
    if len(ans) < 40:
        return 0
    if _is_low_quality_answer(ans):
        return 0

    content = (
        f"[Thread {thread_id[:8]}]\n"
        f"Question: {question.strip()[:600]}\n"
        f"Answer: {ans[:1200]}"
    )
    doc = {
        "content": content,
        "metadata": {
            "source": "chat_history",
            "thread_id": thread_id,
            "chat_id": chat_id,
            "doc_id": chat_id or thread_id,
            "filename": f"chat_{thread_id[:8]}.txt",
            "chunk_index": 0,
        },
    }
    try:
        from rag import append_documents_to_index

        ok, _, n = append_documents_to_index(
            [doc], index_dir=conversation_index_dir(user_id, matter_id)
        )
        return n if ok else 0
    except Exception as exc:
        logger.warning("Chat index append failed: %s", exc)
        return 0


def index_thread_from_db(
    user_id: str, thread_id: str, matter_id: Optional[str] = None
) -> int:
    """Backfill index for one thread or all threads when thread_id empty."""
    from backend.app.core.chat_persistence import list_chat_threads, load_chat_thread

    total = 0
    if thread_id:
        tids = [thread_id]
    else:
        tids = [row[0] for row in list_chat_threads(user_id, limit=200, matter_id=matter_id)]
    for tid in tids:
        rows = load_chat_thread(user_id, tid)
        for row in rows:
            chat_id, q, a = row[0], row[1], row[2]
            total += index_chat_turn(
                user_id, tid, q, a, chat_id=chat_id, matter_id=matter_id
            )
    return total


def search_past_chats(user_id: str, query: str, k: int = 4) -> List[Dict[str, Any]]:
    """Retrieve relevant prior conversation snippets."""
    if not query.strip():
        return []
    try:
        from rag import index_exists, query_kb

        idx = conversation_index_dir(user_id, matter_id)
        if not index_exists(idx):
            index_thread_from_db(user_id, "", matter_id=matter_id)  # no-op if empty
            if not index_exists(idx):
                return []
        hits = query_kb(query, k=k, index_dir=idx)
        return hits[:k]
    except Exception as exc:
        logger.warning("Past chat search failed: %s", exc)
        return []


def format_past_chat_context(hits: List[Dict[str, Any]]) -> str:
    if not hits:
        return ""
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[Prior session {i}]\n{(h.get('content') or '')[:500]}")
    return "\n\n".join(parts)


def _is_low_quality_answer(text: str) -> bool:
    tl = text.lower()
    bad = (
        "couldn't find",
        "could not find",
        "not found in",
        "i could not generate",
        "error:",
    )
    return any(b in tl for b in bad) and len(text) < 200
