param(
    [string]$ApiBaseUrl = "",
    [string]$WsBaseUrl = "",
    [ValidateSet("dev", "prod")]
    [string]$Mode = "dev",
    [int]$Port = 3000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -Path $Path)) {
        return
    }

    Get-Content -Path $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) {
            return
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"')
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value)
        }
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$dashboardRoot = Join-Path $repoRoot "web-dashboard"

Import-DotEnv -Path (Join-Path $repoRoot ".env")

$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
if (-not $ApiBaseUrl) {
    $ApiBaseUrl = "http://127.0.0.1:$backendPort"
}
if (-not $WsBaseUrl) {
    $WsBaseUrl = "ws://127.0.0.1:$backendPort"
}

$env:NEXT_PUBLIC_API_BASE_URL = $ApiBaseUrl
$env:NEXT_PUBLIC_WS_BASE_URL = $WsBaseUrl

Push-Location $dashboardRoot
try {
    if ($Mode -eq "prod") {
        Write-Host "Building dashboard for production..."
        npm run build
        Write-Host "Starting dashboard (prod) at http://127.0.0.1:$Port"
        npm run start -- -p $Port
    } else {
        Write-Host "Starting dashboard (dev) at http://127.0.0.1:$Port"
        npm run dev -- -p $Port
    }
} finally {
    Pop-Location
}
