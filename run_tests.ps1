# LegalEase SaaS automated test runner
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Running LegalEase test suite..." -ForegroundColor Cyan
py -m pytest tests/ -v --tb=short 2>&1
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host "`nAll tests passed." -ForegroundColor Green
} else {
    Write-Host "`nTests failed (exit $code)." -ForegroundColor Red
}
exit $code
