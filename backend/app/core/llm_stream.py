"""SSE token streaming for LM Studio / Ollama compatible APIs."""
from __future__ import annotations

import json
import os
from typing import Generator, List, Optional

import requests

from llms import LM_STUDIO_BASE_URL, LM_STUDIO_MODEL, LM_STUDIO_READ_TIMEOUT, _extract_chat_content


def stream_chat_tokens(
    user_prompt: str,
    *,
    system_prompt: Optional[str] = None,
    temperature: float = 0.12,
    max_tokens: int = 2048,
) -> Generator[str, None, None]:
    """Yield text deltas from LM Studio streaming chat completions."""
    base = (os.getenv("LM_STUDIO_URL") or LM_STUDIO_BASE_URL).rstrip("/")
    endpoint = f"{base}/v1/chat/completions"
    messages: List[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": os.getenv("LM_STUDIO_MODEL") or LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        with requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=LM_STUDIO_READ_TIMEOUT,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                yield f"[Error: LLM returned {resp.status_code}]"
                return
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content") or ""
                if text:
                    yield text
    except requests.exceptions.RequestException as exc:
        yield f"[Error: {exc}]"


def generate_non_stream(
    user_prompt: str,
    *,
    system_prompt: Optional[str] = None,
    temperature: float = 0.12,
    max_tokens: int = 2048,
) -> str:
    from backend.app.core.llm_orchestrator import get_generator_for_task
    from backend.app.core.llm_task_router import TaskType, router_enabled
    from llms import get_generator

    gen = (
        get_generator_for_task(TaskType.LEGAL_REASONING)
        if router_enabled()
        else get_generator()
    )
    return gen.generate(
        user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
    )
