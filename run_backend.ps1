# LegalEase FastAPI backend (production stack)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Test-PortListening([int]$Port) {
    $line = netstat -ano | findstr "LISTENING" | findstr ":$Port " | Select-Object -First 1
    return [bool]$line
}

function Test-BackendHealthy() {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health/live" -UseBasicParsing -TimeoutSec 4
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

Write-Host "LegalEase backend launcher (port 8000) - stable / efficient / safe" -ForegroundColor Cyan

. (Join-Path $PSScriptRoot "scripts\apply_local_env.ps1")
Set-LegalEaseLocalDevEnv -ProjectRoot $PSScriptRoot
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpegCmd) {
    Write-Warning "ffmpeg not found on PATH - speech-to-text needs ffmpeg for webm audio. Install: winget install Gyan.FFmpeg"
} else {
    Write-Host "  ffmpeg: $($ffmpegCmd.Source)" -ForegroundColor DarkGray
}
Write-Host "  Indexing never blocked; smaller batches when RAM is high." -ForegroundColor DarkGray
if (Test-Path (Join-Path $PSScriptRoot ".env")) {
    Get-Content (Join-Path $PSScriptRoot ".env") | ForEach-Object {
        if ($_ -match '^\s*(LLM_BACKEND|OLLAMA_MODEL|OLLAMA_BASE_URL)\s*=\s*(.+)\s*$') {
            Write-Host ("  {0} = {1}" -f $Matches[1], $Matches[2].Trim()) -ForegroundColor DarkGray
        }
    }
}

if (Test-PortListening 8000) {
    if (Test-BackendHealthy) {
        Write-Host "Backend already running: http://127.0.0.1:8000" -ForegroundColor Green
        Write-Host "Health: http://127.0.0.1:8000/api/v1/health/live"
        exit 0
    }
    Write-Host "Port 8000 is stuck (not responding). Clearing it..." -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot "stop_backend.ps1")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Could not free port 8000. End python.exe in Task Manager, then retry."
    }
    Start-Sleep -Seconds 2
}

# Fast startup: skip blocking RAG warmup; embeddings still load in background (see main.py).
if (-not $env:LEGALEEASE_SKIP_RAG_WARMUP) {
    $env:LEGALEEASE_SKIP_RAG_WARMUP = "1"
    Write-Host "Fast startup: embeddings load in background after API is live" -ForegroundColor DarkGray
}
# Keep login/health responsive while KB maintenance runs in background
if (-not $env:REINDEX_AUTO_ON_STALE) { $env:REINDEX_AUTO_ON_STALE = "0" }
if (-not $env:REINDEX_AUTO_STARTUP) { $env:REINDEX_AUTO_STARTUP = "0" }
if (-not $env:INDEX_JOB_WORKERS) { $env:INDEX_JOB_WORKERS = "1" }
# Thread indexing shares one embedding model (~half the RAM vs subprocess on 16GB PCs)
$env:INDEX_JOB_USE_PROCESS = "0"
$env:INDEX_JOB_FORCE_PROCESS = "0"
if (-not $env:RAG_INDEX_EMBED_BATCH) { $env:RAG_INDEX_EMBED_BATCH = "32" }
if (-not $env:LEGALEEASE_RAM_PAUSE_PCT) { $env:LEGALEEASE_RAM_PAUSE_PCT = "88" }
if (-not $env:LEGALEEASE_RAM_HIGH_PCT) { $env:LEGALEEASE_RAM_HIGH_PCT = "85" }
if (-not $env:FAISS_VECTOR_COUNT_CACHE_SEC) { $env:FAISS_VECTOR_COUNT_CACHE_SEC = "12" }
if (-not $env:ENGINE_STATUS_CACHE_SEC) { $env:ENGINE_STATUS_CACHE_SEC = "15" }
if (-not $env:RAG_PREFER_BASE_EMBEDDINGS) { $env:RAG_PREFER_BASE_EMBEDDINGS = "1" }
if (-not $env:OLLAMA_KB_LOCK_MODEL) { $env:OLLAMA_KB_LOCK_MODEL = "1" }
if (-not $env:LEGALEEASE_MINIMAL_STARTUP) { $env:LEGALEEASE_MINIMAL_STARTUP = "1" }
# 16GB laptops: smallest embedding first - respect .env if user set LOW_RESOURCE_MODE=0
$envFile = Join-Path $PSScriptRoot ".env"
$envLowResource = $null
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*LOW_RESOURCE_MODE\s*=\s*(.+)\s*$') {
            $envLowResource = $Matches[1].Trim()
        }
    }
}
if ($null -ne $envLowResource -and $envLowResource -ne "") {
    $env:LOW_RESOURCE_MODE = $envLowResource
} elseif (-not $env:LOW_RESOURCE_MODE) {
    $env:LOW_RESOURCE_MODE = "1"
}
$env:LEGALEEASE_HF_CACHE = (Join-Path $PSScriptRoot "Data\hf_cache")
$env:HF_HOME = $env:LEGALEEASE_HF_CACHE
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
# torch.cuda probe can block 2+ min when Ollama already loaded the GPU — skip at import
if (-not $env:LEGALEEASE_SKIP_CUDA_PROBE) { $env:LEGALEEASE_SKIP_CUDA_PROBE = "1" }
if ($env:TRANSFORMERS_CACHE) { Remove-Item Env:TRANSFORMERS_CACHE -ErrorAction SilentlyContinue }
$env:HF_HUB_DISABLE_SYMLINKS = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
if (-not $env:TQDM_DISABLE) { $env:TQDM_DISABLE = "1" }
if (-not $env:EMBEDDING_MODEL_LOAD_TIMEOUT_SEC) { $env:EMBEDDING_MODEL_LOAD_TIMEOUT_SEC = "240" }
if (-not $env:HF_EMBEDDING_MODEL) { $env:HF_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2" }
if (-not $env:EMBEDDING_MAX_LOAD_RETRIES) { $env:EMBEDDING_MAX_LOAD_RETRIES = "3" }
# Skip training/coach at boot unless explicitly enabled
if (-not $env:LEGALEEASE_EMERGENCY_STARTUP) { $env:LEGALEEASE_EMERGENCY_STARTUP = "1" }
if (-not $env:DISABLE_COACH_STARTUP) { $env:DISABLE_COACH_STARTUP = "1" }
if (-not $env:DISABLE_NEURAL_TUNING_STARTUP) { $env:DISABLE_NEURAL_TUNING_STARTUP = "1" }
if (-not $env:DISABLE_AUTO_REINDEX_STARTUP) { $env:DISABLE_AUTO_REINDEX_STARTUP = "1" }

# Fast boot (~1 min): API first, embeddings/Ollama load in background (override with LEGALEEASE_FULL_WARMUP=1)
if ($env:LEGALEEASE_FULL_WARMUP -ne "1") {
    if (-not $env:LEGALEEASE_SKIP_EMBEDDING_WARMUP) { $env:LEGALEEASE_SKIP_EMBEDDING_WARMUP = "1" }
    $env:OLLAMA_AUTO_WARMUP = "0"
    Write-Host "Fast startup (~1 min). For full KB warmup before API: `$env:LEGALEEASE_FULL_WARMUP='1'" -ForegroundColor DarkGray
} else {
    Write-Host "Full warmup mode (2-5 min) - loading embeddings + Ollama before API." -ForegroundColor DarkGray
}

# GPU + RAM diagnostics
$gpuLine = $null
try {
    $gpuLine = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1
} catch { }
if ($gpuLine) {
    Write-Host "  NVIDIA GPU: $gpuLine" -ForegroundColor DarkGray
} else {
    Write-Host "  NVIDIA GPU: not detected (nvidia-smi)" -ForegroundColor DarkGray
}
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*OLLAMA_NUM_GPU\s*=\s*(.+)\s*$' -and -not $env:OLLAMA_NUM_GPU) {
            $env:OLLAMA_NUM_GPU = $Matches[1].Trim()
        }
    }
}
if (-not $env:OLLAMA_AUTO_START) { $env:OLLAMA_AUTO_START = "1" }
if ($env:OLLAMA_NUM_GPU) {
    Write-Host "  OLLAMA_NUM_GPU = $($env:OLLAMA_NUM_GPU) (auto-start Ollama on GPU with backend)" -ForegroundColor DarkGray
} else {
    $env:OLLAMA_NUM_GPU = "999"
    Write-Host '  OLLAMA_NUM_GPU = 999 (default - GPU auto-start enabled)' -ForegroundColor DarkGray
}
$gpuProfile = "balanced"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*GPU_PROFILE\s*=\s*(.+)\s*$') { $gpuProfile = $Matches[1].Trim() }
        if ($_ -match '^\s*STT_DEVICE\s*=\s*(.+)\s*$') {
            Write-Host ("  STT_DEVICE = {0}" -f $Matches[1].Trim()) -ForegroundColor DarkGray
        }
        if ($_ -match '^\s*RAG_EMBEDDING_DEVICE\s*=\s*(.+)\s*$') {
            Write-Host ("  RAG_EMBEDDING_DEVICE = {0}" -f $Matches[1].Trim()) -ForegroundColor DarkGray
        }
        if ($_ -match '^\s*LEGALEEASE_GPU_ONLY\s*=\s*(.+)\s*$' -and -not $env:LEGALEEASE_GPU_ONLY) {
            $env:LEGALEEASE_GPU_ONLY = $Matches[1].Trim()
        }
    }
}
Write-Host "  GPU_PROFILE = $gpuProfile (see docs/GPU_SETUP.md)" -ForegroundColor DarkGray
if ($env:LEGALEEASE_GPU_ONLY -eq "1") {
    Write-Host '  LEGALEEASE_GPU_ONLY = 1 (Ollama + training on GPU, embeddings CPU during chat)' -ForegroundColor DarkGray
}
try {
    $ramPct = & py -c "import psutil; v=psutil.virtual_memory(); print(int(v.percent))" 2>$null
    if ($ramPct -and [int]$ramPct -gt 80) {
        Write-Warning "System RAM at ${ramPct}% - close other apps before indexing or first Whisper load."
    }
} catch { }

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) { Write-Error "Python not found. Install Python 3.10+." }

$venvPy = Join-Path $PSScriptRoot ".venv_win\Scripts\python.exe"
if (Test-Path $venvPy) {
    $venvOk = $false
    try {
        $null = & $venvPy -c "import typing_extensions, anyio, uvicorn; import uvicorn.main" 2>$null
        if ($LASTEXITCODE -eq 0) { $venvOk = $true }
    } catch {
        $venvOk = $false
    }
    if ($venvOk) {
        $py = @{ Source = $venvPy }
        Write-Host "Using project venv: $venvPy"
    } else {
        Write-Warning "Project venv is broken (PermissionError on site-packages). Using system Python instead."
        Write-Warning "To repair: close all Python terminals, then recreate .venv_win or run as Administrator."
    }
}

$reload = $env:LEGALEEASE_RELOAD -eq "1"

$downloadScript = Join-Path $PSScriptRoot "scripts\download_embedding_model.py"
$embedCache = Join-Path $PSScriptRoot "Data\hf_cache\models--sentence-transformers--paraphrase-MiniLM-L3-v2"
if ($env:LEGALEEASE_FULL_WARMUP -eq "1" -and (Test-Path $downloadScript) -and -not (Test-Path $embedCache)) {
    Write-Host "Ensuring embedding model is cached (one-time download if needed)..." -ForegroundColor DarkGray
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    # tqdm/HF download progress writes to stderr - not a failure (avoid RemoteException noise).
    & $py.Source $downloadScript *>&1 | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
    $dlExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($dlExit -ne 0) {
        Write-Warning "Embedding model pre-download failed - backend will retry in background."
    }
}

$warmScript = Join-Path $PSScriptRoot "scripts\warm_embeddings_once.py"
if ($env:LEGALEEASE_SKIP_EMBEDDING_WARMUP -eq "1") {
    Write-Host 'Skipping embedding warmup (LEGALEEASE_SKIP_EMBEDDING_WARMUP=1) - KB loads on first upload.' -ForegroundColor DarkGray
} elseif (Test-Path $warmScript) {
    Write-Host 'Loading embedding model into memory (1-3 min on first run; set LEGALEEASE_SKIP_EMBEDDING_WARMUP=1 to skip)...' -ForegroundColor DarkGray
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $py.Source $warmScript *>&1 | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
    $warmExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($warmExit -ne 0) {
        Write-Warning "Embedding warmup failed - wait on Documents page or restart after freeing RAM."
    } else {
        Write-Host "Embeddings ready for indexing." -ForegroundColor Green
    }
}

$ollamaScript = Join-Path $PSScriptRoot "scripts\ensure_ollama_once.py"
if ((Test-Path $ollamaScript) -and ($env:LLM_BACKEND -ne "lmstudio")) {
    if (-not $env:LLM_BACKEND) { $env:LLM_BACKEND = "ollama" }
    Write-Host "Ensuring Ollama is running on GPU for legalease-tuned..." -ForegroundColor DarkGray
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $py.Source $ollamaScript *>&1 | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
    $ErrorActionPreference = $prevEap
}

# Firm Chat user search + auth must use the same SQLite file
$mainDb = Join-Path $PSScriptRoot "legalease.db"
$env:LEGALEASE_DB_PATH = $mainDb
Write-Host "  LEGALEASE_DB_PATH = $mainDb" -ForegroundColor DarkGray

Write-Host "Loading Python modules (30-90 sec, no output is normal)..." -ForegroundColor DarkGray
Write-Host "Starting LegalEase API on http://127.0.0.1:8000 ..."
Write-Host "Test: http://127.0.0.1:8000/api/v1/health/live"
Write-Host "Docs: http://127.0.0.1:8000/docs"
if ($reload) {
    Write-Host "Reload ON (backend/ only). Unset LEGALEEASE_RELOAD for stable mode."
} else {
    Write-Host "Stable mode: no file-watch restarts (recommended)."
}

$uvicornArgs = @(
    "-m", "uvicorn", "backend.app.main:app",
    "--host", "127.0.0.1",
    "--port", "8000",
    "--timeout-keep-alive", "300",
    "--limit-concurrency", "200"
)

if ($reload) {
    $uvicornArgs += @(
        "--reload",
        "--reload-dir", "backend",
        "--reload-dir", ".",
        "--reload-exclude", "Data/*",
        "--reload-exclude", "web/*",
        "--reload-exclude", "frontend/*",
        "--reload-exclude", "node_modules/*",
        "--reload-exclude", "*.db"
    )
}

& $py.Source @uvicornArgs
