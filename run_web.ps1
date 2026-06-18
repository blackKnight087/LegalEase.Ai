# LegalEase Next.js frontend
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "web")

Write-Host "LegalEase frontend launcher (Next.js / port 3000)" -ForegroundColor Cyan

. (Join-Path $PSScriptRoot "scripts\apply_local_env.ps1")
Set-LegalEaseLocalDevEnv -ProjectRoot $PSScriptRoot

$node = Get-Command node -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $node -or -not $npm) {
    Write-Error "Node.js not found. Install from https://nodejs.org then reopen PowerShell."
}

function Test-PortListening([int]$Port) {
    # Get-NetTCPConnection can hang 30s+ on some Windows setups; netstat is instant.
    $line = netstat -ano | Select-String -Pattern ":\s*$Port\s+.*LISTENING" | Select-Object -First 1
    return [bool]$line
}

Write-Host "Checking port 3000..." -ForegroundColor Gray
if (Test-PortListening 3000) {
    Write-Host "Port 3000 is already in use." -ForegroundColor Yellow
    Write-Host "If the frontend is already running, open: http://localhost:3000"
    Write-Host "To restart, run: .\stop_web.ps1   then   .\run_web.ps1"
    exit 1
}

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies (first time only)..." -ForegroundColor Yellow
    npm install
}

$apiUrl = if ($env:NEXT_PUBLIC_API_URL) { $env:NEXT_PUBLIC_API_URL } else { "http://127.0.0.1:8000" }
$appUrl = if ($env:NEXT_PUBLIC_APP_URL) { $env:NEXT_PUBLIC_APP_URL } else { "http://localhost:3000" }
# Backend base URL only (no /api suffix) - next.config rewrites add /api/v1
$apiUrl = ($apiUrl -replace '/api$', '').TrimEnd('/')
if ($env:LEGALEEASE_USE_REMOTE_API -eq "1") {
    $rootEnv = Join-Path $PSScriptRoot ".env"
    if (Test-Path $rootEnv) {
        Get-Content $rootEnv | ForEach-Object {
            if ($_ -match '^\s*NEXT_PUBLIC_API_URL\s*=\s*(.+)\s*$') { $apiUrl = $Matches[1].Trim() }
            if ($_ -match '^\s*NEXT_PUBLIC_APP_URL\s*=\s*(.+)\s*$') { $appUrl = $Matches[1].Trim() }
        }
    }
    Write-Host "Remote API mode (LEGALEEASE_USE_REMOTE_API=1): $apiUrl" -ForegroundColor DarkGray
} else {
    Write-Host "Local API: $apiUrl" -ForegroundColor DarkGray
}
$localLines = @(
    "NEXT_PUBLIC_API_URL=$apiUrl",
    "NEXT_PUBLIC_APP_URL=$appUrl"
)
Set-Content -Path ".env.local" -Value ($localLines -join "`n") -Encoding utf8

function Test-BackendHealthy() {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health/live" -UseBasicParsing -TimeoutSec 5
        return $r.StatusCode -eq 200
    } catch {
        $listening = netstat -ano | findstr "LISTENING" | findstr ":8000 "
        if ($listening) {
            Write-Host "Port 8000 is in use but API is not responding (stuck)." -ForegroundColor Yellow
            Write-Host "Run: .\stop_backend.ps1   then   .\run_backend.ps1" -ForegroundColor White
        }
        return $false
    }
}

if (-not (Test-BackendHealthy)) {
    Write-Host ""
    Write-Host "WARNING: Backend is NOT running on port 8000." -ForegroundColor Red
    Write-Host "Login will fail until you start it in another terminal:" -ForegroundColor Yellow
    Write-Host "  cd `"$((Join-Path $PSScriptRoot '.'))`"" -ForegroundColor White
    Write-Host "  .\run_backend.ps1" -ForegroundColor White
    Write-Host ""
}

Write-Host "Starting Next.js on http://localhost:3000" -ForegroundColor Green
Write-Host "Keep this window open while using the app." -ForegroundColor Gray
Write-Host "API backend must run separately: .\run_backend.ps1  ->  http://127.0.0.1:8000" -ForegroundColor Gray

# Ollama + FastAPI often use 12GB+ RAM; Next dev compiler needs headroom (fixes ERR_MEMORY_ALLOCATION_FAILED).
if (-not $env:NODE_OPTIONS) {
    $env:NODE_OPTIONS = "--max-old-space-size=4096"
    Write-Host "NODE_OPTIONS=$env:NODE_OPTIONS (dev compiler memory)" -ForegroundColor DarkGray
}

# Prefer production server if dev keeps crashing (set LEGALEEASE_WEB_PROD=1).
if ($env:LEGALEEASE_WEB_PROD -eq "1") {
    Write-Host "Production mode: npm run build && npm run start (lower RAM than dev)" -ForegroundColor Yellow
    npm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm run start
} else {
    npm run dev
}
