#!/usr/bin/env pwsh
# One-time stable link - runs the setup wizard. See docs/STABLE_PUBLIC_LINK.md
param(
    [string]$TunnelName = "legalease-demo",
    [string]$Hostname = "",
    [switch]$SkipLogin
)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
& (Join-Path $root "scripts\setup_stable_cloudflare_tunnel.ps1") @PSBoundParameters
