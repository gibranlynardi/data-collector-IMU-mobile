# ops/stop.ps1 — stop backend (:8000) and frontend (:3000) by killing whatever owns the port.
foreach ($p in 8000, 3000) {
  $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Write-Host "Stopped backend (:8000) and frontend (:3000) if they were running."
