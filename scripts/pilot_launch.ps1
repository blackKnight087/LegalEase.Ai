# Start LegalEase pilot stack (Docker)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.pilot.example") {
        Copy-Item ".env.pilot.example" ".env"
        Write-Host "Created .env from .env.pilot.example — edit secrets before production pilot."
    } elseif (Test-Path ".env.docker.example") {
        Copy-Item ".env.docker.example" ".env"
        Write-Host "Created .env from .env.docker.example — edit secrets."
    } else {
        Write-Error ".env missing. Copy .env.pilot.example to .env"
    }
}

Write-Host "Building and starting Docker stack..."
docker compose up -d --build

Write-Host "Waiting for API health..."
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost/api/v1/health/live" -TimeoutSec 5
        if ($r.status -eq "ok") { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 3
}

if ($ok) {
    Write-Host "API is live: http://localhost/api/v1/health/live"
    try {
        $pub = Invoke-RestMethod -Uri "http://localhost/api/v1/health/public" -TimeoutSec 10
        Write-Host "core_db:" ($pub.core_db | ConvertTo-Json -Compress)
    } catch { }
} else {
    Write-Host "API not ready yet. Check: docker compose logs api"
}

Write-Host "Web UI: http://localhost"
Write-Host "Docs: docs/PILOT_LAUNCH.md"
