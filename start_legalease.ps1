# Start backend (new window) then frontend — fixes login "API reconnecting" when only run_web was used.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Test-BackendHealthy() {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health/live" -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

Write-Host "LegalEase - starting backend + frontend" -ForegroundColor Cyan

if (-not (Test-BackendHealthy)) {
    Write-Host "Launching backend in a new window..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "run_backend.ps1")
    )
    Write-Host "Waiting for API on http://127.0.0.1:8000 ..."
    $ok = $false
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        if (Test-BackendHealthy) {
            $ok = $true
            break
        }
    }
    if (-not $ok) {
        Write-Host "Backend did not respond in time." -ForegroundColor Red
        Write-Host "In the backend window, wait for 'Uvicorn running' or run .\stop_backend.ps1 then .\run_backend.ps1"
        exit 1
    }
    Write-Host "Backend is healthy." -ForegroundColor Green
} else {
    Write-Host "Backend already running." -ForegroundColor Green
}

Write-Host "Starting frontend (this window)..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "run_web.ps1")
