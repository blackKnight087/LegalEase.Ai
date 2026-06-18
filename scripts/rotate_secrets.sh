#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "LegalEase secret rotation..."
python3 "$(dirname "$0")/rotate_secrets.py"
chmod 600 "$ROOT/scripts/.env.rotation.generated" 2>/dev/null || true
echo ""
echo "Next: merge scripts/.env.rotation.generated into server .env, rotate provider keys, restart stack."
