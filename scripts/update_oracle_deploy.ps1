# Push code updates to Oracle VM after initial deploy (see docs/DEPLOY_ORACLE_FREE.md)
param(
    [Parameter(Mandatory = $true)]
    [string]$OracleIp,
    [string]$SshKey = "$env:USERPROFILE\.ssh\legalease_oracle",
    [string]$RemotePath = "/opt/legalease"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Packaging LegalEase (excludes Data, node_modules, indexes)..."
tar --exclude=Data --exclude=web/node_modules --exclude=.venv_win --exclude=faiss_indexes --exclude=.git -czf legalease-deploy.tgz .

Write-Host "Uploading to ubuntu@${OracleIp}:${RemotePath}..."
scp -i $SshKey legalease-deploy.tgz "ubuntu@${OracleIp}:${RemotePath}/"

Write-Host @"
SSH to the server and run:

  cd $RemotePath
  tar -xzf legalease-deploy.tgz
  docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.override.yml up -d --build

Optional — export legalease-tuned from laptop first:
  ollama show legalease-tuned --modelfile > legalease-tuned.modelfile
  scp -i $SshKey legalease-tuned.modelfile ubuntu@${OracleIp}:~/
  ssh -i $SshKey ubuntu@${OracleIp} 'ollama create legalease-tuned -f ~/legalease-tuned.modelfile'
"@
