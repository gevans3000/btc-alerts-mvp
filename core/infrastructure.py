import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import httpx
from core.logger import logger
from config import COOLDOWN_SECONDS
from engine import AlertScore

class PersistentLogger:
    """Logs alerts to a JSONL file for outcome tracking."""
    def __init__(self, path: str = "logs/pid-129-alerts.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"PersistentLogger initialized at {self.path}")

    def log_alert(self, score: AlertScore, price: float):
        """Records a new alert with null outcome fields."""
        alert_id = str(uuid.uuid4())
        record = {
            "alert_id": alert_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": score.symbol,
            "timeframe": score.timeframe,
            "direction": score.direction,
            "entry_price": price,
            "tp1": score.tp1,
            "tp2": score.tp2,
            "invalidation": score.invalidation,
            "confidence": score.confidence,
            "tier": score.tier,
            "strategy": score.strategy_type,
            "outcome": None,
            "outcome_timestamp": None,
            "outcome_price": None,
            "r_multiple": None,
            "resolved": False,
            "decision_trace": score.decision_trace
        }
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(record) + "\n")
            logger.info(f"Alert persisted for tracking: {alert_id}")
            return alert_id
        except Exception as exc:
            logger.error(f"Failed to persist alert: {exc}", exc_info=True)
            return None

class AuditLogger:
    """Logs every computation cycle for monitoring heartbeats."""
    def __init__(self, path: str = "logs/audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_cycle(self, symbol: str, timeframe: str, score: float, action: str):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "timeframe": timeframe,
            "score": score,
            "action": action
        }
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except:
            pass

class Notifier:
    """Handles sending notifications, currently via Telegram."""
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.last_hash = ""
        logger.info("Notifier initialized.", extra={'token_set': bool(self.token), 'chat_id_set': bool(self.chat_id)})

    def send(self, msg: str):
        """Sends a message, or prints it if Telegram is not configured."""
        if not self.token or not self.chat_id:
            logger.warning("Telegram token or chat ID not set. Alert will be printed to console.", extra={'msg_preview': msg[:50]})
            print(f"\n--- ALERT ---\n{msg}\n------------\n")
            return
        
        # Avoid sending duplicate messages in quick succession
        msg_hash = hashlib.md5(msg[:160].encode()).hexdigest()
        if msg_hash == self.last_hash:
            logger.debug("Skipping duplicate alert message.", extra={'msg_preview': msg[:50], 'hash': msg_hash})
            return
        
        try:
            logger.info("Attempting to send Telegram message.", extra={'msg_preview': msg[:50]})
            response = httpx.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
            response.raise_for_status()
            self.last_hash = msg_hash
            logger.info("Telegram message sent successfully.", extra={'msg_preview': msg[:50], 'response_status': response.status_code})
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"HTTP error sending Telegram message: {exc.response.status_code} - {exc.response.text}", 
                extra={'error': str(exc), 'response_status_code': exc.response.status_code, 'response_text': exc.response.text, 'msg_preview': msg[:50]}
            )
        except Exception as exc:
            logger.error(f"Error sending Telegram message: {exc}", exc_info=True, extra={'msg_preview': msg[:50]})

class AlertStateStore:
    """Manages the state of alerts to prevent redundant notifications."""
    def __init__(self, path: str = ".mvp_alert_state.json"):
        self.path = Path(path)
        self.state = {}
        self._load_state()
        logger.info(f"AlertStateStore initialized. State loaded from {self.path}. Current state keys: {list(self.state.keys())}")

    def _load_state(self) -> None:
        if not self.path.exists():
            return
        try:
            content = self.path.read_text()
            self.state = json.loads(content)
        except Exception as exc:
            logger.warning("Error reading state file, resetting state: %s", exc, exc_info=True)
            self._rotate_bad_state()

    def _rotate_bad_state(self) -> None:
        backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        try:
            self.path.rename(backup_path)
            logger.info(f"Backed up corrupted state file to '{backup_path.name}'")
        except Exception as exc:
            logger.error(f"Failed to backup corrupted state file '{self.path.name}': {exc}", exc_info=True)
        self.state = {}

    def should_send(self, score: AlertScore, current_price: float) -> bool:
        decision_trace_data = {
            "symbol": score.symbol,
            "timeframe": score.timeframe,
            "score_action": score.action,
            "tier": score.tier,
            "current_price": current_price,
        }

        if score.action == "SKIP":
            logger.info("Alert filtered: Explicitly skipped.", extra=decision_trace_data)
            return False

        now = int(time.time())
        symbol_state = self.state.get(score.symbol, {})
        timeframe_state = symbol_state.get(score.timeframe, {})

        cooldown = COOLDOWN_SECONDS.get(score.tier, COOLDOWN_SECONDS["B"])
        old_key = timeframe_state.get("lifecycle_key")
        old_tier = timeframe_state.get("tier")
        old_ts = timeframe_state.get("last_candle_ts", 0)

        tire_ranks = {"NO-TRADE": 0, "WATCH": 1, "B": 2, "A+": 3}
        current_rank = tire_ranks.get(score.tier, 0)
        previous_rank = tire_ranks.get(old_tier, 0)

        is_new_candle = score.last_candle_ts > old_ts
        is_tier_upgrade = current_rank > previous_rank
        is_new_lifecycle = old_key != score.lifecycle_key

        if is_new_lifecycle or is_new_candle or is_tier_upgrade:
            logger.info("Alert should send: Change detected.", extra=decision_trace_data)
            return True

        if now - int(timeframe_state.get("last_sent", 0)) > cooldown:
            logger.info("Alert should send: Cooldown period passed.", extra=decision_trace_data)
            return True

        # TP1 check
        if not timeframe_state.get("tp1_hit", False):
            is_tp1_hit = False
            if score.direction == "LONG" and current_price >= score.tp1:
                is_tp1_hit = True
            elif score.direction == "SHORT" and current_price <= score.tp1:
                is_tp1_hit = True
            
            if is_tp1_hit:
                logger.info("Alert should send: TP1 was hit.", extra=decision_trace_data)
                return True

        return False

    def save(self, score: AlertScore, current_price: float):
        tp1_hit = False
        if score.direction == "LONG" and current_price >= score.tp1:
            tp1_hit = True
        elif score.direction == "SHORT" and current_price <= score.tp1:
            tp1_hit = True

        new_entry = {
            "lifecycle_key": score.lifecycle_key,
            "tier": score.tier,
            "last_sent": int(time.time()),
            "last_candle_ts": score.last_candle_ts,
            "tp1_hit": tp1_hit,
        }
        
        self.state.setdefault(score.symbol, {})[score.timeframe] = new_entry
        try:
            self.path.write_text(json.dumps(self.state, indent=4))
        except Exception as exc:
            logger.error(f"Failed to save state to '{self.path.name}': {exc}", exc_info=True)
