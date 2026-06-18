"""Structured KB pipeline logging (uvicorn console). Set KB_PIPELINE_DEBUG=0 to disable."""
from __future__ import annotations

import logging
import os
from typing import Any, List

logger = logging.getLogger("legalease.kb")

_ENABLED = os.getenv("KB_PIPELINE_DEBUG", "1").lower() in ("1", "true", "yes", "on")


def kb_log(stage: str, **kwargs: Any) -> None:
    if not _ENABLED:
        return
    lines = [f"[KB:{stage}]"]
    for key, val in kwargs.items():
        if key == "chunks" and isinstance(val, list):
            lines.append(f"  RETRIEVED_CHUNKS count={len(val)}")
            for i, ch in enumerate(val[:5]):
                meta = ch.get("metadata") or {}
                excerpt = (ch.get("content") or "")[:160].replace("\n", " ")
                score = ch.get("final_score", ch.get("score", "?"))
                lines.append(
                    f"    [{i}] score={score} file={meta.get('filename', '?')} "
                    f"excerpt={excerpt!r}"
                )
        elif isinstance(val, str) and len(val) > 400:
            lines.append(f"  {key}={val[:400]!r}…")
        else:
            lines.append(f"  {key}={val!r}")
    msg = "\n".join(lines)
    logger.info(msg)
    print(msg, flush=True)


def log_chunks(stage: str, chunks: List[dict]) -> None:
    kb_log(stage, chunks=chunks)
