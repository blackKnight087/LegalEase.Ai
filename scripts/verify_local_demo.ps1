#!/usr/bin/env pwsh
# Verify local stack before sharing via tunnel.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$ok = $true
function Test-Url($label, $url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) {
            Write-Host "[OK] $label" -ForegroundColor Green
            return $true
        }
        Write-Host "[FAIL] $label HTTP $($r.StatusCode)" -ForegroundColor Red
        return $false
    } catch {
        Write-Host "[FAIL] $label - $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

Write-Host "LegalEase local demo health check" -ForegroundColor Cyan
if (-not (Test-Url "API live" "http://127.0.0.1:8000/api/v1/health/live")) { $ok = $false }
if (-not (Test-Url "API LLM" "http://127.0.0.1:8000/api/v1/health/llm")) { $ok = $false }
if (-not (Test-Url "Ollama" "http://127.0.0.1:11434/api/tags")) { $ok = $false }
if (-not (Test-Url "Web" "http://127.0.0.1:3000")) { $ok = $false }

if ($ok) {
    Write-Host "`nAll checks passed. Safe to start cloudflared." -ForegroundColor Green
    exit 0
}
Write-Host "`nFix failures above before exposing a public tunnel." -ForegroundColor Yellow
Write-Host 'Start: ollama serve; .\run_backend.ps1; .\run_web.ps1'
exit 1
