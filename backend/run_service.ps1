# Runs the Edge Predictions app continuously, restarting it if it ever
# exits (crash, external kill, etc). Meant to be launched by the
# "EdgePredictionsBTCScalp" Scheduled Task, not run directly, though running
# it directly in a terminal works too.
#
# Paper trading only — this app never places a real order (see
# app/strategies/btc_15min_scalp.py and PLAN.md's Milestone 8 gating notes).

$ErrorActionPreference = "Continue"
$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $backendDir

$logDir = Join-Path $backendDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

while ($true) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $logFile = Join-Path $logDir "app_$timestamp.log"
    "$(Get-Date -Format o): starting uvicorn, logging to $logFile" | Out-File -FilePath (Join-Path $logDir "service.log") -Append -Encoding utf8

    & "$backendDir\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *>&1 |
        Tee-Object -FilePath $logFile

    "$(Get-Date -Format o): uvicorn exited, restarting in 10s" | Out-File -FilePath (Join-Path $logDir "service.log") -Append -Encoding utf8
    Start-Sleep -Seconds 10
}
