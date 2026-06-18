# Stop process listening on port 8000 (LegalEase API)
$ErrorActionPreference = "SilentlyContinue"

function Get-ListenerPids([int]$Port) {
    # Only LISTENING rows — avoids scanning thousands of CLOSE_WAIT lines (netstat can hang).
    $pids = @()
    $lines = netstat -ano | findstr "LISTENING" | findstr ":$Port "
    foreach ($line in $lines) {
        $parts = ($line.Trim() -split '\s+')
        if ($parts.Length -ge 5) {
            $listenerPid = 0
            if ([int]::TryParse($parts[-1], [ref]$listenerPid) -and $listenerPid -gt 0) {
                $pids += $listenerPid
            }
        }
    }
    return $pids | Sort-Object -Unique
}

$pids = Get-ListenerPids 8000
if (-not $pids -or $pids.Count -eq 0) {
    Write-Host "Port 8000 is free. Restart with: .\run_backend.ps1"
    exit 0
}

foreach ($procId in $pids) {
    Write-Host "Stopping PID $procId on port 8000..."
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 400
    $still = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($still) {
        cmd /c "taskkill /F /PID $procId" 2>$null | Out-Null
    }
}

Start-Sleep -Seconds 2
$left = Get-ListenerPids 8000
if ($left -and $left.Count -gt 0) {
    Write-Host "Port 8000 still in use (PID $($left -join ', '))." -ForegroundColor Red
    Write-Host "Open Task Manager -> Details -> end python.exe on port 8000, or reboot, then run .\run_backend.ps1"
    exit 1
}

Write-Host "Port 8000 cleared. Restart with: .\run_backend.ps1" -ForegroundColor Green
