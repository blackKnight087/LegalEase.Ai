#!/usr/bin/env python3
"""Run deep LegalEase system diagnostic (RAM, API, embeddings, indexing)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from backend.app.core.system_diagnostics import run_system_diagnostics

    report = run_system_diagnostics()
    print(json.dumps(report, indent=2))
    if not report.get("healthy"):
        print("\nRecommended fixes:")
        for fix in report.get("recommended_fixes") or []:
            print(f"  - {fix}")
        return 2
    print("\nSystem looks healthy for API + LLM.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
