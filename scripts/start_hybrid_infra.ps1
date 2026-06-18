# Start Postgres + Redis for hybrid deploy (requires Docker Desktop)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $candidates = @(
        "${env:ProgramFiles}\Docker\Docker\resources\bin\docker.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\resources\bin\docker.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { $env:Path += ";$(Split-Path $p)"; break }
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker not found. Install Docker Desktop, then run:" -ForegroundColor Red
    Write-Host "  docker compose up -d postgres redis" -ForegroundColor Yellow
    exit 1
}

docker compose up -d postgres redis
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Waiting for Postgres..." -ForegroundColor Gray
$ok = $false
foreach ($i in 1..30) {
    py -c @"
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('$root') / '.env')
import psycopg2
psycopg2.connect(os.environ['DATABASE_URL']).close()
"@ 2>$null
    if ($LASTEXITCODE -eq 0) { $ok = $true; break }
    Start-Sleep -Seconds 2
}
if ($ok) {
    Write-Host "Postgres ready." -ForegroundColor Green
} else {
    Write-Host "Postgres not reachable yet — check: docker compose ps" -ForegroundColor Yellow
}
