# LegalEase.AI — Primary launcher: Streamlit (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$stopScript = Join-Path $Root "stop_app.ps1"
if (Test-Path $stopScript) {
    $listener = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host "Clearing stuck process on port 8501..." -ForegroundColor Gray
        & $stopScript
        Start-Sleep -Seconds 2
    }
}

$Py312 = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$VenvPy = Join-Path $Root ".venv_win\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    if (-not (Test-Path $Py312)) {
        Write-Host "Python 3.12 not found. Install: winget install Python.Python.3.12"
        exit 1
    }
    Write-Host "Creating Windows virtual environment (first time only)..." -ForegroundColor Cyan
    & $Py312 -m venv .venv_win
    & $VenvPy -m pip install --upgrade pip
    & $VenvPy -m pip install -r requirements.txt
}

Write-Host "=== LegalEase.AI (Streamlit) ===" -ForegroundColor Cyan
Write-Host "First launch can take 1-3 minutes while AI libraries load." -ForegroundColor Yellow
Write-Host "Keep the Streamlit window open. Browser will open automatically." -ForegroundColor Gray

$streamlitCmd = @(
    "Set-Location -LiteralPath '$Root'",
    "& '$VenvPy' -m streamlit run app.py --server.port 8501 --browser.serverAddress localhost"
) -join "; "

Start-Process powershell -ArgumentList @("-NoExit", "-Command", $streamlitCmd) -WindowStyle Normal

Write-Host "Waiting for Streamlit to start..." -ForegroundColor Gray
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8501" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}

Start-Process "http://localhost:8501"

if ($ready) {
    Write-Host "Browser opened: http://localhost:8501" -ForegroundColor Green
} else {
    Write-Host "Streamlit is still loading. Open manually: http://localhost:8501" -ForegroundColor Yellow
    Write-Host "If the page is blank, wait 1-3 minutes and press F5." -ForegroundColor Yellow
}

Write-Host "Login / Register in the left sidebar." -ForegroundColor Yellow
