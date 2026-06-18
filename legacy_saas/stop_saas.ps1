# Stop LegalEase SaaS processes (fast - no hanging taskkill)
$ErrorActionPreference = "SilentlyContinue"

$ports = @(8001, 5173, 5174, 5175, 5176, 5177, 5178)
$killed = 0

foreach ($port in $ports) {
    $pids = @()
    try {
        $pids = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch { }

    foreach ($procId in $pids) {
        if ($procId -gt 4) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            $killed++
        }
    }
}

Write-Host "Stopped $killed process(es) on ports: $($ports -join ', ')" -ForegroundColor Yellow
Write-Host "Note: zombie on port 8000 is ignored (use API on 8001 via run_saas.ps1)" -ForegroundColor Gray
