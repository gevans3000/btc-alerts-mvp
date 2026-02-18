# healthcheck.ps1 - Windows Health Check for BTC Alerts MVP (PID-129)
# Mirror of healthcheck.sh logic for Windows

$ROOT = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$LOG_DIR = Join-Path $ROOT "logs"
$HEALTH_LOG = Join-Path $LOG_DIR "pid-129-health.log"
$EXIT_CODE = 0

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Write-HealthLog {
    param([string]$Message)
    $ts = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
    $logLine = "[$ts] [HEALTH] $Message"
    Write-Host $logLine
    $logLine | Out-File -FilePath $HEALTH_LOG -Append -Encoding utf8
}

function Test-ServiceRunning {
    Write-HealthLog "Checking for running python processes named app.py..."
    # Using Get-Process is simpler and more cross-compatible on Windows
    $procs = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*app.py*" }
    if ($procs) {
        Write-HealthLog "[OK] App process detected (PIDs: $($procs.Id -join ', '))"
        return $true
    }
    else {
        Write-HealthLog "[FAIL] No app.py process detected."
        return $false
    }
}

function Test-LogsExist {
    Write-HealthLog "Checking for log files..."
    $requiredLogs = @("pid-129-alerts.jsonl")
    foreach ($log in $requiredLogs) {
        $path = Join-Path $LOG_DIR $log
        if (Test-Path $path) {
            $size = (Get-Item $path).Length
            Write-HealthLog "[OK] $log exists ($size bytes)"
        }
        else {
            Write-HealthLog "[FAIL] $log MISSING"
            $script:EXIT_CODE = 2
        }
    }
}

function Test-PythonVenv {
    Write-HealthLog "Checking Python virtual environment..."
    $venv = Join-Path $ROOT ".venv"
    if (Test-Path $venv) {
        Write-HealthLog "[OK] Virtual environment exists"
        $pythonPath = Join-Path $venv "Scripts\python.exe"
        if (Test-Path $pythonPath) {
            Write-HealthLog "[OK] Python interpreter available"
        }
        else {
            Write-HealthLog "[FAIL] Python interpreter MISSING at $pythonPath"
            $script:EXIT_CODE = 2
        }
    }
    else {
        Write-HealthLog "[FAIL] Virtual environment NOT FOUND"
        $script:EXIT_CODE = 2
    }
}

function Get-DataFreshness {
    Write-HealthLog "Checking data freshness..."
    $stateFile = Join-Path $ROOT ".mvp_alert_state.json"
    if (Test-Path $stateFile) {
        $lastWrite = (Get-Item $stateFile).LastWriteTimeUtc
        $age = [DateTime]::UtcNow - $lastWrite
        Write-HealthLog "[OK] State file timestamp: $($lastWrite.ToString('yyyy-MM-dd HH:mm:ss')) ($($age.TotalMinutes.ToString('F1')) min old)"
        if ($age.TotalMinutes -gt 60) {
            Write-HealthLog "[WARN] State file is older than 60 minutes"
        }
    }
    else {
        Write-HealthLog "[FAIL] State file NOT FOUND"
        $script:EXIT_CODE = 2
    }
}

Write-HealthLog "=== PID-129 BTC Alerts Health Check (Windows) ==="
Test-ServiceRunning | Out-Null
Test-LogsExist
Test-PythonVenv
Get-DataFreshness

Write-HealthLog "=== Health Check Complete ==="
Write-HealthLog "Exit code: $EXIT_CODE"

if ($EXIT_CODE -eq 0) {
    Write-HealthLog "STATUS: HEALTHY"
}
else {
    Write-HealthLog "STATUS: UNHEALTHY"
}

exit $EXIT_CODE
