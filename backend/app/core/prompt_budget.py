"""
Rigid prompt token/character budget — memory never starves document RAG.

Approximate: 1 token ≈ 4 chars for English legal text.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

CHARS_PER_TOKEN = 4

MAX_MEMORY_TOKENS = int(os.getenv("MAX_MEMORY_TOKENS", "512"))
MAX_SUMMARY_TOKENS = int(os.getenv("MAX_SUMMARY_TOKENS", "512"))
MAX_RAG_DOCUMENT_TOKENS = int(os.getenv("MAX_RAG_DOCUMENT_TOKENS", "2048"))
MAX_PAST_CHAT_TOKENS = int(os.getenv("MAX_PAST_CHAT_TOKENS", "384"))


def token_to_chars(tokens: int) -> int:
    return max(0, tokens) * CHARS_PER_TOKEN


MAX_MEMORY_CHARS = token_to_chars(MAX_MEMORY_TOKENS)
MAX_SUMMARY_CHARS = token_to_chars(MAX_SUMMARY_TOKENS)
MAX_RAG_DOCUMENT_CHARS = token_to_chars(MAX_RAG_DOCUMENT_TOKENS)
MAX_PAST_CHAT_CHARS = token_to_chars(MAX_PAST_CHAT_TOKENS)


def truncate_text(text: str, max_chars: int, suffix: str = "…") -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - len(suffix)].rstrip() + suffix


def budget_memory_block(block: str) -> str:
    return truncate_text(block, MAX_MEMORY_CHARS)


def budget_summary(summary: str) -> str:
    return truncate_text(summary, MAX_SUMMARY_CHARS)


def budget_past_chat(block: str) -> str:
    return truncate_text(block, MAX_PAST_CHAT_CHARS)


def budget_rag_chunks(chunks: List[Dict[str, Any]], max_chars: int = None) -> List[Dict[str, Any]]:
    """Trim chunk list so total context stays within RAG budget."""
    cap = max_chars or MAX_RAG_DOCUMENT_CHARS
    out: List[Dict[str, Any]] = []
    used = 0
    for ch in chunks:
        content = (ch.get("content") or "").strip()
        if not content:
            continue
        room = cap - used
        if room <= 80:
            break
        piece = content if len(content) <= room else truncate_text(content, room)
        used += len(piece)
        copy = dict(ch)
        copy["content"] = piece
        out.append(copy)
    return out


def compile_context_sections(
    *,
    memory_block: str = "",
    summary_block: str = "",
    past_chat_block: str = "",
    rag_chunks: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply all caps and return trimmed sections + diagnostics."""
    mem = budget_memory_block(memory_block)
    summ = budget_summary(summary_block)
    past = budget_past_chat(past_chat_block)
    rag = budget_rag_chunks(rag_chunks or [])
    return {
        "memory_block": mem,
        "summary_block": summ,
        "past_chat_block": past,
        "rag_chunks": rag,
        "budget": {
            "memory_chars": len(mem),
            "summary_chars": len(summ),
            "past_chat_chars": len(past),
            "rag_chars": sum(len(c.get("content", "")) for c in rag),
            "limits": {
                "memory": MAX_MEMORY_CHARS,
                "summary": MAX_SUMMARY_CHARS,
                "rag": MAX_RAG_DOCUMENT_CHARS,
                "past_chat": MAX_PAST_CHAT_CHARS,
            },
        },
    }
