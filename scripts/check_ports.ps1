param(
    [int[]]$Ports = @(5173, 8000, 5432, 6379, 6333, 8766, 8767)
)

$busy = @()

foreach ($port in $Ports) {
    $listeners = netstat -ano | Select-String ":$port\s" | Select-String "LISTENING"
    if (-not $listeners) {
        continue
    }

    foreach ($line in $listeners) {
        $parts = ($line -replace '\s+', ' ').Trim().Split(' ')
        $pid = $parts[-1]
        $owner = "PID $pid"
        try {
            $proc = Get-Process -Id $pid -ErrorAction Stop
            $owner = "$($proc.ProcessName) (PID $pid)"
        } catch {
            # process may have exited
        }
        $busy += [pscustomobject]@{
            Port = $port
            Owner = $owner
            Line = $line.ToString().Trim()
        }
    }
}

if (-not $busy) {
    Write-Host "Ports are free: $($Ports -join ', ')"
    exit 0
}

Write-Host "Busy ports:"
$busy | Sort-Object Port -Unique | Format-Table -AutoSize

Write-Host ""
Write-Host "Docker containers using these ports:"
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}" 2>$null

exit 1
