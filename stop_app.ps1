# Stop Streamlit LegalEase (port 8501)
$ErrorActionPreference = "SilentlyContinue"

$killed = 0
try {
    Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            if ($_ -gt 4) {
                Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
                $killed++
            }
        }
} catch { }

Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'streamlit\s+run\s+app\.py' } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $killed++
    }

Write-Host "Stopped $killed Streamlit-related process(es). Port 8501 should be free." -ForegroundColor Yellow
