#!/usr/bin/env pwsh
# Stable FREE link - no domain purchase. Uses Cloudflare Zero Trust + free subdomain (afraid.org).
# Skip "Authorize Cloudflare Tunnel" zone picker - that page needs a paid/custom domain on CF.
param(
    [string]$TunnelName = "legalease-demo",
    [string]$Hostname = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Stable link setup (no domain purchase)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "The browser 'Authorize Cloudflare Tunnel' page needs a domain" -ForegroundColor Yellow
Write-Host "on your Cloudflare account. SKIP IT. Use Zero Trust instead:" -ForegroundColor Yellow
Write-Host ""
Write-Host "ONE-TIME SETUP (about 15 min)" -ForegroundColor Green
Write-Host ""
Write-Host "1) Open: https://one.dash.cloudflare.com/" -ForegroundColor White
Write-Host "   Sign up free (Zero Trust plan is free)" -ForegroundColor Gray
Write-Host ""
Write-Host "2) Networks -> Tunnels -> Create a tunnel" -ForegroundColor White
Write-Host "   Name: $TunnelName" -ForegroundColor Gray
Write-Host "   Connector: Cloudflared" -ForegroundColor Gray
Write-Host ""
Write-Host "3) Copy the install command (has --token ...)" -ForegroundColor White
Write-Host "   Or download the credentials JSON to:" -ForegroundColor Gray
Write-Host "   $env:USERPROFILE\.cloudflared\" -ForegroundColor Gray
Write-Host ""
Write-Host "4) Free subdomain (NOT a purchase) at:" -ForegroundColor White
Write-Host "   https://freedns.afraid.org" -ForegroundColor Gray
Write-Host "   Pick e.g. legalease-YOURNAME.mooo.com (free forever)" -ForegroundColor Gray
Write-Host "   CNAME -> YOUR_TUNNEL_ID.cfargotunnel.com" -ForegroundColor Gray
Write-Host "   (Tunnel ID shown in Zero Trust dashboard)" -ForegroundColor Gray
Write-Host ""
Write-Host "5) In Zero Trust tunnel -> Public Hostname -> Add:" -ForegroundColor White
Write-Host "   Hostname: yourname.mooo.com" -ForegroundColor Gray
Write-Host "   Service: http://localhost:3000" -ForegroundColor Gray
Write-Host ""
Write-Host "6) Run connector (keep open every demo):" -ForegroundColor White
Write-Host "   cloudflared tunnel run --token YOUR_TOKEN" -ForegroundColor Gray
Write-Host ""
Write-Host "7) Update .env:" -ForegroundColor White
Write-Host '   .\scripts\configure_tunnel_env.ps1 -TunnelUrl "https://yourname.mooo.com" -TunnelHost "yourname.mooo.com"' -ForegroundColor Gray
Write-Host ""

if (-not $Hostname) {
    $Hostname = Read-Host "Enter your free hostname when ready (e.g. legalease-demo.mooo.com, or Enter to skip)"
}
if ($Hostname) {
    $url = "https://$($Hostname.Trim().ToLower())"
    & (Join-Path $root "scripts\configure_tunnel_env.ps1") -TunnelUrl $url -TunnelHost $Hostname.Trim().ToLower()
    @"
Stable URL: $url
Tunnel: $TunnelName
Setup guide: scripts\setup_stable_no_domain.ps1
"@ | Set-Content (Join-Path $PSScriptRoot "STABLE_PUBLIC_URL.txt") -Encoding UTF8
    Write-Host "Saved stable URL to scripts\STABLE_PUBLIC_URL.txt" -ForegroundColor Green
}

Write-Host ""
Write-Host "Need a link TODAY (changes each restart)? Run:" -ForegroundColor Cyan
Write-Host "  .\scripts\start_quick_tunnel.ps1" -ForegroundColor White
