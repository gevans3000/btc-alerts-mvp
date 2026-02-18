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
from config import COOLDOWN_SECONDS, validate_config, INTELLIGENCE_FLAGS
from intelligence import IntelligenceBundle
from intelligence.squeeze import detect_squeeze
from intelligence.sentiment import analyze_sentiment
from engine import AlertScore, compute_score
from tools.outcome_tracker import resolve_outcomes
from tools.paper_trader import Portfolio as PaperPortfolio

load_dotenv()

# --- Config and Paths ---
BUDGET_MANAGER_PATH = ".mvp_budget.json"
STATE_STORE_PATH = ".mvp_alert_state.json"

from core.logger import logger
from core.infrastructure import PersistentLogger, AuditLogger, Notifier, AlertStateStore
from core.formatting import format_alert_msg, print_market_overview, print_best_setup, print_timeframe_guide

def _latest_spx_price(spx_tf: dict, timeframe: str) -> float:
    """Retrieves the latest closing price from SPX timeframe data."""
    candles = spx_tf.get(timeframe, [])
    if not candles:
        logger.warning("No SPX candles found for timeframe '%s' to get latest price.", timeframe)
        return 0.0
    return candles[-1].close


def _collect_intelligence(candles, news, btc_price):
    """Call all intelligence layers. Never crashes. Returns whatever succeeded."""
    intel = IntelligenceBundle()
    degraded = []

    # Squeeze
    if INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
        try:
            intel.squeeze = detect_squeeze(candles)
        except Exception as e:
            logger.warning(f"Squeeze degraded: {e}")
            degraded.append("squeeze")
    
    # Sentiment
    if INTELLIGENCE_FLAGS.get("sentiment_enabled", True):
        try:
            intel.sentiment = analyze_sentiment(news)
        except Exception as e:
            logger.warning(f"Sentiment degraded: {e}")
            degraded.append("sentiment")
    
    if degraded:
        logger.info(f"Intelligence degraded layers: {degraded}")

    return intel


def run(bm: BudgetManager, notif: Notifier, state: AlertStateStore, p_logger: PersistentLogger, a_logger: AuditLogger, portfolio: PaperPortfolio):
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
        intel = IntelligenceBundle() # Initialize for each timeframe
        # Compute score for BTC if data is available
        if btc_price and btc_tf.get(tf) and btc_tf.get("15m", []) and btc_tf.get("1h", []):
            try:
                candles = btc_tf[tf]

                # Initialize intelligence bundle for this timeframe
                intel = IntelligenceBundle()


                # All intelligence layers are now prepared in 'intel' bundle
                intel = _collect_intelligence(candles, news, btc_price)
                computed_alert = compute_score(
                    symbol="BTC",
                    timeframe=tf,
                    price=btc_price, # Pass full snapshot object
                    candles=candles, # Corrected to 'candles'
                    candles_15m=btc_tf.get("15m", []),
                    candles_1h=btc_tf.get("1h", []),
                    fg=fg,
                    news=news,
                    derivatives=derivatives,
                    flows=flows,
                    macro=macro,
                    intel=intel,
                )
                alerts.append(computed_alert)
                a_logger.log_cycle("BTC", tf, computed_alert.confidence, computed_alert.action)
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
                a_logger.log_cycle("SPX_PROXY", tf, computed_alert.confidence, computed_alert.action)
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
            "fear_greed": fg.label if alert.symbol == "BTC" else "N/A", # Include F&G for BTC alerts
            "squeeze": alert.intel.squeeze if alert.intel and alert.intel.squeeze else "N/A", # Squeeze state
        }

        # Format the alert message
        msg = format_alert_msg(alert, provider_context)
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
    print_market_overview(alerts)
    print_best_setup(best_alert_btc)
    print_timeframe_guide()
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
    a_logger = AuditLogger()
    portfolio = PaperPortfolio()

    # Check if the script is run with '--once' argument
    if "--once" in sys.argv:
        run(bm, notif, state, p_logger, a_logger, portfolio)
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
                run(bm, notif, state, p_logger, a_logger, portfolio)
            except Exception as exc:
                logger.error("Unhandled exception in main loop: %s", exc, exc_info=True)
            
            # Calculate sleep time to align with 5-minute intervals (300 seconds)
            current_time_seconds = time.time()
            interval_seconds = 300
            sleep_duration = interval_seconds - (current_time_seconds % interval_seconds)
            logger.info(f"Sleeping for {sleep_duration:.2f} seconds before next cycle.")
            time.sleep(sleep_duration)
