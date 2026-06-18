"""
Export Ollama Modelfile + JSONL training dataset from coaching feedback.

Enables true weight-level fine-tuning:
  ollama create legalease-tuned -f Modelfile
  # then set OLLAMA_MODEL=legalease-tuned in .env
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[3]
EXPORT_DIR = ROOT / "Data" / "ollama_exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BASE_MODEL = (
    os.getenv("OLLAMA_MODEFILE_BASE") or os.getenv("OLLAMA_MODEL") or "llama3.1:8b"
).strip()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _connect():
    from backend.app.core.database import connect_data_db

    return connect_data_db()


def _escape_modelfile(s: str) -> str:
    return (s or "").replace('"""', "'''").strip()


def _collect_training_examples(user_id: str, limit: int = 500) -> List[Dict[str, str]]:
    """Gather Q→A examples from feedback, neural pairs, and coach memories."""
    from backend.app.core.adaptive_learning import ensure_learning_schema
    from backend.app.core.neural_finetuning import ensure_neural_tuning_schema

    ensure_learning_schema()
    ensure_neural_tuning_schema()
    uid = str(user_id)
    examples: List[Dict[str, str]] = []
    seen: set[str] = set()

    def _add(query: str, answer: str, source: str) -> None:
        q, a = (query or "").strip(), (answer or "").strip()
        if len(q) < 8 or len(a) < 40:
            return
        key = f"{q[:120]}|{a[:80]}"
        if key in seen:
            return
        seen.add(key)
        examples.append({"query": q[:2000], "answer": a[:4000], "source": source})

    conn = _connect()
    try:
        for q, a in conn.execute(
            """
            SELECT i.query, i.answer_preview
            FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE f.signal IN ('thumbs_up', 'helpful', 'copy')
            AND i.user_id = ?
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (uid, limit),
        ).fetchall():
            _add(q, a, "feedback")

        for q, p in conn.execute(
            """
            SELECT query, positive_passage FROM neural_tuning_pairs
            WHERE user_id = ? AND label >= 0.5
            ORDER BY created_at DESC LIMIT ?
            """,
            (uid, limit),
        ).fetchall():
            _add(q, p, "neural_pair")
    finally:
        conn.close()

    try:
        from backend.app.core.gemini_ollama_coach import list_coach_memories

        for mem in list_coach_memories(uid, limit=30):
            content = (mem.get("content") or "").strip()
            if len(content) >= 40 and "Q:" in content:
                parts = content.split("| Issue:", 1)
                if len(parts) == 2:
                    q = parts[0].replace("Q:", "").strip()
                    _add(q, f"[Improved approach] {parts[1].strip()}", "coach_memory")
    except Exception:
        pass

    return examples[:limit]


def build_system_prompt(user_id: str) -> str:
    """System block for Modelfile — persona, facts, directives, coach memory."""
    from backend.app.core.user_memory import PERSONA_PRESETS, get_or_create_profile, list_facts

    prof = get_or_create_profile(user_id)
    persona_key = prof.get("persona", "warm")
    lines = [
        PERSONA_PRESETS.get(persona_key, PERSONA_PRESETS["warm"]),
        "",
        "You are LegalEase — an Indian legal research assistant powered by the user's Knowledge Base.",
        "Answer from uploaded documents of ANY type: contracts, judgments, statutes, policies, FIRs, "
        "affidavits, tax, property, constitutional text, or general legal PDFs.",
        "Use exact IPC/BNS section numbers only when the user asks about those sections.",
        "Cite filenames or page markers when available. Be accurate; say when information is not in documents.",
    ]
    if prof.get("practice_area"):
        lines.append(f"User practice area: {prof['practice_area']}")
    if prof.get("communication_notes"):
        lines.append(f"User preferences: {prof['communication_notes']}")
    try:
        from backend.app.core.gemini_ollama_coach import get_coach_memory_block, get_directives

        directives = get_directives(user_id)
        if directives:
            lines.append(f"User tuning instructions: {directives[:800]}")
        coach_block = get_coach_memory_block(user_id, limit=10)
        if coach_block:
            lines.append(coach_block)
    except Exception:
        pass
    for f in list_facts(user_id, limit=12):
        if f.get("source") in ("user", "coach") or (f.get("confidence") or 0) >= 0.75:
            lines.append(f"Remember: {f['key']} = {f['value']}")
    return "\n".join(lines)[:6000]


def build_modelfile_content(user_id: str, *, base_model: str = "") -> Tuple[str, int]:
    """Return (Modelfile text, example_count)."""
    base = (base_model or DEFAULT_BASE_MODEL).strip()
    system = _escape_modelfile(build_system_prompt(user_id))
    examples = _collect_training_examples(user_id)

    parts = [
        f"FROM {base}",
        "",
        f'SYSTEM """',
        system,
        '"""',
        "",
        "PARAMETER temperature 0.25",
        "PARAMETER top_p 0.9",
        "PARAMETER num_ctx 8192",
        "PARAMETER stop \"<|eot_id|>\"",
        "PARAMETER stop \"\"",
    ]

    for ex in examples[:12]:
        q = _escape_modelfile(ex["query"][:800])
        a = _escape_modelfile(ex["answer"][:1200])
        parts.extend(["", f'MESSAGE user "{q}"', f'MESSAGE assistant "{a}"'])

    return "\n".join(parts), len(examples)


def build_jsonl_content(user_id: str, limit: int = 500) -> Tuple[str, int]:
    """ChatML-style JSONL for external fine-tuning (Axolotl, Unsloth, etc.)."""
    system = build_system_prompt(user_id)
    examples = _collect_training_examples(user_id, limit=limit)
    lines: List[str] = []
    for ex in examples:
        record = {
            "messages": [
                {"role": "system", "content": system[:3000]},
                {"role": "user", "content": ex["query"]},
                {"role": "assistant", "content": ex["answer"]},
            ],
            "metadata": {"source": ex.get("source", ""), "user_id": str(user_id)},
        }
        lines.append(json.dumps(record, ensure_ascii=False))
    return "\n".join(lines), len(lines)


def export_ollama_bundle(
    user_id: str,
    *,
    base_model: str = "",
) -> Dict[str, Any]:
    """
    Write Modelfile, training.jsonl, and README to Data/ollama_exports/{user_id}/.
    """
    uid = str(user_id)
    stamp = _utc_stamp()
    out_dir = EXPORT_DIR / uid / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    modelfile, ex_count = build_modelfile_content(uid, base_model=base_model)
    jsonl, jsonl_count = build_jsonl_content(uid)
    base = (base_model or DEFAULT_BASE_MODEL).strip()
    model_name = re.sub(r"[^a-z0-9_-]", "-", f"legalease-{uid[:8]}".lower())

    modelfile_path = out_dir / "Modelfile"
    jsonl_path = out_dir / "training.jsonl"
    readme_path = out_dir / "README.txt"

    modelfile_path.write_text(modelfile, encoding="utf-8")
    jsonl_path.write_text(jsonl, encoding="utf-8")

    readme = f"""LegalEase Ollama Fine-Tuning Bundle
Generated: {datetime.now(timezone.utc).isoformat()}
User: {uid}
Base model: {base}
Training examples: {ex_count} (Modelfile few-shot) / {jsonl_count} (JSONL)

--- Quick start (Modelfile — instant custom model) ---

1. Open a terminal in this folder:
   cd "{out_dir}"

2. Create the tuned model:
   ollama create {model_name} -f Modelfile

3. Update your .env:
   OLLAMA_MODEL={model_name}
   LLM_BACKEND=ollama

4. Restart the backend.

--- Weight-level fine-tuning (JSONL) ---

Use training.jsonl with Ollama fine-tune or tools like Unsloth/Axolotl:
   ollama run {base}
   # Or: fine-tune locally then import adapter

Files:
  Modelfile     — system prompt + few-shot examples (ollama create)
  training.jsonl — full chat dataset for LoRA/SFT training
"""
    readme_path.write_text(readme, encoding="utf-8")

    latest_link = EXPORT_DIR / uid / "latest"
    try:
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(out_dir.name, target_is_directory=True)
    except OSError:
        (EXPORT_DIR / uid / "latest_path.txt").write_text(str(out_dir), encoding="utf-8")

    return {
        "ok": True,
        "status": "ok",
        "user_id": uid,
        "base_model": base,
        "suggested_model_name": model_name,
        "example_count": ex_count,
        "jsonl_count": jsonl_count,
        "export_dir": str(out_dir),
        "modelfile_path": str(modelfile_path),
        "jsonl_path": str(jsonl_path),
        "readme_path": str(readme_path),
        "create_command": f"ollama create {model_name} -f Modelfile",
    }


def latest_export_info(user_id: str) -> Dict[str, Any]:
    uid = str(user_id)
    user_dir = EXPORT_DIR / uid
    if not user_dir.exists():
        return {"has_export": False}
    latest = user_dir / "latest"
    path_file = user_dir / "latest_path.txt"
    export_path = None
    if latest.is_symlink() or latest.is_dir():
        export_path = latest.resolve() if latest.exists() else None
    elif path_file.exists():
        export_path = Path(path_file.read_text(encoding="utf-8").strip())
    if not export_path or not export_path.exists():
        dirs = sorted(user_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        export_path = dirs[0] if dirs else None
    if not export_path:
        return {"has_export": False}
    mf = export_path / "Modelfile"
    jl = export_path / "training.jsonl"
    return {
        "has_export": True,
        "export_dir": str(export_path),
        "modelfile_path": str(mf) if mf.exists() else "",
        "jsonl_path": str(jl) if jl.exists() else "",
        "modelfile_preview": mf.read_text(encoding="utf-8")[:500] if mf.exists() else "",
    }
