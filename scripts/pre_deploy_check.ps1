# Hybrid pre-deploy gate — run from project root
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "=== LegalEase pre-deploy (hybrid) ===" -ForegroundColor Cyan

py scripts/verify_production_ready.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

py scripts/audit_env.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`nPostgres connectivity..." -ForegroundColor Gray
py -c @"
import os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.') / '.env')
url = os.getenv('DATABASE_URL','')
if not url.startswith('postgresql'):
    print('SKIP: no DATABASE_URL'); sys.exit(0)
try:
    import psycopg2
    conn = psycopg2.connect(url)
    conn.close()
    print('OK: Postgres connected')
except Exception as e:
    print('FAIL:', e)
    sys.exit(1)
"@

Write-Host "`nCI gate tests..." -ForegroundColor Gray
py -m pytest tests/test_kb_trust_ci.py tests/test_enterprise_api_ci.py tests/test_tenant_attack_ci.py -q --tb=short -m ci_gate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`nSecurity health (API must be running)..." -ForegroundColor Gray
try {
    Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/security | ConvertTo-Json -Depth 4
} catch {
    Write-Host "WARN: start run_backend.ps1 first for health/security" -ForegroundColor Yellow
}

Write-Host "`nAll automated pre-deploy checks passed." -ForegroundColor Green
