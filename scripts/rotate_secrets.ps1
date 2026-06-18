# Generate new locally-managed secrets for production deploy.
# Does NOT overwrite .env — writes scripts/.env.rotation.generated

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "LegalEase secret rotation..."
py "$PSScriptRoot\rotate_secrets.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Merge scripts/.env.rotation.generated into server .env (never commit)."
Write-Host "  2. Align DATABASE_URL with POSTGRES_PASSWORD."
Write-Host "  3. Restart API — users must re-login after JWT rotation."
Write-Host "  4. Rotate Gemini, Stripe, email keys in provider consoles; revoke old keys."
Write-Host "  5. py scripts/verify_production_ready.py"
