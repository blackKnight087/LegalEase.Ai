#!/usr/bin/env pwsh
# Smoke-test a public tunnel URL (run from your laptop while tunnel is up).
param(
    [Parameter(Mandatory = $true)]
    [string]$PublicUrl
)

$ErrorActionPreference = "Stop"
$base = $PublicUrl.Trim().TrimEnd("/")

Write-Host "Testing public URL: $base" -ForegroundColor Cyan

try {
    $r = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 30
    Write-Host "[OK] Frontend HTTP $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Frontend - $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

try {
    $r = Invoke-WebRequest -Uri "$base/api/v1/health/live" -UseBasicParsing -TimeoutSec 30
    Write-Host "[OK] API health/live HTTP $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "[WARN] API via tunnel failed. Use one tunnel on port 3000 only." -ForegroundColor Yellow
    Write-Host "       $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Manual test: open $base on your phone using mobile data." -ForegroundColor Cyan
Write-Host "Then register, upload a document, and run a KB chat."
