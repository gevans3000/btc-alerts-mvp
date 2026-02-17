#!/usr/bin/env python3
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from collectors.base import BudgetManager
from collectors.price import fetch_btc_price

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("outcome_tracker")

MAX_DURATION = {
    "5m": 4 * 3600,   # 4 hours
    "15m": 12 * 3600, # 12 hours
    "1h": 48 * 3600   # 48 hours
}

def resolve_outcomes(alerts_path: str = "logs/pid-129-alerts.jsonl"):
    path = Path(alerts_path)
    if not path.exists():
        logger.warning(f"No alerts file found at {alerts_path}")
        return

    # Load all alerts
    alerts = []
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                alerts.append(json.loads(line))

    unresolved = [a for a in alerts if not a.get("resolved")]
    if not unresolved:
        logger.info("No unresolved alerts to track.")
        return

    logger.info(f"Checking outcomes for {len(unresolved)} unresolved alerts...")
    
    # Fetch current price
    bm = BudgetManager(".mvp_budget.json")
    px_snapshot = fetch_btc_price(bm)
    if not px_snapshot.healthy:
        logger.error("Failed to fetch current price for outcome tracking.")
        return
    
    current_price = px_snapshot.price
    now = datetime.now(timezone.utc)
    
    updated = False
    for alert in alerts:
        if alert.get("resolved"):
            continue
        
        # Calculate time elapsed
        try:
            start_time = datetime.fromisoformat(alert["timestamp"])
            elapsed = (now - start_time).total_seconds()
        except Exception as e:
            logger.error(f"Error parsing timestamp for alert {alert.get('alert_id')}: {e}")
            continue

        symbol = alert.get("symbol")
        if symbol != "BTC": # Only BTC for now
            continue

        direction = alert.get("direction")
        entry = alert.get("entry_price")
        tp1 = alert.get("tp1")
        tp2 = alert.get("tp2")
        sl = alert.get("invalidation")
        tf = alert.get("timeframe")
        
        resolved = False
        outcome = None
        outcome_price = current_price
        r_multiple = 0.0

        # Logic for resolution
        risk = abs(entry - sl) if abs(entry - sl) > 0 else 1.0
        
        if direction == "LONG":
            if current_price >= tp2:
                resolved = True
                outcome = "WIN_TP2"
                r_multiple = abs(tp2 - entry) / risk
            elif current_price >= tp1:
                # We don't necessarily resolve on TP1 if we want to wait for TP2 or SL
                # But for the MVP, let's mark as resolved on TP1 to simplify
                resolved = True
                outcome = "WIN_TP1"
                r_multiple = abs(tp1 - entry) / risk
            elif current_price <= sl:
                resolved = True
                outcome = "LOSS"
                r_multiple = -1.0
        elif direction == "SHORT":
            if current_price <= tp2:
                resolved = True
                outcome = "WIN_TP2"
                r_multiple = abs(entry - tp2) / risk
            elif current_price <= tp1:
                resolved = True
                outcome = "WIN_TP1"
                r_multiple = abs(entry - tp1) / risk
            elif current_price >= sl:
                resolved = True
                outcome = "LOSS"
                r_multiple = -1.0
        
        # Check timeout
        if not resolved and elapsed > MAX_DURATION.get(tf, 24 * 3600):
            resolved = True
            outcome = "TIMEOUT"
            r_multiple = (current_price - entry) / risk if direction == "LONG" else (entry - current_price) / risk
            logger.info(f"Alert {alert['alert_id']} timed out after {elapsed/3600:.1f}h")

        if resolved:
            alert["resolved"] = True
            alert["outcome"] = outcome
            alert["outcome_timestamp"] = now.isoformat()
            alert["outcome_price"] = outcome_price
            alert["r_multiple"] = round(r_multiple, 2)
            updated = True
            logger.info(f"Resolved alert {alert['alert_id']}: {outcome} ({r_multiple:.2f}R)")

    if updated:
        # Write back all alerts
        with open(path, "w") as f:
            for alert in alerts:
                f.write(json.dumps(alert) + "\n")
        logger.info("Updated alerts file with resolved outcomes.")

if __name__ == "__main__":
    resolve_outcomes()
