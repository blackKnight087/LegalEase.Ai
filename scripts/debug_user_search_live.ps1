# Hit live backend search (requires token) — run from project root
$base = "http://127.0.0.1:8000"
try {
    $live = Invoke-RestMethod -Uri "$base/api/v1/health/live" -TimeoutSec 3
    Write-Host "Backend live: OK"
} catch {
    Write-Host "Backend not reachable at $base"
    exit 1
}

$body = @{ username = "yus"; password = "wrong" } | ConvertTo-Json
Write-Host "Try login as yus (will fail without password) — use your credentials in browser DevTools instead."
Write-Host "Open Firm Chat, search, then Network tab: GET /api/v1/collaboration/users/search?q=..."
