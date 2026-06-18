#!/usr/bin/env python3
"""Merge thesis expansion chapters into main LegalEase_SAAS_Thesis.md."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "docs" / "LegalEase_SAAS_Thesis.md"
EXPANSION = ROOT / "docs" / "thesis_expansion_chapters.md"
MARKER = "## Conclusion"


def main() -> None:
    if not EXPANSION.exists():
        raise SystemExit(f"Missing {EXPANSION} — run generate_thesis_expansion_md.py first")
    main_text = MAIN.read_text(encoding="utf-8")
    expansion = EXPANSION.read_text(encoding="utf-8").strip()
    if MARKER not in main_text:
        raise SystemExit(f"Marker {MARKER!r} not found in thesis")
    if expansion in main_text:
        print("Expansion already merged.")
        return
    merged = main_text.replace(MARKER, expansion + "\n\n---\n\n" + MARKER, 1)
    MAIN.write_text(merged, encoding="utf-8")
    lines = len(merged.splitlines())
    print(f"Merged expansion into {MAIN} ({lines} lines)")


if __name__ == "__main__":
    main()
