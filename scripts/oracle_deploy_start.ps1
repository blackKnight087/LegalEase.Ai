#!/usr/bin/env pwsh
# Oracle Cloud Always Free - local prep (run on your Windows laptop).
# Full guide: docs/DEPLOY_ORACLE_FREE.md
param(
    [string]$VmIp = "",
    [switch]$CreateArchive,
    [switch]$UploadBootstrap
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$keyPath = Join-Path $env:USERPROFILE ".ssh\legalease_oracle"
$pubPath = "$keyPath.pub"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Oracle Always Free - local setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: SSH key ---
if (-not (Test-Path $pubPath)) {
    Write-Host "Creating SSH key for Oracle VM..." -ForegroundColor Yellow
    $sshDir = Split-Path $keyPath
    if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir -Force | Out-Null }
    ssh-keygen -t ed25519 -C "legalease-oracle" -f $keyPath -N '""'
    Write-Host "[OK] Key created: $keyPath" -ForegroundColor Green
} else {
    Write-Host "[OK] SSH key already exists: $keyPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "--- PASTE THIS into Oracle 'SSH public key' box ---" -ForegroundColor Yellow
Get-Content $pubPath
Write-Host "--- end of public key ---" -ForegroundColor Yellow
Write-Host ""

try {
    Get-Content $pubPath | Set-Clipboard
    Write-Host "[OK] Public key copied to clipboard." -ForegroundColor Green
} catch {
    Write-Host "[!] Copy the key above manually." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "ORACLE CONSOLE CHECKLIST (do this in browser):" -ForegroundColor Cyan
Write-Host "  1. https://cloud.oracle.com -> Sign up (Always Free)" -ForegroundColor White
Write-Host "  2. Compute -> Instances -> Create instance" -ForegroundColor White
Write-Host "  3. Name: legalease-prod" -ForegroundColor Gray
Write-Host "  4. Image: Ubuntu 22.04 (aarch64 / ARM)" -ForegroundColor Gray
Write-Host "  5. Shape: Ampere A1 - max free (4 OCPU / 24 GB if available)" -ForegroundColor Gray
Write-Host "  6. Public IPv4: assign" -ForegroundColor Gray
Write-Host "  7. Paste SSH public key (clipboard)" -ForegroundColor Gray
Write-Host "  8. Create -> note PUBLIC IP" -ForegroundColor Gray
Write-Host ""
Write-Host "FIREWALL (Oracle -> VCN -> Security List -> Ingress):" -ForegroundColor Cyan
Write-Host "  TCP 22, 80, 443 from 0.0.0.0/0" -ForegroundColor Gray
Write-Host ""

if ($CreateArchive -or $VmIp) {
    $archive = Join-Path $root "legalease-deploy.tgz"
    Write-Host "Creating deploy archive (excludes Data, node_modules, venv)..." -ForegroundColor Yellow
    Push-Location $root
    try {
        if (Get-Command tar -ErrorAction SilentlyContinue) {
            tar --exclude=Data --exclude=web/node_modules --exclude=web/.next --exclude=.venv_win --exclude=faiss_indexes --exclude=legalease-deploy.tgz -czf $archive .
            Write-Host "[OK] Archive: $archive ($([math]::Round((Get-Item $archive).Length / 1MB, 1)) MB)" -ForegroundColor Green
        } else {
            Write-Host "[!!] tar not found. Use Git clone on VM instead (see docs)." -ForegroundColor Red
        }
    } finally {
        Pop-Location
    }
}

if ($UploadBootstrap -and $VmIp) {
    Write-Host "Uploading bootstrap to ubuntu@$VmIp ..." -ForegroundColor Yellow
    scp -i $keyPath -o StrictHostKeyChecking=accept-new `
        (Join-Path $root "deploy\oracle\bootstrap.sh") `
        (Join-Path $root "deploy\oracle\.env.production.example") `
        "ubuntu@${VmIp}:/tmp/"
    Write-Host "[OK] Uploaded. SSH in and run:" -ForegroundColor Green
    Write-Host "  ssh -i `"$keyPath`" ubuntu@$VmIp" -ForegroundColor White
    Write-Host "  chmod +x /tmp/bootstrap.sh && sudo /tmp/bootstrap.sh" -ForegroundColor White
}

if ($VmIp -and (Test-Path (Join-Path $root "legalease-deploy.tgz"))) {
    Write-Host "Uploading archive to VM..." -ForegroundColor Yellow
    scp -i $keyPath -o StrictHostKeyChecking=accept-new (Join-Path $root "legalease-deploy.tgz") "ubuntu@${VmIp}:/opt/legalease/"
    Write-Host "[OK] On VM run:" -ForegroundColor Green
    Write-Host "  cd /opt/legalease && tar -xzf legalease-deploy.tgz" -ForegroundColor White
    Write-Host "  cp deploy/oracle/.env.production.example .env && nano .env" -ForegroundColor White
}

if (-not $VmIp) {
    Write-Host "When you have the VM public IP, run:" -ForegroundColor Cyan
    Write-Host "  .\scripts\oracle_deploy_start.ps1 -VmIp YOUR.IP -CreateArchive -UploadBootstrap" -ForegroundColor White
}

Write-Host ""
Write-Host "Docs: docs\DEPLOY_ORACLE_FREE.md" -ForegroundColor DarkGray
