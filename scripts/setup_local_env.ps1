# One-time laptop setup: create .env.local from template (does not touch EC2).
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$example = Join-Path $root ".env.local.example"
$local = Join-Path $root ".env.local"

if (Test-Path $local) {
    Write-Host ".env.local already exists - no changes." -ForegroundColor Green
    exit 0
}
if (-not (Test-Path $example)) {
    Write-Error "Missing .env.local.example"
}
Copy-Item $example $local
Write-Host "Created .env.local from template." -ForegroundColor Green
Write-Host "Edit .env.local for laptop settings. Keep API keys in .env." -ForegroundColor Gray
Write-Host 'Start: .\run_backend.ps1 then .\run_web.ps1' -ForegroundColor Cyan
