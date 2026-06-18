"""Cross-document contradiction detection within a matter."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


_CONTRADICTION_CUES = (
    (re.compile(r"\bdenied\b", re.I), re.compile(r"\badmitted\b", re.I)),
    (re.compile(r"\bnever\b", re.I), re.compile(r"\balways\b", re.I)),
    (re.compile(r"\bno injury\b", re.I), re.compile(r"\binjury\b", re.I)),
    (re.compile(r"\bnot present\b", re.I), re.compile(r"\bpresent at\b", re.I)),
)


def find_contradictions(chunks: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, str]]:
    """Heuristic pairwise scan of top KB chunks."""
    findings: List[Dict[str, str]] = []
    tops = chunks[:10]
    for i, a in enumerate(tops):
        for j, b in enumerate(tops):
            if j <= i:
                continue
            ta = (a.get("content") or "")[:1200]
            tb = (b.get("content") or "")[:1200]
            if not ta or not tb:
                continue
            meta_a = (a.get("metadata") or {}).get("filename", f"doc{i+1}")
            meta_b = (b.get("metadata") or {}).get("filename", f"doc{j+1}")
            for pa, pb in _CONTRADICTION_CUES:
                if pa.search(ta) and pb.search(tb):
                    findings.append({
                        "doc_a": meta_a,
                        "doc_b": meta_b,
                        "note": f"Possible tension: '{pa.pattern}' vs '{pb.pattern}'",
                        "excerpt_a": pa.search(ta).group(0) if pa.search(ta) else "",
                        "excerpt_b": pb.search(tb).group(0) if pb.search(tb) else "",
                    })
                    break
            if len(findings) >= limit:
                return findings
    return findings


def format_contradiction_report(findings: List[Dict[str, str]]) -> str:
    if not findings:
        return ""
    lines = ["## Document Contradiction Scan", ""]
    for f in findings:
        lines.append(f"- **{f['doc_a']}** vs **{f['doc_b']}**: {f['note']}")
    return "\n".join(lines)
