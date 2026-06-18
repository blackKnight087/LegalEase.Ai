#!/usr/bin/env pwsh
# Zero-budget public demo launcher — checks health, guides cloudflared setup.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " LegalEase - Zero-budget public demo" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1) Ollama
$ollamaOk = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 4
    $ollamaOk = $r.StatusCode -eq 200
} catch { }
if ($ollamaOk) {
    Write-Host "[OK] Ollama on :11434" -ForegroundColor Green
} else {
    Write-Host "[!!] Ollama not reachable. Run in another terminal:" -ForegroundColor Yellow
    Write-Host "     ollama serve" -ForegroundColor White
}

# 2) Backend
$apiOk = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health/live" -UseBasicParsing -TimeoutSec 4
    $apiOk = $r.StatusCode -eq 200
} catch { }
if ($apiOk) {
    Write-Host "[OK] Backend on :8000" -ForegroundColor Green
} else {
    Write-Host "[!!] Backend not running. Open a new terminal and run:" -ForegroundColor Yellow
    Write-Host "     .\run_backend.ps1" -ForegroundColor White
}

# 3) Web
$webOk = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:3000" -UseBasicParsing -TimeoutSec 4
    $webOk = $r.StatusCode -eq 200
} catch { }
if ($webOk) {
    Write-Host "[OK] Frontend on :3000" -ForegroundColor Green
} else {
    Write-Host "[!!] Frontend not running. Open a new terminal and run:" -ForegroundColor Yellow
    Write-Host "     .\run_web.ps1" -ForegroundColor White
}

if (-not ($apiOk -and $webOk -and $ollamaOk)) {
    Write-Host ""
    Write-Host "Start missing services, then re-run this script." -ForegroundColor Yellow
    Write-Host "Full checklist: docs\DEPLOY_ZERO_BUDGET.md"
    exit 1
}

# LLM health
try {
    $llm = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health/llm" -TimeoutSec 8
    $ready = $llm.llm_ready -or $llm.online -or $llm.available
    if ($ready) {
        Write-Host "[OK] LLM health endpoint reports online" -ForegroundColor Green
    } else {
        Write-Host "[WARN] LLM endpoint up but model may be offline - check ollama list" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] Could not read /api/v1/health/llm" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "--- Public access ---" -ForegroundColor Cyan
Write-Host ""
Write-Host "TEMP (URL changes each restart):" -ForegroundColor Yellow
Write-Host "  cloudflared tunnel --url http://127.0.0.1:3000" -ForegroundColor White
Write-Host ""
Write-Host "STABLE (recommended, free, no domain purchase):" -ForegroundColor Green
Write-Host "  .\scripts\setup_stable_cloudflare_tunnel.ps1" -ForegroundColor White
Write-Host "  See docs\STABLE_PUBLIC_LINK.md" -ForegroundColor DarkGray
Write-Host ""
Write-Host "After ANY tunnel URL, run:" -ForegroundColor Cyan
Write-Host '  .\scripts\configure_tunnel_env.ps1 -TunnelUrl "https://YOUR-URL"' -ForegroundColor White
Write-Host "  .\run_backend.ps1" -ForegroundColor White
Write-Host '  .\scripts\verify_public_demo.ps1 -PublicUrl "https://YOUR-URL"' -ForegroundColor White
Write-Host ""
Write-Host "Share the stable link. PC must stay on. Max 1-2 users on laptop GPU." -ForegroundColor DarkGray
Write-Host ""
