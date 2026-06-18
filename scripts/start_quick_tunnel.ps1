#!/usr/bin/env pwsh
# Free public link - NO domain purchase, NO Cloudflare zone login.
# URL changes each time you restart cloudflared (use for demos today).
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Quick tunnel (free, no domain needed)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cf) {
    Write-Host "Install cloudflared:" -ForegroundColor Red
    Write-Host "  winget install Cloudflare.cloudflared" -ForegroundColor White
    exit 1
}

& (Join-Path $root "scripts\verify_local_demo.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Start ollama, run_backend.ps1, run_web.ps1 first." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Starting tunnel to http://127.0.0.1:3000 ..." -ForegroundColor Green
Write-Host ""
Write-Host "COPY the https://....trycloudflare.com URL from output below." -ForegroundColor Yellow
Write-Host "Then in a NEW terminal run:" -ForegroundColor Yellow
Write-Host '  .\scripts\configure_tunnel_env.ps1 -TunnelUrl "https://YOUR-URL.trycloudflare.com"' -ForegroundColor White
Write-Host "  .\run_backend.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Keep THIS terminal open. URL dies when you close it." -ForegroundColor DarkGray
Write-Host ""

& cloudflared tunnel --url http://127.0.0.1:3000
