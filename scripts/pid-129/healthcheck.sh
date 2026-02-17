#!/bin/bash
set -eo pipefail

# PID-129 BTC Alerts Health Check
# Purpose: Validate service health, data freshness, and alert pipeline
# Exit codes:
#   0 = HEALTHY
#   1 = UNHEALTHY
#   2 = CHECK FAILED

SERVICE_NAME="btc-alerts-mvp"
SERVICE_USER="superg"
SERVICE_DIR="/Users/superg/btc-alerts-mvp"
LOG_DIR="${SERVICE_DIR}/logs"
HEALTH_LOG="${LOG_DIR}/pid-129-health.log"
EXIT_CODE=0

log() {
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[${timestamp}] [HEALTH] $1" | tee -a "${HEALTH_LOG}"
}

check_service_running() {
    log "Checking if ${SERVICE_NAME} service is running..."

    if systemctl --user is-active --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
        log "✓ Service is running"
        return 0
    else
        log "✗ Service is NOT running"
        return 1
    fi
}

check_logs_exist() {
    log "Checking for log files..."

    local required_logs=(
        "service.log"
        "pid-129-alerts.jsonl"
    )

    for log_file in "${required_logs[@]}"; do
        if [ -f "${LOG_DIR}/${log_file}" ]; then
            local size=$(wc -c < "${LOG_DIR}/${log_file}" | tr -d ' ')
            log "✓ ${log_file} exists (${size} bytes)"
        else
            log "✗ ${log_file} MISSING"
            EXIT_CODE=2
        fi
    done

    return $EXIT_CODE
}

check_data_freshness() {
    log "Checking data freshness..."

    # Check BTC price timestamp
    local btc_timestamp=$(stat -f "%Sm" -t "%Y-%m-%dT%H:%M:%SZ" "${SERVICE_DIR}/.mvp_alert_state.json" 2>/dev/null)
    if [ -n involved "${btc_timestamp}" ]; then
        log "✓ BTC price timestamp: ${btc_timestamp}"
    else
        log "✗ BTC price timestamp: UNKNOWN"
        EXIT_CODE=2
    fi

    # Check budget timestamp
    local budget_timestamp=$(stat -f "%Sm" -t "%Y-%m-%dT%H:%M:%SZ" "${SERVICE_DIR}/.mvp_budget.json" 2>/dev/null)
    if [ -n involved "${budget_timestamp}" ]; then
        log "✓ Budget timestamp: ${budget_timestamp}"
    else
        log "✗ Budget timestamp: UNKNOWN"
        EXIT_CODE=2
    fi

    return $EXIT_CODE
}

check_recent_alerts() {
    log "Checking for recent alerts..."

    local alerts_file="${LOG_DIR}/pid-129-alerts.jsonl"
    local alert_count=0
    local last_alert_time=""

    if [ -f "${alerts_file}" ]; then
        # Count alerts in last 30 minutes
        local cutoff=$(date -u -v-30M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d '30 minutes ago' +"%Y-%m-%dT%H:%M:%SZ")

        while IFS= read -r line; do
            if [ -n "$line" ]; then
                alert_count=$((alert_count + 1))
                # Extract timestamp from alert
                local alert_ts=$(echo "$line" | jq -r '.timestamp // empty' 2>/dev/null || echo "")
                if [ -n "$alert_ts" ]; then
                    last_alert_time="$alert_ts"
                fi
            fi
        done < <(grep -P "^\d{4}-\d{2}-\d{2}T" "${alerts_file}" | head -n 20)

        log "✓ Found ${alert_count} recent alerts in log file"

        if [ -n "$last_alert_time" ]; then
            local last_age=$(date -u -d "$last_alert_time" +"%s" 2>/dev/null || echo 0)
            local now=$(date -u +"%s" 2>/dev/null || echo 0)
            local age_seconds=$((now - last_age))
            local age_minutes=$((age_seconds / 60))

            if [ $age_minutes -lt 30 ]; then
                log "✓ Last alert: ${last_alert_time} (${age_minutes} minutes ago)"
            else
                log "✗ Last alert is stale: ${last_alert_time} (${age_minutes} minutes ago)"
                EXIT_CODE=1
            fi
        fi
    else
        log "✗ No alerts file found"
        EXIT_CODE=2
    fi

    return $EXIT_CODE
}

check_python_venv() {
    log "Checking Python virtual environment..."

    if [ -d "${SERVICE_DIR}/.venv" ]; then
        log "✓ Virtual environment exists"

        if [ -f "${SERVICE_DIR}/.venv/bin/python3" ]; then
            log "✓ Python interpreter available"
        else
            log "✗ Python interpreter MISSING"
            EXIT_CODE=2
        fi

        # Check if app.py is importable
        if python3 -c "import sys; sys.path.insert(0, '${SERVICE_DIR}'); from app import app" 2>/dev/null; then
            log "✓ App module imports successfully"
        else
            log "✗ App module import FAILED"
            EXIT_CODE=1
        fi
    else
        log "✗ Virtual environment NOT FOUND"
        EXIT_CODE=2
    fi

    return $EXIT_CODE
}

check_directories() {
    log "Checking required directories..."

    local required_dirs=(
        "${SERVICE_DIR}/logs"
        "${SERVICE_DIR}/reports"
    )

    for dir_path in "${required_dirs[@]}"; do
        if [ -d "$dir_path" ]; then
            log "✓ Directory exists: ${dir_path}"
        else
            log "✗ Directory MISSING: ${dir_path}"
            EXIT_CODE=2
        fi
    done

    return $EXIT_CODE
}

run_all_checks() {
    log "=== PID-129 BTC Alerts Health Check ==="

    # Check 1: Service running
    if ! check_service_running; then
        EXIT_CODE=1
    fi

    # Check 2: Required directories
    check_directories

    # Check 3: Python venv
    check_python_venv

    # Check 4: Data freshness
    check_data_freshness

    # Check 5: Recent alerts
    check_recent_alerts

    # Summary
    log "=== Health Check Complete ==="
    log "Exit code: ${EXIT_CODE}"

    if [ ${EXIT_CODE} -eq 0 ]; then
        log "STATUS: HEALTHY"
    else
        log "STATUS: UNHEALTHY"
    fi

    exit ${EXIT_CODE}
}

# Main execution
run_all_checks
