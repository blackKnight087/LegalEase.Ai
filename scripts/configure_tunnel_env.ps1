#!/usr/bin/env pwsh
# Set PUBLIC_APP_URL and CORS_ORIGINS in project .env for a Cloudflare tunnel URL.
param(
    [Parameter(Mandatory = $true)]
    [string]$TunnelUrl,
    [string]$TunnelHost = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $root ".env"
$url = $TunnelUrl.Trim().TrimEnd("/")
$hostOnly = $TunnelHost.Trim()
if (-not $hostOnly -and $url -match "^https?://([^/]+)") {
    $hostOnly = $Matches[1]
}

if ($url -notmatch "^https?://") {
    Write-Error "TunnelUrl must start with https:// (e.g. https://abc.trycloudflare.com)"
}

if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root ".env.example") $envFile
    Write-Host "Created .env from .env.example"
}

function Set-EnvLine($path, $key, $value) {
    $lines = @(Get-Content $path -ErrorAction SilentlyContinue)
    $found = $false
    $out = [System.Collections.Generic.List[string]]::new()
    foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($key))\s*=") {
            if (-not $found) {
                $out.Add("$key=$value")
                $found = $true
            }
            # skip duplicate keys
        } else {
            $out.Add($line)
        }
    }
    if (-not $found) {
        $out.Add("$key=$value")
    }
    $out | Set-Content $path -Encoding UTF8
}

Set-EnvLine $envFile "PUBLIC_APP_URL" $url
Set-EnvLine $envFile "CORS_ORIGINS" $url

# web/.env.local: keep API on localhost so Next.js rewrites work through single tunnel on :3000
$webLocal = Join-Path $root "web\.env.local"
if (-not (Test-Path $webLocal)) {
    $ex = Join-Path $root "web\.env.local.example"
    if (Test-Path $ex) { Copy-Item $ex $webLocal }
}
if (Test-Path $webLocal) {
    Set-EnvLine $webLocal "NEXT_PUBLIC_API_URL" "http://127.0.0.1:8000"
    if ($hostOnly) {
        Set-EnvLine $webLocal "NEXT_PUBLIC_TUNNEL_HOST" $hostOnly
    }
}

Write-Host "Updated:" -ForegroundColor Green
Write-Host "  PUBLIC_APP_URL=$url"
Write-Host "  CORS_ORIGINS=$url"
if ($hostOnly) {
    Write-Host "  NEXT_PUBLIC_TUNNEL_HOST=$hostOnly"
}
Write-Host "  web/.env.local NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 (Next proxy via tunnel :3000)"
Write-Host "`nRestart backend: .\run_backend.ps1" -ForegroundColor Yellow
Write-Host "Restart web if it was already running: .\run_web.ps1" -ForegroundColor Yellow
