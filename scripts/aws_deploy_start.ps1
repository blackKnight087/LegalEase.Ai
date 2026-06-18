#!/usr/bin/env pwsh
# AWS EC2 deploy helper — run on your Windows laptop from project root.
param(
    [Parameter(Mandatory = $true)]
    [string]$VmIp,
    [Parameter(Mandatory = $true)]
    [string]$KeyPath,
    [switch]$CreateArchive,
    [switch]$Bootstrap,
    [switch]$Upload
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$key = (Resolve-Path $KeyPath).Path
# Fix Windows SSH key permissions if needed
$sshCopy = Join-Path $env:USERPROFILE ".ssh\legalease-aws.pem"
if ($key -ne $sshCopy) {
    New-Item -ItemType Directory -Force -Path (Split-Path $sshCopy) | Out-Null
    Copy-Item -Force $key $sshCopy
    icacls $sshCopy /inheritance:r | Out-Null
    icacls $sshCopy /grant:r "$($env:USERNAME):(R)" | Out-Null
    icacls $sshCopy /remove "CodexSandboxUsers" 2>$null | Out-Null
    $key = $sshCopy
}
$archive = Join-Path $root "legalease-deploy.tgz"

Write-Host ""
Write-Host "AWS LegalEase deploy helper" -ForegroundColor Cyan
Write-Host "  VM: ubuntu@$VmIp" -ForegroundColor Gray
Write-Host "  Key: $key" -ForegroundColor Gray
Write-Host ""

if ($CreateArchive -or $Upload) {
    Write-Host "Creating deploy archive..." -ForegroundColor Yellow
    Push-Location $root
    try {
        tar --exclude=Data --exclude=web/node_modules --exclude=web/.next --exclude=.venv_win --exclude=faiss_indexes --exclude=legalease-deploy.tgz -czf $archive .
        Write-Host "[OK] $archive ($([math]::Round((Get-Item $archive).Length / 1MB, 1)) MB)" -ForegroundColor Green
    } finally {
        Pop-Location
    }
}

if ($Bootstrap) {
    Write-Host "Running bootstrap on EC2 (Docker install)..." -ForegroundColor Yellow
    scp -i $key -o StrictHostKeyChecking=accept-new (Join-Path $root "deploy\oracle\bootstrap.sh") "ubuntu@${VmIp}:/tmp/"
    ssh -i $key -o StrictHostKeyChecking=accept-new "ubuntu@$VmIp" "chmod +x /tmp/bootstrap.sh && sudo /tmp/bootstrap.sh"
}

if ($Upload) {
    Write-Host "Uploading project..." -ForegroundColor Yellow
    ssh -i $key -o StrictHostKeyChecking=accept-new "ubuntu@$VmIp" "sudo mkdir -p /opt/legalease && sudo chown ubuntu:ubuntu /opt/legalease"
    scp -i $key -o StrictHostKeyChecking=accept-new $archive "ubuntu@${VmIp}:/opt/legalease/"
    scp -i $key -o StrictHostKeyChecking=accept-new (Join-Path $root "deploy\aws\.env.production.example") "ubuntu@${VmIp}:/opt/legalease/"
    Write-Host "[OK] Uploaded." -ForegroundColor Green
    Write-Host ""
    Write-Host "SSH in:" -ForegroundColor Cyan
    Write-Host "  ssh -i `"$key`" ubuntu@$VmIp" -ForegroundColor White
    Write-Host ""
    Write-Host "On EC2:" -ForegroundColor Cyan
    Write-Host "  cd /opt/legalease && tar -xzf legalease-deploy.tgz" -ForegroundColor White
    Write-Host "  cp deploy/aws/.env.production.example .env && nano .env" -ForegroundColor White
    Write-Host "  bash deploy/aws/fix-ec2-env.sh YOUR.PUBLIC.IP   # sets .env + rebuilds web" -ForegroundColor White
    Write-Host "  See deploy/aws/OPEN_PORT_80.md — open inbound HTTP :80 on the security group" -ForegroundColor Yellow
}

if (-not ($CreateArchive -or $Upload -or $Bootstrap)) {
    Write-Host "Example (replace IP and key path):" -ForegroundColor Yellow
    Write-Host '  .\scripts\aws_deploy_start.ps1 -VmIp 3.110.x.x -KeyPath "C:\Users\YOU\legalease-aws.pem" -Bootstrap -CreateArchive -Upload' -ForegroundColor White
}
