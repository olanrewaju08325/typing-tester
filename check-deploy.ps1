Write-Host "🔍 Checking Internet & Deployment Connectivity..." -ForegroundColor Cyan

# List of important hosts
$hosts = @(
    "github.com",
    "render.com",
    "fly.io",
    "pypi.org"
)

foreach ($h in $hosts) {
    Write-Host "-------------------------------------------"
    Write-Host "Testing: $h" -ForegroundColor Yellow
    try {
        $ping = Test-Connection -Count 1 -Quiet $h
        if ($ping) {
            Write-Host "✅ Ping OK"
        } else {
            Write-Host "⚠️ Ping failed"
        }

        $response = Invoke-WebRequest -Uri "https://$h" -UseBasicParsing -TimeoutSec 10
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ HTTPS OK (Status 200)"
        } else {
            Write-Host "⚠️ HTTPS returned status $($response.StatusCode)"
        }
    } catch {
        Write-Host "❌ Connection error: $($_.Exception.Message)"
    }
}

Write-Host "-------------------------------------------"
Write-Host "✅ Check completed!" -ForegroundColor Green
