#!/usr/bin/env pwsh
# Push fixes to EC2 and run full go-live (tunnel + env + rebuild).
param(
    [string]$VmIp = "18.61.68.82",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\legalease-aws.pem",
    [string]$PublicUrl = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$key = (Resolve-Path $KeyPath).Path

$files = @(
    "deploy\aws\ec2-go-live.sh",
    "deploy\aws\fix-ec2-env.sh",
    "deploy\aws\docker-compose.override.yml",
    "deploy\Dockerfile.api.aws",
    "backend\app\core\pg_rest_schema.py"
)
foreach ($f in $files) {
    $local = Join-Path $root $f
    $remoteDir = "/opt/legalease/$(Split-Path $f -Parent)".Replace('\', '/')
    ssh -i $key -o StrictHostKeyChecking=accept-new "ubuntu@$VmIp" "mkdir -p $remoteDir"
    scp -i $key $local "ubuntu@${VmIp}:/opt/legalease/$($f.Replace('\','/'))"
}

$urlArg = if ($PublicUrl) { $PublicUrl } else { "" }
ssh -i $key "ubuntu@$VmIp" "sed -i 's/\r$//' /opt/legalease/deploy/aws/ec2-go-live.sh; chmod +x /opt/legalease/deploy/aws/ec2-go-live.sh; bash /opt/legalease/deploy/aws/ec2-go-live.sh $urlArg"

Write-Host ""
Write-Host "If port 80 is still blocked on AWS, the script started a Cloudflare tunnel." -ForegroundColor Cyan
Write-Host "Read the URL from the output above, or on EC2: grep trycloudflare /tmp/cloudflared.log" -ForegroundColor Gray
