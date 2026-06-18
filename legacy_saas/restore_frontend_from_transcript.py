"""Restore frontend + api_server from agent transcript (last Write + StrReplace order)."""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
transcript = Path(
    r"C:\Users\ASUS\.cursor\projects\c-Users-ASUS-Desktop-Legal-ai-1-Legal-ai-Legal-AI-Final-3"
    r"\agent-transcripts\44707f15-645f-43dc-92f1-e0b7fe86337d"
    r"\44707f15-645f-43dc-92f1-e0b7fe86337d.jsonl"
)

writes: dict[str, str] = {}
patches: list[tuple[str, str, str]] = []

with open(transcript, encoding="utf-8") as f:
    for line in f:
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        for part in o.get("message", {}).get("content", []):
            if part.get("type") != "tool_use":
                continue
            name = part.get("name")
            inp = part.get("input")
            if not isinstance(inp, dict):
                continue
            p = inp.get("path", "")
            if "Legal_AI_Final 3" not in p:
                continue
            rel = p.split("Legal_AI_Final 3")[-1].lstrip("\\").replace("\\", os.sep)
            if not (
                rel.startswith("frontend")
                or rel == "api_server.py"
                or rel == "run_saas.ps1"
            ):
                continue
            if name == "Write":
                writes[rel] = inp.get("contents", "")
            elif name == "StrReplace":
                patches.append(
                    (rel, inp.get("old_string", ""), inp.get("new_string", ""))
                )

for rel, content in writes.items():
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    print("W", rel)

skipped = 0
for rel, old, new in patches:
    dest = root / rel
    if not dest.exists() or not old:
        skipped += 1
        continue
    text = dest.read_text(encoding="utf-8")
    if old not in text:
        skipped += 1
        print("SKIP", rel)
        continue
    dest.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("P", rel)

print(f"done: {len(writes)} writes, {len(patches)} patches, {skipped} skipped")
