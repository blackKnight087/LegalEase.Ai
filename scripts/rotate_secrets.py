"""Write scripts/.env.rotation.generated with new local production secrets."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.secret_rotation import generate_rotation_bundle, rotation_checklist  # noqa: E402

OUT = Path(__file__).resolve().parent / ".env.rotation.generated"


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bundle = generate_rotation_bundle()
    checklist = rotation_checklist()
    lines = [
        "# LegalEase — generated secrets",
        f"# Created: {stamp}",
        "# Copy into production .env; rotate provider keys in dashboards.",
        "",
    ]
    for key, value in bundle.items():
        lines.append(f"{key}={value}")
    lines.extend(["", "# Provider dashboard rotation (manual):"])
    for key in checklist["provider_dashboards"]:
        lines.append(f"#   - {key}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
