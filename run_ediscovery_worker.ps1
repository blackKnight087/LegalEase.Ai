# Background worker for large e-discovery batches (Redis or SQLite poll)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (Test-Path ".env") { Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim().Trim('"'), "Process")
    }
} }
py scripts/ediscovery_worker.py
