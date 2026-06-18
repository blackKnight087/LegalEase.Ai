#!/usr/bin/env pwsh
param(
    [string]$VmIp = "18.61.68.82",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\legalease-aws.pem",
    [string]$Email = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$key = (Resolve-Path $KeyPath).Path

Write-Host "=== Enable HTTPS on legalease.duckdns.org ===" -ForegroundColor Cyan
Write-Host "Also open port 443 in EC2 security group (HTTPS)." -ForegroundColor Yellow

$files = @(
    "deploy\aws\setup-https-duckdns.sh",
    "deploy\aws\docker-compose.https.yml",
    "deploy\nginx\nginx-duckdns-https.conf"
)
foreach ($f in $files) {
    $remote = "/opt/legalease/$($f.Replace('\','/'))"
    ssh -i $key "ubuntu@$VmIp" "mkdir -p $(Split-Path $remote -Parent)"
    scp -i $key (Join-Path $root $f) "ubuntu@${VmIp}:${remote}"
}

$emailEnv = if ($Email) { "CERTBOT_EMAIL=$Email" } else { "" }
ssh -i $key "ubuntu@$VmIp" "cd /opt/legalease && sed -i 's/\r$//' deploy/aws/setup-https-duckdns.sh && chmod +x deploy/aws/setup-https-duckdns.sh && $emailEnv bash deploy/aws/setup-https-duckdns.sh"

Write-Host "`nTest:" -ForegroundColor Cyan
try {
    $r = Invoke-WebRequest -Uri "https://legalease.duckdns.org/api/v1/health/live" -UseBasicParsing -TimeoutSec 20
    Write-Host "[OK] $($r.StatusCode) $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "If HTTP works but HTTPS fails, add security group rule: HTTPS port 443." -ForegroundColor Yellow
}
