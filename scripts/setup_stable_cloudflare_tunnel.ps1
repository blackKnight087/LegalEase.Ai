#!/usr/bin/env pwsh
# Stable public link - Cloudflare Named Tunnel + free DNS (no paid domain).
# See docs/STABLE_PUBLIC_LINK.md
param(
    [string]$TunnelName = "legalease-demo",
    [string]$Hostname = "",
    [switch]$SkipLogin
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " LegalEase - Stable public link setup" -ForegroundColor Cyan
Write-Host " (Cloudflare named tunnel + free DNS)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cf) {
    Write-Host "[!!] Install cloudflared first:" -ForegroundColor Red
    Write-Host "     winget install Cloudflare.cloudflared"
    exit 1
}
Write-Host "[OK] cloudflared: $($cf.Source)" -ForegroundColor Green

# Local stack
& (Join-Path $root "scripts\verify_local_demo.ps1")
if ($LASTEXITCODE -ne 0) { exit 1 }

$cfDir = Join-Path $env:USERPROFILE ".cloudflared"
if (-not (Test-Path $cfDir)) {
    New-Item -ItemType Directory -Path $cfDir -Force | Out-Null
}

if (-not $SkipLogin) {
    Write-Host ""
    Write-Host "Step 1 - Log in to Cloudflare (browser opens once):" -ForegroundColor Cyan
    Write-Host "  cloudflared tunnel login" -ForegroundColor White
    $ans = Read-Host "Run login now? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        & cloudflared tunnel login
    }
}

Write-Host ""
Write-Host "Step 2 - Create named tunnel (once):" -ForegroundColor Cyan
Write-Host "  cloudflared tunnel create $TunnelName" -ForegroundColor White
$ans = Read-Host "Create tunnel '$TunnelName' now? [Y/n]"
if ($ans -eq "" -or $ans -match "^[Yy]") {
    & cloudflared tunnel create $TunnelName
}

Write-Host ""
Write-Host "Step 3 - List tunnels and copy the TUNNEL ID:" -ForegroundColor Cyan
& cloudflared tunnel list

$credFiles = Get-ChildItem -Path $cfDir -Filter "*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "cert.pem" } |
    Sort-Object LastWriteTime -Descending

$tunnelId = ""
$credPath = ""
if ($credFiles) {
    $credPath = $credFiles[0].FullName
    $tunnelId = [System.IO.Path]::GetFileNameWithoutExtension($credFiles[0].Name)
    Write-Host "[OK] Latest credentials: $credPath" -ForegroundColor Green
    Write-Host "     Tunnel ID: $tunnelId" -ForegroundColor Green
    Write-Host "     CNAME target: ${tunnelId}.cfargotunnel.com" -ForegroundColor Yellow
}

if (-not $Hostname) {
    Write-Host ""
    Write-Host "Step 4 - Free hostname (no paid domain):" -ForegroundColor Cyan
    Write-Host "  1. Go to https://freedns.afraid.org (free account)"
    Write-Host "  2. Add subdomain e.g. legalease-demo.mooo.com"
    Write-Host "  3. Type: CNAME -> ${tunnelId}.cfargotunnel.com"
    Write-Host ""
    $Hostname = Read-Host "Enter your stable hostname (e.g. legalease-demo.mooo.com)"
}

if (-not $Hostname) {
    Write-Host "[!!] Hostname required. Re-run with -Hostname yourname.mooo.com" -ForegroundColor Red
    exit 1
}

$hostname = $Hostname.Trim().ToLower()
$configPath = Join-Path $cfDir "config.yml"
if ($credPath) {
    $credLine = ($credPath -replace "\\", "/")
} else {
    $credLine = "C:/Users/YOU/.cloudflared/TUNNEL_ID.json"
}

$config = @"
tunnel: $TunnelName
credentials-file: $credLine

ingress:
  - hostname: $hostname
    service: http://127.0.0.1:3000
  - service: http_status:404
"@

$config | Set-Content -Path $configPath -Encoding UTF8
Write-Host ""
Write-Host "[OK] Wrote $configPath" -ForegroundColor Green

$stableUrl = "https://$hostname"
& (Join-Path $root "scripts\configure_tunnel_env.ps1") -TunnelUrl $stableUrl -TunnelHost $hostname

Write-Host ""
Write-Host "Step 5 - Start the stable tunnel (keep this terminal open):" -ForegroundColor Cyan
Write-Host "  cloudflared tunnel run $TunnelName" -ForegroundColor White
Write-Host ""
Write-Host "Your stable link (does NOT change on restart):" -ForegroundColor Green
Write-Host "  $stableUrl" -ForegroundColor White
Write-Host ""
Write-Host "Restart backend + web if they were already running." -ForegroundColor Yellow
Write-Host "Test: .\scripts\verify_public_demo.ps1 -PublicUrl `"$stableUrl`"" -ForegroundColor Yellow
Write-Host ""

$linkFile = Join-Path $root "scripts\STABLE_PUBLIC_URL.txt"
@"
LegalEase stable public link
============================
URL: $stableUrl
Tunnel: $TunnelName

Daily start (keep terminal open):
  cloudflared tunnel run $TunnelName

Also running: ollama serve, run_backend.ps1, run_web.ps1
"@ | Set-Content -Path $linkFile -Encoding UTF8
Write-Host "Stable link saved to scripts\STABLE_PUBLIC_URL.txt" -ForegroundColor Green
Write-Host ""

$ans = Read-Host "Start tunnel now? [Y/n]"
if ($ans -eq "" -or $ans -match "^[Yy]") {
    & cloudflared tunnel run $TunnelName
}
