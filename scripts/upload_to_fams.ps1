param(
    [Parameter(Mandatory = $true)]
    [string]$SessionId,

    [Parameter(Mandatory = $true)]
    [string]$LocalFile,

    [Parameter(Mandatory = $true)]
    [string]$FamsHost,

    [Parameter(Mandatory = $true)]
    [string]$FamsUser,

    [Parameter(Mandatory = $true)]
    [string]$RemotePath,

    [string]$SshKeyPath = $env:FAMS_SSH_KEY_PATH,
    [string]$RsyncExecutable = $(if ($env:RSYNC_EXECUTABLE) { $env:RSYNC_EXECUTABLE } else { "rsync" }),
    [string]$SshExecutable = $(if ($env:SSH_EXECUTABLE) { $env:SSH_EXECUTABLE } else { "ssh" })
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $LocalFile)) {
    throw "Local file not found: $LocalFile"
}

$localChecksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $LocalFile).Hash.ToLowerInvariant()
Write-Host "[phase12] Local checksum: $localChecksum"

$sshTarget = "$FamsUser@$FamsHost"
$remoteDir = [System.IO.Path]::GetDirectoryName($RemotePath.Replace('/', '\')).Replace('\\', '/')

$sshArgs = @()
if ($SshKeyPath) {
    $sshArgs += "-i"
    $sshArgs += $SshKeyPath
}

$sshCommand = "$SshExecutable $($sshArgs -join ' ')"
$rsyncArgs = @(
    "-avzP",
    "--partial",
    "--append-verify",
    "-e", $sshCommand,
    $LocalFile,
    "$sshTarget:$RemotePath"
)

Write-Host "[phase12] Upload with rsync (resume enabled)..."
& $RsyncExecutable @rsyncArgs
if ($LASTEXITCODE -ne 0) {
    throw "rsync upload failed with exit code $LASTEXITCODE"
}

$mkDirCmd = "mkdir -p '$remoteDir'"
$remoteChecksumCmd = "sha256sum '$RemotePath' | awk '{print `$1}'"

& $SshExecutable @sshArgs $sshTarget $mkDirCmd | Out-Null
$remoteChecksum = (& $SshExecutable @sshArgs $sshTarget $remoteChecksumCmd).Trim().ToLowerInvariant()

if ($remoteChecksum -ne $localChecksum) {
    throw "Checksum mismatch. local=$localChecksum remote=$remoteChecksum"
}

Write-Host "[phase12] Upload OK for session $SessionId"
Write-Host "[phase12] Remote path: $RemotePath"
Write-Host "[phase12] Checksum verified: $localChecksum"
