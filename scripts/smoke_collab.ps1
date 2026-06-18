# Smoke-test Collaboration Hub API (requires backend on :8000)
$base = "http://127.0.0.1:8000/api/v1"
$health = Invoke-RestMethod "$base/health/live" -TimeoutSec 5
Write-Host "Health:" $health.status
$loginBody = '{"username":"admin","password":"admin"}'
try {
  $auth = Invoke-RestMethod -Method POST -Uri "$base/auth/login" -Body $loginBody -ContentType "application/json" -TimeoutSec 10
  $headers = @{ Authorization = "Bearer $($auth.token)" }
  $perms = Invoke-RestMethod -Uri "$base/collaboration/permissions" -Headers $headers
  Write-Host "Collab view permission:" $perms.permissions.view
  $rooms = Invoke-RestMethod -Uri "$base/collaboration/rooms" -Headers $headers
  Write-Host "Rooms count:" $rooms.rooms.Count
  Write-Host "OK - Collaboration Hub API reachable"
} catch {
  Write-Host "Auth or collab check failed:" $_.Exception.Message
  Write-Host "Use pytest tests/test_collab_api.py for offline verification"
}
