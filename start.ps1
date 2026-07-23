# start.ps1 — all-in-one launcher (backend + frontend), Windows-native (no `make` required).
# Assumes env + build already exist (venv, .env, node_modules). Warns (does not hard-fail)
# if something's missing, then launches backend + frontend in separate windows.
#
# PORTABILITY: repo root is derived from this script's own location — never hardcode a
# path or an IP, so any peer can `git pull` and run this unchanged on their laptop.
$root = $PSScriptRoot
$port = 8000

Write-Host "=== IMU Telemetry — Start ===" -ForegroundColor Cyan

# 1. Banner + IP (same logic as ops/ip.ps1)
& (Join-Path $root 'ops\ip.ps1')
Write-Host ""

# 2. Preflight (warn, don't hard-fail)
$venvPy = Join-Path $root 'master_backend\venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host "WARNING: master_backend\venv not found — run 'make install-backend' or create a venv. Falling back to 'python' on PATH." -ForegroundColor Yellow
}
$envFile = Join-Path $root 'master_backend\.env'
if (-not (Test-Path $envFile)) {
    Write-Host "WARNING: master_backend\.env not found — copy .env.example to .env first." -ForegroundColor Yellow
}
$nodeModules = Join-Path $root 'master_frontend\node_modules'
if (-not (Test-Path $nodeModules)) {
    Write-Host "WARNING: master_frontend\node_modules not found — run 'npm install' in master_frontend first." -ForegroundColor Yellow
}
$buildId = Join-Path $root 'master_frontend\.next\BUILD_ID'
$hasBuild = Test-Path $buildId
if (-not $hasBuild) {
    Write-Host "No production build found — starting dev server instead. Run 'npm run build' in master_frontend for prod." -ForegroundColor Yellow
}

$already = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($already) {
    Write-Host "WARNING: port $port already LISTENING — backend appears to be running already. Skipping backend start." -ForegroundColor Yellow
} else {
    # 3. Start backend in a new window
    $py = if (Test-Path $venvPy) { $venvPy } else { 'python' }
    Write-Host "Starting backend ($py master_backend/run.py) ..." -ForegroundColor Cyan
    Start-Process -FilePath $py -ArgumentList 'master_backend/run.py' -WorkingDirectory $root
}

# 4. Start frontend in a new window
$fe = Join-Path $root 'master_frontend'
$script = if ($hasBuild) { 'start' } else { 'dev' }   # prod if built, else dev
Write-Host "Starting frontend (npm run $script) ..." -ForegroundColor Cyan
Start-Process -FilePath 'npm.cmd' -ArgumentList 'run', $script -WorkingDirectory $fe

# 5. Open the dashboard
Start-Sleep -Seconds 2
Start-Process 'http://localhost:3000'

Write-Host ""
Write-Host "Backend + Frontend launched in separate windows. Close those windows (or run 'ops\stop.ps1') to stop." -ForegroundColor Green
