"""Validate matter intelligence modules at startup."""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("legalease.matter_intel")

_MODULES = (
    "backend.app.core.matter_intelligence",
    "backend.app.core.matter_intel_pipeline",
    "backend.app.core.matter_entities",
    "backend.app.core.matter_evidence",
    "backend.app.core.matter_hearings_intel",
)


def _syntax_check_file(path: Path) -> Tuple[bool, str]:
    try:
        src = path.read_text(encoding="utf-8")
        ast.parse(src)
        return True, ""
    except SyntaxError as exc:
        return False, f"{path.name}:{exc.lineno}: {exc.msg}"
    except OSError as exc:
        return False, str(exc)


def validate_matter_intel_modules() -> List[str]:
    """Return list of errors; empty if all OK."""
    errors: List[str] = []
    root = Path(__file__).resolve().parents[3]
    checks = [
        root / "backend" / "app" / "core" / "matter_intelligence.py",
        root / "backend" / "app" / "core" / "matter_intel_pipeline.py",
        root / "backend" / "app" / "core" / "matter_entities.py",
        root / "backend" / "app" / "core" / "matter_evidence.py",
        root / "backend" / "app" / "core" / "matter_hearings_intel.py",
    ]
    for p in checks:
        ok, err = _syntax_check_file(p)
        if not ok:
            errors.append(err)

    for mod in _MODULES:
        try:
            __import__(mod)
        except Exception as exc:
            errors.append(f"import {mod}: {exc}")

    if errors:
        logger.error("Matter intelligence validation failed: %s", errors)
    else:
        logger.info("Matter intelligence modules validated OK")
    return errors


def ensure_matter_intel_ready() -> None:
    errs = validate_matter_intel_modules()
    if errs:
        raise RuntimeError("Matter intelligence module error: " + "; ".join(errs[:3]))
