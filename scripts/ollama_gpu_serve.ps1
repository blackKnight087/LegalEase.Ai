# Restart Ollama with GPU offload for legalease-tuned (KB chat).
# Run in a dedicated terminal and leave it open.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $k = $Matches[1].Trim()
            $v = $Matches[2].Trim().Trim('"')
            if ($k -match '^(OLLAMA_|GPU_|RAG_EMBEDDING)') {
                Set-Item -Path "env:$k" -Value $v
            }
        }
    }
}

if (-not $env:OLLAMA_NUM_GPU) { $env:OLLAMA_NUM_GPU = "999" }
if (-not $env:OLLAMA_MODEL) { $env:OLLAMA_MODEL = "legalease-tuned" }

Write-Host "LegalEase - Ollama GPU serve" -ForegroundColor Cyan
Write-Host ('  OLLAMA_NUM_GPU = {0}' -f $env:OLLAMA_NUM_GPU)
Write-Host ('  OLLAMA_MODEL   = {0}' -f $env:OLLAMA_MODEL)
Write-Host '  Embeddings stay on CPU; RAG_EMBEDDING_DEVICE=cpu frees VRAM for chat.'
Write-Host ""

# Stop desktop Ollama so we can restart with GPU env
Get-Process -Name "ollama", "ollama app" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Error "ollama not in PATH. Install from https://ollama.com"
}

Write-Host ('Starting ollama serve with GPU layers={0}...' -f $env:OLLAMA_NUM_GPU) -ForegroundColor Green
Write-Host ('Warm-up: ollama run {0} ready' -f $env:OLLAMA_MODEL) -ForegroundColor DarkGray
Write-Host ""

# serve blocks — user keeps this window open
& ollama serve
