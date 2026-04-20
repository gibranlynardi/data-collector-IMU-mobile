param(
    [string]$SourceDir = "",
    [string]$OutputDir = "",
    [int]$RetentionDays = 14
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
Import-DotEnv -Path (Join-Path $repoRoot ".env")

if (-not $SourceDir) {
    $SourceDir = if ($env:BACKUP_SOURCE_DIR) { $env:BACKUP_SOURCE_DIR } else { "./data" }
}
if (-not $OutputDir) {
    $OutputDir = if ($env:BACKUP_OUTPUT_DIR) { $env:BACKUP_OUTPUT_DIR } else { "./backups" }
}
if ($env:BACKUP_RETENTION_DAYS) {
    $RetentionDays = [int]$env:BACKUP_RETENTION_DAYS
}

$resolvedSource = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $SourceDir))
$resolvedOutput = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDir))

if (-not (Test-Path -Path $resolvedSource)) {
    throw "Source directory tidak ditemukan: $resolvedSource"
}

New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archiveName = "imu_data_backup_$timestamp.zip"
$archivePath = Join-Path $resolvedOutput $archiveName
$stageDir = Join-Path $resolvedOutput (".stage_" + $timestamp)

Write-Host "Membuat backup dari $resolvedSource"
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

try {
    $sessionsDir = Join-Path $resolvedSource "sessions"
    if (Test-Path -Path $sessionsDir) {
        Copy-Item -Path $sessionsDir -Destination (Join-Path $stageDir "sessions") -Recurse -Force
    }

    $metadataDb = Join-Path $resolvedSource "metadata.db"
    if (Test-Path -Path $metadataDb) {
        try {
            Copy-Item -Path $metadataDb -Destination (Join-Path $stageDir "metadata.db") -Force
        } catch {
            Write-Warning "metadata.db sedang dipakai proses lain, backup dilanjutkan tanpa file ini."
        }
    }

    $hasStageContent = (Get-ChildItem -Path $stageDir -Force | Measure-Object).Count -gt 0
    if (-not $hasStageContent) {
        throw "Tidak ada konten yang bisa dibackup dari $resolvedSource"
    }

    Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $archivePath -CompressionLevel Optimal
}
finally {
    if (Test-Path -Path $stageDir) {
        Remove-Item -Path $stageDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$cutoff = (Get-Date).AddDays(-1 * [Math]::Max(0, $RetentionDays))
Get-ChildItem -Path $resolvedOutput -Filter "imu_data_backup_*.zip" -File |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    Remove-Item -Force

Write-Host "Backup selesai: $archivePath"
