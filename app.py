import hashlib
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import load_dotenv

from collectors.base import BudgetManager
from collectors.derivatives import DerivativesSnapshot, fetch_derivatives_context
from collectors.flows import FlowSnapshot, fetch_flow_context
from collectors.price import (
    PriceSnapshot,
    fetch_btc_multi_timeframe_candles,
    fetch_btc_price,
    fetch_macro_context,
    fetch_spx_multi_timeframe_bundle,
)
from collectors.social import FearGreedSnapshot, fetch_fear_greed, fetch_news
from config import COOLDOWN_SECONDS, validate_config
from engine import AlertScore, compute_score
from tools.outcome_tracker import resolve_outcomes
from tools.paper_trader import Portfolio as PaperPortfolio

load_dotenv()

# --- Config and Paths ---
BUDGET_MANAGER_PATH = ".mvp_budget.json"
STATE_STORE_PATH = ".mvp_alert_state.json"

# --- Structured Logging Configuration START ---
class JSONFormatter(logging.Formatter):
    """
    A custom logging formatter that outputs log records in JSON format.
    Includes timestamp, level, message, logger name, file, line number, process ID, and thread ID.
    Also captures any extra attributes passed to the log record.
    """
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        # Use ISO 8601 format with timezone for consistency
        self.datefmt = "%Y-%m-%dT%H:%M:%S%z" if datefmt is None else datefmt
        # Pre-define fields that are standard in logging.LogRecord to avoid duplicating them
        self.standard_fields = (
            "name", "levelname", "levelno", "pathname", "lineno", 
            "asctime", "msecs", "relativeCreated", "created", 
            "thread", "threadName", "process", "processName", 
            "message", "exc_info", "exc_text", "stack_info"
        )

    def formatTime(self, record, datefmt=None):
        """Format time using the datefmt specified in the constructor or overridden."""
        ct = self.converter(record.created)
        if datefmt is None:
            datefmt = self.datefmt
        # Ensure timezone is included if available (e.g., PST, EST)
        if '%z' in datefmt and ct.tm_zone:
            return time.strftime(datefmt, ct)
        elif '%z' not in datefmt:
            # Add ISO 8601 style offset if %z is not in datefmt and timezone is known
            return time.strftime(datefmt, ct) + time.strftime("%z", ct)
        return time.strftime(datefmt, ct)


    def format(self, record):
        """Format the log record into a JSON string."""
        log_record = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "file": record.pathname.split('/')[-1] if record.pathname else None, # Extract filename
            "line": record.lineno,
            "process_id": record.process,
            "thread_id": record.thread,
        }

        # Attach any extra attributes passed to the logger
        for key, value in record.__dict__.items():
            if key not in self.standard_fields:
                try:
                    # Test if serializable
                    json.dumps(value)
                    log_record[key] = value
                except (TypeError, OverflowError):
                    log_record[key] = str(value)
        
        # Include exception information if present
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_record)

# Setup the logger for the application
logger = logging.getLogger("btc_alerts")

# Configure the logger only if it doesn't already have handlers
# This prevents adding multiple handlers if the script is run multiple times (e.g., in an interactive session)
if not logger.handlers:
    logger.setLevel(logging.INFO) # Set the minimum logging level
    
    # Create a console handler
    handler = logging.StreamHandler(sys.stdout)
    
    # Create an instance of our JSON formatter
    formatter = JSONFormatter()
    handler.setFormatter(formatter)
    
    # Add the handler to the logger
    logger.addHandler(handler)
    
    # Prevent logs from being propagated to the root logger, which might have its own configuration
    logger.propagate = False 

logger.info("Structured logging configured.")
# --- Structured Logging Configuration END ---


import uuid
from datetime import datetime

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
            "resolved": False
        }
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(record) + "\n")
            logger.info(f"Alert persisted for tracking: {alert_id}")
            return alert_id
        except Exception as exc:
            logger.error(f"Failed to persist alert: {exc}", exc_info=True)
            return None


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
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            self.last_hash = msg_hash
            logger.info("Telegram message sent successfully.", extra={'msg_preview': msg[:50], 'response_status': response.status_code})
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"HTTP error sending Telegram message: {exc.response.status_code} - {exc.response.text}", 
                extra={'error': str(exc), 'response_status_code': exc.response.status_code, 'response_text': exc.response.text, 'msg_preview': msg[:50]}
            )
        except Exception as exc:
            # Log other exceptions with traceback
            logger.error(f"Error sending Telegram message: {exc}", exc_info=True, extra={'msg_preview': msg[:50]})


class AlertStateStore:
    """Manages the state of alerts to prevent redundant notifications."""
    def __init__(self, path: str = ".mvp_alert_state.json"):
        self.path = Path(path)
        self.state = {} # Initialize state dictionary
        self._load_state()
        logger.info(f"AlertStateStore initialized. State loaded from {self.path}. Current state keys: {list(self.state.keys())}")

    def _load_state(self) -> None:
        """Loads the alert state from a JSON file."""
        if not self.path.exists():
            logger.info("State file not found, starting with empty state.")
            return
        try:
            content = self.path.read_text()
            self.state = json.loads(content)
            logger.info(f"State file '{self.path.name}' loaded successfully. Contains {len(self.state)} symbols.")
        except json.JSONDecodeError as exc:
            logger.warning("State file is not valid JSON, resetting state. Error: %s", exc, exc_info=True)
            self._rotate_bad_state()
        except Exception as exc:
            logger.warning("Error reading state file, resetting state: %s", exc, exc_info=True)
            self._rotate_bad_state()

    def _rotate_bad_state(self) -> None:
        """Backs up the corrupted state file and resets the state."""
        backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        try:
            self.path.rename(backup_path)
            logger.info(f"Backed up corrupted state file to '{backup_path.name}'")
        except Exception as exc:
            logger.error(f"Failed to backup corrupted state file '{self.path.name}': {exc}", exc_info=True)
        self.state = {} # Ensure state is empty if backup failed or if file was empty/unreadable

    def should_send(self, score: AlertScore, current_price: float) -> bool:
        """
        Determines if an alert should be sent based on state, cooldown, and TP1 hit.
        Includes detailed logging for decision tracing.
        """
        decision_trace_data = {
            "symbol": score.symbol,
            "timeframe": score.timeframe,
            "score_action": score.action,
            "tier": score.tier,
            "current_price": current_price,
            "lifecycle_key_from_score": score.lifecycle_key,
            "tier_from_score": score.tier,
        }

        # Decision 1: Explicitly skip
        if score.action == "SKIP":
            decision_trace_data["decision"] = "SKIP"
            decision_trace_data["reason"] = "Score action is explicitly SKIP."
            logger.info("Alert filtered: Explicitly skipped.", extra=decision_trace_data)
            return False

        now = int(time.time())
        symbol_state = self.state.get(score.symbol, {})
        timeframe_state = symbol_state.get(score.timeframe, {})

        # Add state information to trace data for context
        decision_trace_data.update({
            "last_sent_from_state": timeframe_state.get("last_sent"),
            "cooldown_seconds": COOLDOWN_SECONDS.get(score.tier, COOLDOWN_SECONDS["B"]),
            "lifecycle_key_from_state": timeframe_state.get("lifecycle_key"),
            "tier_from_state": timeframe_state.get("tier"),
            "tp1_hit_from_state": timeframe_state.get("tp1_hit", False),
            "current_time": now,
            "time_since_last_sent": now - int(timeframe_state.get("last_sent", 0)) if timeframe_state.get("last_sent") else float('inf')
        })
        
        # Decision 2: Lifecycle, Tier, or Candle changed
        old_key = timeframe_state.get("lifecycle_key")
        old_tier = timeframe_state.get("tier")
        old_ts = timeframe_state.get("last_candle_ts", 0)

        # Send if it's a new lifecycle OR a new candle
        # BUT if it's the same candle, only send if the tier upgraded (e.g. WATCH -> TRADE)
        tire_ranks = {"NO-TRADE": 0, "WATCH": 1, "B": 2, "A+": 3}
        current_rank = tire_ranks.get(score.tier, 0)
        previous_rank = tire_ranks.get(old_tier, 0)

        is_new_candle = score.last_candle_ts > old_ts
        is_tier_upgrade = current_rank > previous_rank
        is_new_lifecycle = old_key != score.lifecycle_key

        if is_new_lifecycle or is_new_candle or is_tier_upgrade:
            decision_trace_data["decision"] = "SEND"
            decision_trace_data["reason"] = f"New signal: candle_change={is_new_candle}, upgrade={is_tier_upgrade}, lifecycle={is_new_lifecycle}"
            logger.info("Alert should send: Change detected.", extra=decision_trace_data)
            return True

        # Decision 3: Cooldown period has passed
        cooldown = COOLDOWN_SECONDS.get(score.tier, COOLDOWN_SECONDS["B"])
        if now - int(timeframe_state.get("last_sent", 0)) > cooldown:
            decision_trace_data["decision"] = "SEND"
            decision_trace_data["reason"] = "Cooldown period has passed."
            logger.info("Alert should send: Cooldown period passed.", extra=decision_trace_data)
            return True

        # Decision 4: Check if Take Profit 1 (TP1) has been hit for the first time in this lifecycle
        if not timeframe_state.get("tp1_hit", False):
            is_tp1_hit = False
            if score.direction == "LONG" and current_price >= score.tp1:
                is_tp1_hit = True
            elif score.direction == "SHORT" and current_price <= score.tp1:
                is_tp1_hit = True
            
            if is_tp1_hit:
                decision_trace_data["decision"] = "SEND"
                decision_trace_data["reason"] = "TP1 hit for the first time in this lifecycle."
                decision_trace_data["new_tp1_hit_status"] = True
                logger.info("Alert should send: TP1 was hit.", extra=decision_trace_data)
                return True
            else:
                # If TP1 is not hit and not previously hit, we don't send yet based on TP1 condition alone.
                # This path means it's not a new lifecycle/tier, cooldown hasn't passed, and TP1 is not hit.
                decision_trace_data["decision"] = "FILTER"
                decision_trace_data["reason"] = "TP1 not hit and not previously hit for this lifecycle; other conditions not met."
                logger.debug("Alert filtered: TP1 not hit. Other conditions not met.", extra=decision_trace_data)
                return False

        # Decision 5: If TP1 was already hit, and no other conditions triggered sending (lifecycle/tier change, cooldown),
        # then we should not send another alert for this cycle.
        # This implies it's a subsequent check after TP1 was already hit.
        decision_trace_data["decision"] = "FILTER"
        decision_trace_data["reason"] = "TP1 already hit for this lifecycle; no new conditions met."
        logger.debug("Alert filtered: TP1 already hit for this lifecycle and no new conditions met.", extra=decision_trace_data)
        return False


    def save(self, score: AlertScore, current_price: float):
        """Saves the current alert state, including TP1 hit status."""
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
        
        # Log the state change with detailed context
        log_data = {
            "symbol": score.symbol,
            "timeframe": score.timeframe,
            "new_state_entry": new_entry,
            "current_price": current_price,
            "tp1_hit_calculated": tp1_hit,
            "previous_state": self.state.get(score.symbol, {}).get(score.timeframe, {}),
        }
        logger.info("Saving alert state.", extra=log_data)
        
        # Update the state dictionary
        self.state.setdefault(score.symbol, {})[score.timeframe] = new_entry
        
        # Write the updated state to the file
        try:
            self.path.write_text(json.dumps(self.state, indent=4)) # Use indent for readability
            logger.info(f"State successfully saved to '{self.path.name}'.")
        except Exception as exc:
            logger.error(f"Failed to save state to '{self.path.name}': {exc}", exc_info=True)


def _latest_spx_price(spx_tf: dict, timeframe: str) -> float:
    """Retrieves the latest closing price from SPX timeframe data."""
    candles = spx_tf.get(timeframe, [])
    if not candles:
        logger.warning("No SPX candles found for timeframe '%s' to get latest price.", timeframe)
        return 0.0
    # Assuming candles is a list of objects, each with a 'close' attribute
    return candles[-1].close


def _format_alert(score: AlertScore, provider_context: dict) -> str:
    """Formats an AlertScore object into a readable string for notifications."""
    # Log the decision to format this alert, capturing key details for tracing
    alert_payload_log_data = {
        "symbol": score.symbol,
        "timeframe": score.timeframe,
        "action": score.action,
        "tier": score.tier,
        "direction": score.direction,
        "strategy_type": score.strategy_type,
        "confidence_score": score.confidence,
        "entry_zone": score.entry_zone,
        "invalidation_level": round(score.invalidation, 2),
        "tp1": round(score.tp1, 2),
        "tp2": round(score.tp2, 2),
        "rr_ratio": round(score.rr_ratio, 2),
        "context": {
            "regime": score.regime,
            "session": score.session,
            "quality": score.quality,
            "providers": provider_context,
        },
        "reason_codes": score.reason_codes,
        "score_breakdown": score.score_breakdown,
        "blockers": score.blockers,
        "decision_trace": score.decision_trace, # This might already be a list in AlertScore
    }
    logger.debug("Formatting alert payload for notification.", extra=alert_payload_log_data)

    # Construct the detailed payload to be embedded in the message
    payload_for_display = {
        "symbol": score.symbol,
        "timeframe": score.timeframe,
        "action": score.action,
        "tier": score.tier,
        "direction": score.direction,
        "strategy_type": score.strategy_type,
        "confidence_score": score.confidence,
        "entry_zone": score.entry_zone,
        "invalidation_level": round(score.invalidation, 2),
        "tp1": round(score.tp1, 2),
        "tp2": round(score.tp2, 2),
        "rr_ratio": round(score.rr_ratio, 2),
        "context": {
            "regime": score.regime,
            "session": score.session,
            "quality": score.quality,
            "providers": provider_context,
        },
        "reason_codes": score.reason_codes,
        "score_breakdown": score.score_breakdown,
        "blockers": score.blockers,
        "decision_trace": score.decision_trace,
    }
    
    # Return the formatted message string with embedded JSON payload
    return f"--- ALERT ---\n*{score.symbol} {score.timeframe} {score.action} ({score.tier})*\n```{json.dumps(payload_for_display, indent=2)}```"


def run(bm: BudgetManager, notif: Notifier, state: AlertStateStore, p_logger: PersistentLogger, portfolio: PaperPortfolio):
    """Main function to execute the BTC alert monitoring process."""
    # Log the start of the main execution, indicating configuration validation is next.
    logger.info("Starting main execution cycle.")
    
    # Data collection phase
    alerts = [] # List to hold all computed alert scores
    
    # --- Data Collection: BTC ---
    btc_price = None # Initialize to None to handle exceptions gracefully
    sleep_duration = 1.0 # Base sleep duration

    try:
        logger.info("Fetching BTC price data...")
        btc_price = fetch_btc_price(bm)
        if btc_price.healthy:
            logger.info(f"Successfully fetched live BTC price.", extra={'price': f"{btc_price.price:,.2f}", 'source': btc_price.source})
        else:
            logger.warning("Failed to fetch BTC price or data is unhealthy.", extra={'source': btc_price.source, 'healthy': btc_price.healthy})
    except Exception as e:
        logger.error("Exception occurred during BTC price fetch: %s", e, exc_info=True)
        # Create a dummy unhealthy PriceSnapshot if fetch fails
        btc_price = PriceSnapshot(price=0.0, timestamp=time.time(), source="error", healthy=False)
    
    # Add a small delay to respect API rate limits or server load
    time.sleep(sleep_duration)

    btc_tf = {} # Initialize to empty dict
    try:
        logger.info("Fetching BTC multi-timeframe candles...")
        btc_tf = fetch_btc_multi_timeframe_candles(bm)
        logger.info(f"Collected BTC multi-timeframe candle data. Available timeframes: {list(btc_tf.keys())}")
        
        # Log health status for each collected timeframe
        for tf in ["5m", "15m", "1h", "4h", "1d"]: # Check common timeframes
            if tf in btc_tf:
                if btc_tf[tf]: # Check if list of candles is not empty
                    # Assuming each candle object has a 'healthy' attribute or similar check is needed
                    # For now, we check if the list is non-empty, implying data was fetched
                    logger.info(f"Collected {len(btc_tf[tf])} BTC {tf} candles.", extra={'timeframe': tf, 'candle_count': len(btc_tf[tf])})
                else:
                    logger.warning("Collected BTC %s candles, but the list is empty.", tf, extra={'timeframe': tf})
            else:
                logger.warning("BTC %s candles not found in fetch result.", tf, extra={'timeframe': tf})
    except Exception as e:
        logger.error("Exception occurred during BTC multi-timeframe candle fetch: %s", e, exc_info=True)
        btc_tf = {} # Ensure btc_tf is an empty dict on error
    
    time.sleep(sleep_duration) 

    # --- Data Collection: SPX ---
    spx_tf, spx_source_map = {}, {} # Initialize to empty dicts to handle potential errors gracefully
    try:
        logger.info("Fetching SPX multi-timeframe bundle...")
        spx_tf, spx_source_map = fetch_spx_multi_timeframe_bundle(bm)
        logger.info(f"Successfully fetched SPX data. Sources mapped: {spx_source_map}")
        
        # Log health status for fetched SPX data
        for tf, candles in spx_tf.items():
            if candles:
                logger.info(f"Collected {len(candles)} SPX {tf} candles.", extra={'timeframe': tf, 'candle_count': len(candles)})
            else:
                 logger.warning("Collected SPX %s candles, but the list is empty.", tf, extra={'timeframe': tf})
    except Exception as e:
        logger.error("Exception occurred during SPX multi-timeframe bundle fetch: %s", e, exc_info=True)
        spx_tf = {} # Ensure spx_tf is empty on error
        spx_source_map = {}
    
    time.sleep(sleep_duration) # Short delay after SPX fetch

    # --- Data Collection: Macro Context (reuses SPX data) ---
    macro = {"spx": [], "vix": [], "nq": []}
    try:
        logger.info("Fetching macro context data (reusing SPX 5m candles)...")
        # Pass a subset of SPX data if available
        prefetched_spx_5m = spx_tf.get("5m", []) if spx_tf else []
        macro = fetch_macro_context(bm, prefetched_spx=prefetched_spx_5m)
        logger.info(f"Macro context fetched successfully.")
    except Exception as e:
        logger.error("Exception occurred during macro context fetch: %s", e, exc_info=True)
        # Fallback dictionary
        macro = {"spx": [], "vix": [], "nq": []}
    
    time.sleep(sleep_duration)

    # --- Data Collection: Derivatives & Flows ---
    derivatives = None
    try:
        logger.info("Fetching derivatives context data...")
        derivatives = fetch_derivatives_context(bm)
        logger.info(f"Derivatives context fetched.", extra={'source': derivatives.source, 'healthy': derivatives.healthy})
    except Exception as e:
        logger.error("Exception occurred during derivatives context fetch: %s", e, exc_info=True)
        derivatives = DerivativesSnapshot(bid_price=0.0, ask_price=0.0, last_price=0.0, healthy=False, source="error", meta={"provider": "error"})
    
    time.sleep(sleep_duration)
    
    flows = None
    try:
        logger.info("Fetching flows context data...")
        flows = fetch_flow_context(bm)
        logger.info(f"Flows context fetched.", extra={'source': flows.source, 'healthy': flows.healthy})
    except Exception as e:
        logger.error("Exception occurred during flows context fetch: %s", e, exc_info=True)
        flows = FlowSnapshot(volume=0.0, open_interest=0.0, funding_rate=0.0, healthy=False, source="error", meta={"provider": "error"})
    
    time.sleep(sleep_duration)

    # --- Data Collection: Social / News ---
    fg = None
    try:
        logger.info("Fetching Fear & Greed index...")
        fg = fetch_fear_greed(bm)
        logger.info(f"Fear & Greed index fetched.", extra={'value': fg.value, 'label': fg.label, 'healthy': fg.healthy})
    except Exception as e:
        logger.error("Exception occurred during Fear & Greed fetch: %s", e, exc_info=True)
        # Create a dummy healthy snapshot if fetch fails
        fg = FearGreedSnapshot(value=50, label="Neutral", healthy=False)
    
    news = [] # Initialize as empty list
    try:
        logger.info("Fetching latest news headlines...")
        news = fetch_news(bm)
        logger.info(f"Fetched {len(news)} news headlines.", extra={'headline_count': len(news)})
    except Exception as e:
        logger.error("Exception occurred during news fetch: %s", e, exc_info=True)
        news = [] # Ensure news is an empty list on error

    # --- Alert Computation Phase ---
    logger.info("Starting alert computation. Processing BTC and SPX data across timeframes.")
    
    # Check initial data collection status for BTC
    if btc_price and btc_price.healthy and btc_tf.get("5m") and btc_tf.get("15m") and btc_tf.get("1h"):
        logger.info("Core BTC market data collected successfully.", extra={'price_healthy': btc_price.healthy, 'candle_data_available': True})
    else:
        logger.warning("Core BTC market data is incomplete or unhealthy.", extra={'price_healthy': btc_price.healthy if btc_price else 'N/A', 'candle_5m_present': bool(btc_tf.get("5m")), 'candle_15m_present': bool(btc_tf.get("15m")), 'candle_1h_present': bool(btc_tf.get("1h"))})

    # Iterate through common timeframes to compute scores for BTC and SPX
    for tf in ["5m", "15m", "1h"]: # Focused on 5m, 15m, 1h as per original logic
        # Compute score for BTC if data is available
        if btc_price and btc_tf.get(tf) and btc_tf.get("15m", []) and btc_tf.get("1h", []):
            try:
                computed_alert = compute_score(
                    "BTC",
                    tf,
                    btc_price,
                    btc_tf[tf],
                    btc_tf.get("15m", []),
                    btc_tf.get("1h", []),
                    fg,
                    news,
                    derivatives,
                    flows,
                    macro,
                )
                alerts.append(computed_alert)
                logger.info(f"Computed alert score for BTC {tf}.", extra={'symbol': 'BTC', 'timeframe': tf, 'score_confidence': computed_alert.confidence, 'action': computed_alert.action})
            except Exception as e:
                logger.error("Exception during BTC %s score computation: %s", tf, e, exc_info=True, extra={'symbol': 'BTC', 'timeframe': tf})
        else:
            logger.warning(f"Skipping BTC {tf} analysis due to missing or incomplete data. BTC Price healthy: {btc_price.healthy if btc_price else 'N/A'}, BTC Candles {tf} present: {bool(btc_tf.get(tf))}.", extra={'symbol': 'BTC', 'timeframe': tf})

        # Compute score for SPX (as a proxy for general market sentiment/direction)
        if spx_tf and spx_tf.get(tf) and spx_tf.get("15m", []) and spx_tf.get("1h", []):
            try:
                # Create a PriceSnapshot for SPX using its latest closing price from the timeframe
                spx_latest_close = spx_tf[tf][-1].close if spx_tf[tf] else 0.0
                spx_price_snapshot = PriceSnapshot(price=spx_latest_close, timestamp=time.time(), source=spx_source_map.get(tf, "yahoo"), healthy=True)
                
                computed_alert = compute_score(
                    "SPX_PROXY", # Use a distinct symbol for SPX proxy alerts
                    tf,
                    spx_price_snapshot,
                    spx_tf[tf],
                    spx_tf.get("15m", []),
                    spx_tf.get("1h", []),
                    # Use a dummy FearGreed if SPX, as it's market-wide, not specific to BTC fear
                    FearGreedSnapshot(50, "Neutral", healthy=False), 
                    [], # News might be too specific for SPX proxy, or could be included if relevant
                    DerivativesSnapshot(0.0, 0.0, 0.0, healthy=False, source="none", meta={"provider": "none"}), # No derivatives for SPX proxy
                    FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="none", meta={"provider": "none"}), # No flows for SPX proxy
                    macro, # Macro context is relevant for SPX
                )
                alerts.append(computed_alert)
                logger.info(f"Computed alert score for SPX_PROXY {tf}.", extra={'symbol': 'SPX_PROXY', 'timeframe': tf, 'score_confidence': computed_alert.confidence, 'action': computed_alert.action})
            except Exception as e:
                logger.error("Exception during SPX_PROXY %s score computation: %s", tf, e, exc_info=True, extra={'symbol': 'SPX_PROXY', 'timeframe': tf})
        else:
            logger.warning("Skipping SPX_PROXY %s analysis due to missing or incomplete data.", tf, extra={'symbol': 'SPX_PROXY', 'timeframe': tf})

    logger.info(f"Total alerts generated: {len(alerts)}. Starting alert filtering and notification phase.")
    
    # --- Alert Filtering and Notification Phase ---
    best_alert_btc = None # Track the best BTC alert
    best_score_btc = -1   # Track the best BTC alert score

    # Process each computed alert
    for alert in alerts:
        # Identify the best BTC alert for summary
        if alert.symbol == "BTC":
            if alert.confidence > best_score_btc:
                best_score_btc = alert.confidence
                best_alert_btc = alert

        # Determine the relevant current price for state checks
        if alert.symbol == "BTC":
            current_price_for_state = btc_price.price if btc_price else 0.0
        elif alert.symbol == "SPX_PROXY":
            current_price_for_state = _latest_spx_price(spx_tf, alert.timeframe) if spx_tf else 0.0
        else:
            current_price_for_state = 0.0 # Fallback for unknown symbols

        # Check if the alert should be sent using the state store
        if not state.should_send(alert, current_price_for_state):
            logger.debug("Alert filtered by state store: %s %s", alert.symbol, alert.timeframe, extra={'symbol': alert.symbol, 'timeframe': alert.timeframe, 'action': alert.action})
            continue # Skip to the next alert if should_send returns False
        
        # If should_send is True, format and send the alert
        # Construct provider context for logging/formatting
        provider_context = {
            "price": btc_price.source if alert.symbol == "BTC" else spx_source_map.get(alert.timeframe, "none"),
            "derivatives": derivatives.source if alert.symbol == "BTC" else "none", # Derivatives for BTC
            "flows": flows.source if alert.symbol == "BTC" else "none", # Flows for BTC
            "spx_mode": "direct" if spx_source_map.get(alert.timeframe) == "^GSPC" else "proxy" if alert.symbol == "SPX_PROXY" else "n/a",
            "macro_regime": alert.regime,
            "fear_greed": fg.label if alert.symbol == "BTC" else "N/A" # Include F&G for BTC alerts
        }

        # Format the alert message
        msg = _format_alert(alert, provider_context)
        logger.info(f">>> SENDING ALERT <<<", extra={'symbol': alert.symbol, 'timeframe': alert.timeframe, 'action': alert.action, 'message_preview': msg[:100]})
        
        # Send the notification
        notif.send(msg)
        
        # Save the state after sending the alert
        state.save(alert, current_price_for_state)
        alert_id = p_logger.log_alert(alert, current_price_for_state)
        if alert_id:
            portfolio.on_alert(
                alert_id, alert.symbol, alert.timeframe, alert.direction, 
                current_price_for_state, alert.invalidation, alert.tp1, alert.action
            )

    # --- Summary and Reporting ---
    logger.info("Finished processing all alerts. Generating summary output.")
    
    # Print market overview for BTC
    print("\n" + "="*50)
    print("  MARKET OVERVIEW: BTC")
    print("="*50)
    print(f"  {'TIMEFRAME':<10} | {'ACTION':<10} | {'DIRECTION':<10} | {'SCORE':<5}")
    print("-" * 50)
    
    btc_alerts = [a for a in alerts if a.symbol == "BTC"]
    if btc_alerts:
        for a in btc_alerts:
            print(f"  {a.timeframe:<10} | {a.action:<10} | {a.direction:<10} | {a.confidence:<5}")
    else:
        print("  No BTC alerts computed.")
    print("="*50)

    # Print the best BTC setup found
    if best_alert_btc:
        print("\n" + "="*50)
        print(f"  BEST BTC SETUP: {best_alert_btc.symbol} ({best_alert_btc.timeframe})")
        print("="*50)
        print(f"  • ACTION:      {best_alert_btc.action} ({best_alert_btc.tier})")
        print(f"  • DIRECTION:   {best_alert_btc.direction}")
        print(f"  • CONFIDENCE:  {best_alert_btc.confidence}/100")
        print(f"  • STRATEGY:    {best_alert_btc.strategy_type}")
        print("-" * 50)
        if best_alert_btc.direction != "NEUTRAL":
            print(f"  • ENTRY ZONE:  {best_alert_btc.entry_zone}")
            print(f"  • TARGET 1:    ${best_alert_btc.tp1:,.2f}")
            print(f"  • TARGET 2:    ${best_alert_btc.tp2:,.2f}")
            print(f"  • STOP LOSS:   ${best_alert_btc.invalidation:,.2f}")
            print(f"  • R:R RATIO:   {best_alert_btc.rr_ratio:.2f}")
        else:
            print("  • No clear trade setup currently.")
        print("-" * 50)
        print(f"  • REASONS:     {', '.join(best_alert_btc.reasons)}")
        if best_alert_btc.blockers:
            print(f"  • BLOCKERS:    {', '.join(best_alert_btc.blockers)}")
        print("="*50 + "\n")
        logger.info("Best BTC alert details displayed.", extra={'symbol': best_alert_btc.symbol, 'timeframe': best_alert_btc.timeframe, 'confidence': best_alert_btc.confidence})
    else:
        logger.info("No best BTC alert identified for summary.")
        
    # Print timeframe guide
    print("  TIMEFRAME GUIDE:")
    print("  • 5m:  Scalping (Fast action, 15-60 min hold)")
    print("  • 15m: Day Trading (Balanced, 1-4 hour hold)")
    print("  • 1h:  Swing Trading (Trend following, 4-24 hour hold)")
    print("\n")
    logger.info("Summary and timeframe guide displayed.")
    
    # Resolve outcomes for pending alerts
    try:
        resolve_outcomes()
        if btc_price and btc_price.healthy:
            portfolio.update(btc_price.price)
        
        # Generate reporting artifacts
        os.system(f"{sys.executable} scripts/pid-129/generate_scorecard.py")
        os.system(f"{sys.executable} scripts/pid-129/generate_dashboard.py")
    except Exception as e:
        logger.error(f"Error during loop house-keeping: {e}")


# --- Main execution block ---
if __name__ == "__main__":
    try:
        validate_config()
        logger.info("Configuration validated successfully.")
    except Exception as e:
        logger.error("Configuration validation failed: %s", e, exc_info=True)
        print("FATAL: Configuration validation failed. Exiting.")
        sys.exit(1)

    # Initialize core components once at startup
    bm = BudgetManager(BUDGET_MANAGER_PATH)
    notif = Notifier()
    state = AlertStateStore(STATE_STORE_PATH)
    p_logger = PersistentLogger()
    portfolio = PaperPortfolio()

    # Check if the script is run with '--once' argument
    if "--once" in sys.argv:
        run(bm, notif, state, p_logger, portfolio)
        logger.info("Script finished execution in --once mode.")
    else:
        # Run in a continuous loop with a 5-minute interval
        logger.info("Starting continuous monitoring loop (5-minute intervals).")
        while True:
            if os.path.exists("STOP"):
                logger.warning("STOP file detected. Gracefully exiting...")
                os.remove("STOP") # Remove it so it doesn't block future starts
                sys.exit(0)

            try:
                run(bm, notif, state, p_logger, portfolio)
            except Exception as exc:
                logger.error("Unhandled exception in main loop: %s", exc, exc_info=True)
            
            # Calculate sleep time to align with 5-minute intervals (300 seconds)
            current_time_seconds = time.time()
            interval_seconds = 300
            sleep_duration = interval_seconds - (current_time_seconds % interval_seconds)
            logger.info(f"Sleeping for {sleep_duration:.2f} seconds before next cycle.")
            time.sleep(sleep_duration)
