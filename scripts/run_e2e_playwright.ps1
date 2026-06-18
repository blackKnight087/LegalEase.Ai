# Browser E2E — requires API (8000) and web (3000) running.
# Usage:
#   .\run_e2e_playwright.ps1
#   $env:E2E_STRIPE='1'; .\run_e2e_playwright.ps1   # also open billing/settings

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "tests\e2e")

if (-not (Test-Path "node_modules")) {
  npm ci
  npx playwright install chromium
}

$env:E2E_BASE_URL = if ($env:E2E_BASE_URL) { $env:E2E_BASE_URL } else { "http://127.0.0.1:3000" }
$env:E2E_API_URL = if ($env:E2E_API_URL) { $env:E2E_API_URL } else { "http://127.0.0.1:8000" }
Remove-Item Env:E2E_SKIP -ErrorAction SilentlyContinue

npm test
