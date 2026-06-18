# Emergency backend reset — kills stuck port 8000 and starts a responsive API.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== LegalEase backend fix ===" -ForegroundColor Cyan

& (Join-Path $PSScriptRoot "stop_backend.ps1")
Start-Sleep -Seconds 2

$still = netstat -ano | findstr "LISTENING" | findstr ":8000 "
if ($still) {
    Write-Host "Port 8000 still busy. End python.exe in Task Manager, then re-run .\fix_backend.ps1" -ForegroundColor Red
    exit 1
}

$env:LEGALEEASE_SKIP_RAG_WARMUP = "1"
$env:LEGALEEASE_MINIMAL_STARTUP = "1"
$env:REINDEX_AUTO_ON_STALE = "0"
$env:REINDEX_AUTO_STARTUP = "0"
$env:COACH_AUTO_SCHEDULE = "0"
$env:IMPROVEMENT_AUTO = "0"

Write-Host "Starting API (minimal startup — login stays fast)..." -ForegroundColor Green
Write-Host "Keep this window OPEN. Test: http://127.0.0.1:8000/docs" -ForegroundColor Gray
Write-Host ""

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }

& $py.Source -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --limit-concurrency 60
