# ops/ip.ps1 — show backend connection config WITHOUT stopping the server.
# Run anytime in a second terminal. Read-only: does not touch the running backend.
$port = 8000
Write-Host "=== IMU Backend Connection Doctor ===" -ForegroundColor Cyan

$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' }
foreach ($ip in $ips) {
    $lan = $ip.IPAddress -match '^(192\.168|10\.|172\.(1[6-9]|2[0-9]|3[01]))\.'
    $tag = if ($lan) { '  <-- use this on the phones' } else { '' }
    Write-Host ("  {0}  ({1}){2}" -f $ip.IPAddress, $ip.InterfaceAlias, $tag)
}

$listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listening) { Write-Host "Port $port : LISTENING (backend is up)" -ForegroundColor Green }
else { Write-Host "Port $port : NOT listening — start the backend first" -ForegroundColor Red }

$lanIp = ($ips | Where-Object { $_.IPAddress -match '^(192\.168|10\.|172\.(1[6-9]|2[0-9]|3[01]))\.' } |
    Select-Object -First 1).IPAddress
if ($lanIp) {
    Write-Host ""
    Write-Host "Type into phone / dashboard:  $lanIp" -ForegroundColor Yellow
    Write-Host "  ws://$lanIp`:$port/ws/control"
    Write-Host "  ws://$lanIp`:$port/ws/telemetry"
    try {
        $h = Invoke-RestMethod "http://$lanIp`:$port/health" -TimeoutSec 2
        Write-Host ("Health OK — state=$($h.session_state) devices=$($h.online_devices)") -ForegroundColor Green
    } catch {
        Write-Host "Health probe failed — check Windows Firewall inbound rule for port $port on the Wi-Fi (Private) network." -ForegroundColor Red
    }
}
