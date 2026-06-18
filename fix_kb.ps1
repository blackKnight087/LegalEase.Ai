# Stop backend, repair embeddings + FAISS index, then tell you to restart.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "LegalEase KB repair" -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "stop_backend.ps1")

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) { Write-Error "Python not found." }

$env:LOW_RESOURCE_MODE = "1"
$env:LEGALEEASE_HF_CACHE = (Join-Path $PSScriptRoot "Data\hf_cache")
$env:HF_HUB_DISABLE_SYMLINKS = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $py.Source (Join-Path $PSScriptRoot "scripts\download_embedding_model.py")
& $py.Source (Join-Path $PSScriptRoot "scripts\fix_kb_now.py")
$fixExit = $LASTEXITCODE
$ErrorActionPreference = $prevEap

if ($fixExit -ne 0) {
    Write-Warning "KB repair had errors. Close other apps to free RAM and run again."
} else {
    Write-Host "KB repair complete." -ForegroundColor Green
}

Write-Host ""
Write-Host "Now run:  .\run_backend.ps1" -ForegroundColor Yellow
Write-Host "Then open Documents and confirm vectors > 0 and Query ready = Yes."
