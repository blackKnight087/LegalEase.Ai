#!/usr/bin/env pwsh
# Fix DuckDNS + EC2: server env, rebuild web, verify. Port 80 must be open in AWS SG.
param(
    [string]$VmIp = "18.61.68.82",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\legalease-aws.pem",
    [string]$DuckDnsHost = "legalease.duckdns.org"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$key = (Resolve-Path $KeyPath).Path
$base = "http://${DuckDnsHost}"

Write-Host "=== DuckDNS + EC2 setup ===" -ForegroundColor Cyan
Write-Host "  Host: $DuckDnsHost -> $VmIp (DNS must match)" -ForegroundColor Gray

# Upload and run setup script
$setup = Join-Path $root "deploy\aws\setup-duckdns.sh"
scp -i $key -o StrictHostKeyChecking=accept-new $setup "ubuntu@${VmIp}:/opt/legalease/deploy/aws/setup-duckdns.sh"
ssh -i $key "ubuntu@$VmIp" "sed -i 's/\r$//' /opt/legalease/deploy/aws/setup-duckdns.sh; chmod +x /opt/legalease/deploy/aws/setup-duckdns.sh; bash /opt/legalease/deploy/aws/setup-duckdns.sh '$base'"

Write-Host "`n=== Port 80 check from your PC ===" -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "$base/api/v1/health/live" -UseBasicParsing -TimeoutSec 12
    Write-Host "[OK] DuckDNS reachable: $($r.StatusCode) $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "[BLOCKED] Cannot reach $base from this network (AWS security group)." -ForegroundColor Red
    $script:PortBlocked = $true
    Write-Host @"

Open AWS EC2 security group inbound rule:
  Type: HTTP | Port: 80 | Source: 0.0.0.0/0

Steps: EC2 -> Instances -> your instance -> Security -> Security group ->
  Edit inbound rules -> Add rule -> Save

Then re-test:
  curl.exe http://${DuckDnsHost}/api/v1/health/live

Temporary access without opening port 80:
  ssh -i `"$key`" -L 8080:127.0.0.1:80 ubuntu@$VmIp
  Open http://localhost:8080

"@ -ForegroundColor Gray
}

Write-Host "`nAdd to EC2 /opt/legalease/.env for auto IP updates after reboot:" -ForegroundColor Cyan
Write-Host "  DUCKDNS_TOKEN=your-token-from-duckdns.org" -ForegroundColor Gray

if ($script:PortBlocked) { exit 2 }
