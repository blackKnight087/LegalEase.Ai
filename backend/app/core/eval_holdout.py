"""
Holdout eval set — lightweight regression check before Modelfile export.

Uses retrieval scores + optional keyword checks (no Gemini, no legal answer generation).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
HOLDOUT_PATH = ROOT / "Data" / "eval_holdout.json"
REGRESSION_MAX_DROP = float(os.getenv("EVAL_REGRESSION_MAX_DROP", "0.12"))

DEFAULT_HOLDOUT: List[Dict[str, Any]] = [
    {
        "id": "criminal_section",
        "query": "What is the punishment for murder under IPC?",
        "expect_keywords": ["punishment", "murder", "section"],
        "min_score": 0.18,
    },
    {
        "id": "contract_breach",
        "query": "What are the remedies for breach of contract?",
        "expect_keywords": ["breach", "contract", "remedy"],
        "min_score": 0.15,
    },
    {
        "id": "bail_general",
        "query": "Explain anticipatory bail requirements.",
        "expect_keywords": ["bail"],
        "min_score": 0.12,
    },
    {
        "id": "evidence_act",
        "query": "What is hearsay evidence?",
        "expect_keywords": ["evidence", "hearsay"],
        "min_score": 0.12,
    },
    {
        "id": "limitation",
        "query": "What is the limitation period for filing a civil suit?",
        "expect_keywords": ["limitation", "period"],
        "min_score": 0.12,
    },
]


def ensure_holdout_file() -> None:
    HOLDOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not HOLDOUT_PATH.exists():
        HOLDOUT_PATH.write_text(
            json.dumps({"queries": DEFAULT_HOLDOUT}, indent=2),
            encoding="utf-8",
        )


def load_holdout_queries() -> List[Dict[str, Any]]:
    ensure_holdout_file()
    try:
        data = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
        queries = data.get("queries") or DEFAULT_HOLDOUT
        return queries if isinstance(queries, list) else DEFAULT_HOLDOUT
    except Exception:
        return DEFAULT_HOLDOUT


def _score_query(user_id: str, query: str, min_score: float) -> Dict[str, Any]:
    """Retrieve from user KB index; score by top chunk relevance."""
    try:
        from app import index_exists, resolve_rag_index_dir

        index_dir = resolve_rag_index_dir(str(user_id), None)
        if not index_exists(index_dir):
            return {
                "query": query,
                "score": 0.0,
                "passed": False,
                "reason": "no_index",
                "chunks": 0,
            }
        from rag import query_kb

        chunks = query_kb(query, k=5, index_dir=index_dir)
        if not chunks:
            return {
                "query": query,
                "score": 0.0,
                "passed": False,
                "reason": "no_chunks",
                "chunks": 0,
            }
        top = float(chunks[0].get("score") or chunks[0].get("relevance") or 0)
        body = " ".join((c.get("content") or "")[:400] for c in chunks[:3]).lower()
        return {
            "query": query,
            "score": round(top, 4),
            "passed": top >= min_score,
            "reason": "ok" if top >= min_score else "low_score",
            "chunks": len(chunks),
            "preview": body[:120],
        }
    except Exception as exc:
        return {
            "query": query,
            "score": 0.0,
            "passed": False,
            "reason": str(exc)[:80],
            "chunks": 0,
        }


def run_holdout_eval(user_id: str) -> Dict[str, Any]:
    """Run holdout queries; pass if majority meet min_score."""
    queries = load_holdout_queries()
    if not queries:
        return {"passed": True, "skipped": True, "summary": "No holdout queries configured."}

    results: List[Dict[str, Any]] = []
    for item in queries[:12]:
        q = str(item.get("query") or "")
        min_s = float(item.get("min_score") or 0.12)
        r = _score_query(str(user_id), q, min_s)
        r["id"] = item.get("id") or q[:30]
        keywords = [str(k).lower() for k in (item.get("expect_keywords") or [])]
        if keywords and r.get("preview"):
            kw_hit = sum(1 for k in keywords if k in r["preview"])
            r["keyword_hits"] = kw_hit
            if kw_hit == 0 and r.get("passed"):
                r["passed"] = False
                r["reason"] = "no_keyword_match"
        results.append(r)

    passed_count = sum(1 for r in results if r.get("passed"))
    total = len(results)
    avg_score = sum(float(r.get("score") or 0) for r in results) / max(1, total)
    pass_ratio = passed_count / max(1, total)
    passed = pass_ratio >= 0.6 or (total <= 2 and passed_count == total)

    baseline_path = ROOT / "Data" / "eval_baselines" / f"{user_id}.json"
    regression = False
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            prev_avg = float(baseline.get("avg_score") or 0)
            if prev_avg > 0 and avg_score < prev_avg * (1 - REGRESSION_MAX_DROP):
                passed = False
                regression = True
        except Exception:
            pass

    try:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(
                {"avg_score": avg_score, "pass_ratio": pass_ratio, "results_count": total},
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    summary = (
        f"Holdout: {passed_count}/{total} passed, avg score {avg_score:.3f}"
        + (" (regression detected)" if regression else "")
    )
    return {
        "passed": passed,
        "pass_ratio": round(pass_ratio, 3),
        "avg_score": round(avg_score, 4),
        "passed_count": passed_count,
        "total": total,
        "regression": regression,
        "results": results,
        "summary": summary,
    }
