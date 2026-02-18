# run.ps1 - Windows Bootstrap for BTC Alerts MVP
# Mirror of run.sh

$VENV_DIR = ".venv"
$PYTHON = "python"

if (-not (Test-Path $VENV_DIR)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    & $PYTHON -m venv $VENV_DIR
}

$ACTIVATE_SCRIPT = Join-Path $VENV_DIR "Scripts" "Activate.ps1"
if (-not (Test-Path $ACTIVATE_SCRIPT)) {
    Write-Host "Virtual environment script not found at $ACTIVATE_SCRIPT" -ForegroundColor Red
    exit 1
}

. $ACTIVATE_SCRIPT

$INSTALL = $false
$APP_ARGS = @()

foreach ($arg in $args) {
    if ($arg -eq "--install") {
        $INSTALL = $true
    } else {
        $APP_ARGS += $arg
    }
}

$REQ_FILE = "requirements.txt"
$HASH_FILE = ".venv/.requirements.sha256"

if (Test-Path $REQ_FILE) {
    $currentHash = (Get-FileHash $REQ_FILE -Algorithm SHA256).Hash
    $oldHash = ""
    if (Test-Path $HASH_FILE) {
        $oldHash = Get-Content $HASH_FILE
    }

    if ($INSTALL -or ($currentHash -ne $oldHash)) {
        Write-Host "Installing requirements..." -ForegroundColor Cyan
        pip install -r $REQ_FILE
        $currentHash | Out-File -FilePath $HASH_FILE -Encoding ascii
    }
}

if ($args -contains "--loop") {
    Write-Host ">>> STARTING BTC ALERTS (CONTINUOUS MODE) <<<" -ForegroundColor Green
    Write-Host ">>> To turn OFF: Press Ctrl+C <<<" -ForegroundColor Yellow
    python app.py
} else {
    Write-Host ">>> RUNNING BTC ALERTS (SINGLE SNAPSHOT) <<<" -ForegroundColor Green
    python app.py --once
}
