#!/usr/bin/env pwsh
# Push all code changes to AWS EC2, extract, rebuild containers, run go-live.
param(
    [string]$VmIp = "18.61.68.82",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\legalease-aws.pem",
    [string]$PublicUrl = "https://legalease.duckdns.org",  # EC2 runs 24/7 — laptop can be off
    [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$key = (Resolve-Path $KeyPath).Path
$archive = Join-Path $root "legalease-deploy.tgz"
$remote = "/opt/legalease"

if (-not $SkipArchive) {
    Write-Host "Packaging project (excludes Data, node_modules, .next, venv)..." -ForegroundColor Yellow
    Push-Location $root
    try {
        if (Test-Path $archive) { Remove-Item -Force $archive }
        tar --exclude=Data --exclude=web/node_modules --exclude=web/.next --exclude=.venv_win `
            --exclude=faiss_indexes --exclude=legalease-deploy.tgz --exclude=.pytest_cache `
            --exclude=.env --exclude=.env.local `
            -czf $archive .
        $mb = [math]::Round((Get-Item $archive).Length / 1MB, 1)
        Write-Host "[OK] $archive ($mb MB)" -ForegroundColor Green
    } finally {
        Pop-Location
    }
} elseif (-not (Test-Path $archive)) {
    throw "Archive missing: $archive (run without -SkipArchive)"
}

Write-Host "Uploading to ubuntu@${VmIp}:${remote}..." -ForegroundColor Yellow
ssh -i $key -o StrictHostKeyChecking=accept-new "ubuntu@$VmIp" "mkdir -p $remote"
scp -i $key -o StrictHostKeyChecking=accept-new $archive "ubuntu@${VmIp}:${remote}/"

$urlArg = if ($PublicUrl) { $PublicUrl.TrimEnd('/') } else { "" }
$remoteScript = Join-Path $env:TEMP "legalease-ec2-update.sh"
@(
    "#!/usr/bin/env bash"
    "set -euo pipefail"
    "cd $remote"
    "rm -rf web/app/\(app\)/premium 2>/dev/null || true"
    "tar -xzf legalease-deploy.tgz"
    "sed -i 's/\r$//' deploy/aws/*.sh 2>/dev/null || true"
    "chmod +x deploy/aws/*.sh 2>/dev/null || true"
    "bash deploy/aws/fix-ec2-env.sh '$urlArg'"
    "bash deploy/aws/fix-postgres-password.sh 2>/dev/null || true"
    "sed -i 's/\r$//' deploy/aws/ec2-go-live.sh deploy/aws/fix-ec2-env.sh deploy/aws/fix-postgres-password.sh 2>/dev/null || true"
    "chmod +x deploy/aws/ec2-go-live.sh deploy/aws/fix-ec2-env.sh 2>/dev/null || true"
    "sudo chown -R 10001:10001 /opt/legalease/Data /data 2>/dev/null || true"
    "bash deploy/aws/ec2-go-live.sh '$urlArg'"
) -join "`n" | Out-File -FilePath $remoteScript -Encoding ascii -NoNewline
Add-Content -Path $remoteScript -Value "`n" -Encoding ascii -NoNewline

Write-Host "Extracting + rebuild on EC2 (5-15 min)..." -ForegroundColor Yellow
scp -i $key -o StrictHostKeyChecking=accept-new $remoteScript "ubuntu@${VmIp}:/tmp/legalease-ec2-update.sh"
ssh -i $key "ubuntu@$VmIp" "sed -i 's/\r$//' /tmp/legalease-ec2-update.sh; chmod +x /tmp/legalease-ec2-update.sh; bash /tmp/legalease-ec2-update.sh"

Write-Host ""
Write-Host "Deploy finished." -ForegroundColor Green
if ($PublicUrl) {
    Write-Host "  App: $PublicUrl" -ForegroundColor Cyan
    Write-Host "  Health: ${PublicUrl}/api/v1/health/live" -ForegroundColor Gray
} else {
    Write-Host "  Check tunnel URL on EC2: grep trycloudflare /tmp/cloudflared.log" -ForegroundColor Gray
}
