# scripts/pipeline.ps1 — Full EMBER pipeline
# Usage: powershell -ExecutionPolicy Bypass -File scripts/pipeline.ps1
# Runs: data collection → scoring → outcome resolution → auto-tune → briefing

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $ProjectRoot

# Activate venv if it exists
$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    . $VenvActivate
}

$env:PYTHONPATH = "."
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "[$timestamp] === EMBER Pipeline Start ===" -ForegroundColor Cyan

# Step 1: Run one alert cycle
Write-Host "[$timestamp] Step 1: Alert cycle..." -ForegroundColor Yellow
python app.py --once
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: app.py exited with code $LASTEXITCODE" -ForegroundColor Red
}

# Step 2: Generate scorecard
Write-Host "[$timestamp] Step 2: Scorecard..." -ForegroundColor Yellow
python scripts/pid-129/generate_scorecard.py

# Step 3: Generate dashboard
Write-Host "[$timestamp] Step 3: Dashboard..." -ForegroundColor Yellow
python scripts/pid-129/generate_dashboard.py

# Step 4: Auto-tune thresholds
Write-Host "[$timestamp] Step 4: Auto-tune..." -ForegroundColor Yellow
python tools/auto_tune.py

# Step 5: Generate morning briefing
Write-Host "[$timestamp] Step 5: Morning briefing..." -ForegroundColor Yellow
python scripts/morning_briefing.py

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$timestamp] === EMBER Pipeline Complete ===" -ForegroundColor Green
