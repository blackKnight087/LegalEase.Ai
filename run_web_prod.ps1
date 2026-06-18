# LegalEase Next.js — production build + start (uses less RAM than `next dev` on 16GB PCs)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "web")

Write-Host "LegalEase frontend (production mode / port 3000)" -ForegroundColor Cyan
$env:NODE_OPTIONS = "--max-old-space-size=4096"
$env:LEGALEEASE_WEB_PROD = "1"
& (Join-Path $PSScriptRoot "run_web.ps1")
