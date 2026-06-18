# Apply laptop-only environment. EC2 uses /opt/legalease/.env via deploy - not this file.
function Set-LegalEaseLocalDevEnv {
    param(
        [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent)
    )

    $env:LEGALEEASE_LOCAL_DEV = "1"
    $env:SAAS_PRODUCTION = "0"
    $env:SAAS_PRODUCTION_STRICT = "0"
    if (-not $env:CORS_ALLOW_LOCALHOST_REGEX) { $env:CORS_ALLOW_LOCALHOST_REGEX = "1" }

    $localFile = Join-Path $ProjectRoot ".env.local"
    if (Test-Path $localFile) {
        Get-Content $localFile | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#")) { return }
            if ($line -match '^\s*([^#=]+)=(.*)$') {
                $key = $Matches[1].Trim()
                $val = $Matches[2].Trim()
                if (
                    ($val.StartsWith('"') -and $val.EndsWith('"')) -or
                    ($val.StartsWith("'") -and $val.EndsWith("'"))
                ) {
                    $val = $val.Substring(1, $val.Length - 2)
                }
                Set-Item -Path "env:$key" -Value $val
            }
        }
        Write-Host '  Loaded .env.local (laptop overrides)' -ForegroundColor DarkGray
    } else {
        Write-Host '  Tip: run scripts\setup_local_env.ps1 to create .env.local' -ForegroundColor DarkYellow
    }

    if ($env:SAAS_USE_POSTGRES_LEGACY -ne "1") {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }

    Write-Host '  Local dev mode (SAAS_PRODUCTION=0)' -ForegroundColor DarkGray
    if ($env:LLM_BACKEND) {
        Write-Host ('  LLM_BACKEND = ' + $env:LLM_BACKEND) -ForegroundColor DarkGray
    }

    if (-not $env:NEXT_PUBLIC_API_URL) {
        $env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8000'
    } else {
        $env:NEXT_PUBLIC_API_URL = ($env:NEXT_PUBLIC_API_URL -replace '/api$', '').TrimEnd('/')
    }
    if (-not $env:NEXT_PUBLIC_APP_URL) {
        $env:NEXT_PUBLIC_APP_URL = 'http://localhost:3000'
    }
}
