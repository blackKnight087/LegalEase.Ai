# Stop process listening on port 3000 (Next.js frontend)
$ErrorActionPreference = "SilentlyContinue"

$lines = netstat -ano | Select-String -Pattern ":\s*3000\s+.*LISTENING"
$pids = @()
foreach ($line in $lines) {
    $parts = ($line.ToString().Trim() -split '\s+')
    if ($parts.Length -ge 5) {
        $pids += [int]$parts[-1]
    }
}
$pids = $pids | Sort-Object -Unique
foreach ($procId in $pids) {
    if ($procId -gt 0) {
        cmd /c "taskkill /F /PID $procId" 2>$null | Out-Null
    }
}
Write-Host "Port 3000 cleared. Restart with: .\run_web.ps1"
