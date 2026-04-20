param(
    [ValidateSet("native", "docker")]
    [string]$Mode = "native"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

if ($Mode -eq "docker") {
    Push-Location $repoRoot
    try {
        Write-Host "Starting backend + dashboard via Docker Compose..."
        docker compose up -d --build
        Write-Host "Dashboard: http://127.0.0.1:3000"
        Write-Host "Backend:   http://127.0.0.1:8000"
    } finally {
        Pop-Location
    }
    return
}

$backendScript = Join-Path $PSScriptRoot "start_backend.ps1"
$dashboardScript = Join-Path $PSScriptRoot "start_dashboard.ps1"

Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", $backendScript)
Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", $dashboardScript)

Write-Host "Started backend and dashboard in two separate terminals."
Write-Host "Dashboard: http://127.0.0.1:3000"
Write-Host "Backend:   http://127.0.0.1:8000"
