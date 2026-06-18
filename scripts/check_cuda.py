"""Verify CUDA is available for LegalEase GPU features."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from backend.app.core.gpu_runtime import apply_gpu_profile, get_gpu_diagnostics


def main() -> int:
    apply_gpu_profile()
    d = get_gpu_diagnostics()
    print("cuda_available:", d.get("cuda_available"))
    print("gpu_name:", d.get("gpu_name") or "(none)")
    print("vram_total_mb:", d.get("vram_total_mb"))
    print("gpu_profile:", d.get("gpu_profile"))
    if not d.get("cuda_available"):
        print("\nInstall CUDA PyTorch — see docs/GPU_SETUP.md")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
