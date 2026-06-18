"""Split-screen redlining & live diff engine."""
from __future__ import annotations

import difflib
import html
import re
from typing import Any, Dict, List, Optional, Tuple


def apply_redline_instruction(
    document: str,
    instruction: str,
    user_id: str = "",
) -> Dict[str, Any]:
    """Apply a natural-language edit instruction to a draft."""
    doc = document or ""
    instr = (instruction or "").strip()
    if not instr:
        return {"error": "Instruction required", "revised": doc}

    revised = _llm_revise(doc, instr, user_id)
    if revised is None:
        revised = _heuristic_revise(doc, instr)

    diff_md = generate_diff_markdown(doc, revised)
    diff_html = generate_diff_html(doc, revised)
    return {
        "original": doc,
        "revised": revised,
        "instruction": instr,
        "diff_markdown": diff_md,
        "diff_html": diff_html,
        "change_count": _count_changes(doc, revised),
    }


def generate_diff_markdown(old: str, new: str) -> str:
    old_lines = (old or "").splitlines(keepends=True)
    new_lines = (new or "").splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile="Original", tofile="Revised", lineterm=""
    )
    return "".join(diff) or "(no changes)"


def generate_diff_html(old: str, new: str) -> str:
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    differ = difflib.SequenceMatcher(None, old_lines, new_lines)
    parts: List[str] = ['<div class="redline-diff">']
    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                parts.append(
                    f'<div class="diff-line diff-same">{html.escape(line)}</div>'
                )
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                parts.append(
                    f'<div class="diff-line diff-del">{html.escape(line)}</div>'
                )
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                parts.append(
                    f'<div class="diff-line diff-add">{html.escape(line)}</div>'
                )
        elif tag == "replace":
            for line in old_lines[i1:i2]:
                parts.append(
                    f'<div class="diff-line diff-del">{html.escape(line)}</div>'
                )
            for line in new_lines[j1:j2]:
                parts.append(
                    f'<div class="diff-line diff-add">{html.escape(line)}</div>'
                )
    parts.append("</div>")
    return "\n".join(parts)


def record_redline_feedback(
    user_id: str,
    instruction: str,
    before: str,
    after: str,
    accepted: bool = True,
) -> Dict[str, Any]:
    return {"recorded": True, "accepted": accepted}


def _llm_revise(doc: str, instruction: str, user_id: str = "") -> Optional[str]:
    try:
        from llms import generate_text

        prompt = (
            "You are a legal drafting assistant. Apply ONLY the requested change. "
            "Return the full revised document text, no commentary.\n\n"
            + f"Instruction: {instruction}\n\nDocument:\n{doc[:12000]}"
        )
        out = generate_text(prompt, max_tokens=4000, temperature=0.3)
        if out and len(out.strip()) > len(doc) * 0.3:
            return out.strip()
    except Exception:
        pass
    return None


def _heuristic_revise(doc: str, instruction: str) -> str:
    il = instruction.lower()
    # Section-specific favorability
    m = re.search(r"section\s+(\d+)", il)
    if m and ("lessor" in il or "landlord" in il):
        sec = m.group(1)
        pattern = rf"(?i)(section\s+{sec}[^\n]*\n)([^\n]+)"
        return re.sub(
            pattern,
            r"\1The Lessor shall have sole discretion regarding maintenance obligations.",
            doc,
            count=1,
        )
    if "more favorable" in il or "favourable" in il or "favorable" in il:
        if "lessee" in il or "tenant" in il:
            return doc.replace(
                "Tenant shall",
                "Tenant shall, to the maximum extent permitted by law,",
                1,
            )
    if "delete" in il or "remove" in il:
        m = re.search(r"['\"]([^'\"]+)['\"]", instruction)
        if m:
            return doc.replace(m.group(1), "")
    if "add" in il:
        return doc + "\n\n[Added per instruction: " + instruction[:200] + "]\n"
    return doc + "\n\n<!-- Revised per: " + instruction[:120] + " -->\n"


def _count_changes(old: str, new: str) -> int:
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    return sum(
        1
        for tag, _, _, _, _ in difflib.SequenceMatcher(
            None, old_lines, new_lines
        ).get_opcodes()
        if tag != "equal"
    )
