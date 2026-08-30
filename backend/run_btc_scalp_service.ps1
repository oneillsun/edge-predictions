# Runs the standalone BTC 15-min scalp script continuously, restarting it if
# it ever exits (crash, external kill, etc). Meant to be launched by the
# "EdgePredictionsBTCScalp" Scheduled Task, not run directly, though running
# it directly in a terminal works too.
#
# Isolated from the rest of the app on purpose — see
# scripts/run_btc_15min_scalp.py. Paper trading only, never places a real
# order.

$ErrorActionPreference = "Continue"
$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $backendDir

$logDir = Join-Path $backendDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

while ($true) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $logFile = Join-Path $logDir "btc_scalp_$timestamp.log"
    "$(Get-Date -Format o): starting run_btc_15min_scalp.py, logging to $logFile" | Out-File -FilePath (Join-Path $logDir "btc_scalp_service.log") -Append -Encoding utf8

    & "$backendDir\.venv\Scripts\python.exe" -u scripts\run_btc_15min_scalp.py *>&1 |
        Tee-Object -FilePath $logFile

    "$(Get-Date -Format o): script exited, restarting in 10s" | Out-File -FilePath (Join-Path $logDir "btc_scalp_service.log") -Append -Encoding utf8
    Start-Sleep -Seconds 10
}
