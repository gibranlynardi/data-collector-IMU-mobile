param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$Reload
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
$backendRoot = Join-Path $repoRoot "backend"

Import-DotEnv -Path (Join-Path $repoRoot ".env")

if (-not $env:DATA_ROOT) {
    $env:DATA_ROOT = Join-Path $repoRoot "data"
}
if (-not $env:BACKEND_HOST) {
    $env:BACKEND_HOST = $BindHost
}
if (-not $env:BACKEND_REST_PORT) {
    $env:BACKEND_REST_PORT = [string]$Port
}
if (-not $env:BACKEND_WS_PORT) {
    $env:BACKEND_WS_PORT = $env:BACKEND_REST_PORT
}

$pythonLocal = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path -Path $pythonLocal) {
    $pythonExe = $pythonLocal
} else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        throw "Python tidak ditemukan. Buat venv di .venv atau install Python global."
    }
    $pythonExe = $pythonCmd.Source
}

if ($env:DATABASE_URL -and $env:DATABASE_URL.StartsWith("postgresql")) {
    & $pythonExe -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('psycopg2') else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "DATABASE_URL PostgreSQL terdeteksi, tapi psycopg2 belum tersedia. Fallback ke SQLite lokal."
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
}

Push-Location $backendRoot
try {
    $args = @("-m", "uvicorn", "app.main:app", "--host", $env:BACKEND_HOST, "--port", $env:BACKEND_REST_PORT)
    if ($Reload) {
        $args += "--reload"
    }

    Write-Host "Starting backend at http://$($env:BACKEND_HOST):$($env:BACKEND_REST_PORT)"
    & $pythonExe @args
} finally {
    Pop-Location
}
