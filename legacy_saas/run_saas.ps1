# OPTIONAL: React + FastAPI (experimental). For daily use run .\run_app.ps1 (Streamlit) instead.
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

# Clear stuck API/Vite from previous runs (fixes crash / port-in-use)
& (Join-Path $Root "stop_saas.ps1")

$NodeDir = "C:\Program Files\nodejs"
if (Test-Path $NodeDir) {
    $env:Path = "$NodeDir;" + $env:Path
}

$py = Join-Path $Root ".venv_win\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "venv not found - using py launcher" -ForegroundColor Yellow
    $py = "py"
}

Write-Host "NOTE: Streamlit is recommended. Use .\run_app.ps1 instead (no port 8000/5173 issues)." -ForegroundColor Yellow
Write-Host "=== LegalEase SaaS (React + API) ===" -ForegroundColor Cyan

$depsOk = $false
try {
    if (Test-Path (Join-Path $Root ".venv_win\Scripts\python.exe")) {
        & $py -c "import fastapi, uvicorn" 2>$null
        if ($LASTEXITCODE -eq 0) { $depsOk = $true }
    }
} catch { }

if (-not $depsOk) {
    Write-Host "Installing Python API dependencies (one-time)..." -ForegroundColor Gray
    & $py -m pip install fastapi "uvicorn[standard]" python-multipart -q --disable-pip-version-check
} else {
    Write-Host "Python API dependencies OK" -ForegroundColor Gray
}

# Use 8001 when 8000 is stuck by a zombie process from older runs
$ApiPort = 8001
Write-Host "Starting API: http://127.0.0.1:$ApiPort" -ForegroundColor Green
$apiArgs = @("-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", "$ApiPort")
Start-Process -FilePath $py -ArgumentList $apiArgs -WorkingDirectory $Root -WindowStyle Normal

$frontend = Join-Path $Root "frontend"
$npmExe = Join-Path $NodeDir "npm.cmd"
if (-not (Test-Path $npmExe)) {
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    $npmExe = if ($npmCmd) { $npmCmd.Source } else { $null }
}

if (-not $npmExe) {
    Write-Host ""
    Write-Host "Node.js not found. Install LTS, then re-run:" -ForegroundColor Red
    Write-Host "  winget install OpenJS.NodeJS.LTS" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "npm install (first time)..." -ForegroundColor Cyan
    Push-Location $frontend
    & $npmExe install
    Pop-Location
}

Write-Host "Starting React UI: http://localhost:5173" -ForegroundColor Green

$reactLines = @("Set-Location -LiteralPath '$frontend'", "npm run dev")
if (Test-Path $NodeDir) {
    $reactLines = @("`$env:Path = '$NodeDir;' + `$env:Path") + $reactLines
}
$reactCommand = $reactLines -join "; "
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $reactCommand) -WindowStyle Normal

Start-Sleep -Seconds 5

# Verify API is responding
$apiOk = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/api/health" -UseBasicParsing -TimeoutSec 8
    if ($r.StatusCode -eq 200) { $apiOk = $true }
} catch { }

Write-Host ""
if ($apiOk) {
    Write-Host "API is ready." -ForegroundColor Green
} else {
    Write-Host "API still starting - wait 10s then refresh the login page." -ForegroundColor Yellow
}
Write-Host "Open: http://localhost:5173/login" -ForegroundColor Yellow
Write-Host "To stop everything later: .\stop_saas.ps1" -ForegroundColor Gray
