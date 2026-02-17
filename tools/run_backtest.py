#!/usr/bin/env python3
"""
Backtest Runner for BTC Alerts.
Fetches historical data and replays the engine to measure performance.
"""

import sys
import logging
import time
from collectors.base import BudgetManager
from collectors.price import _fetch_kraken_ohlc, _fetch_bybit_ohlc
from tools.replay import replay_symbol_timeframe, summarize

import engine

# Monkeypatch: Disable stale checks for replay
engine._is_stale = lambda candles, timeframe: False

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

def get_history(limit=720):
    """Fetch max available 5m candles."""
    budget = BudgetManager()
    logging.info(f"Fetching last {limit} candles (5m timeframe)...")
    
    # Try Kraken first (reliable)
    candles = _fetch_kraken_ohlc(budget, interval=5, limit=limit)
    if not candles:
        logging.info("Kraken failed, trying Bybit...")
        candles = _fetch_bybit_ohlc(budget, interval="5", limit=limit)
        
    if not candles:
        logging.error("Could not fetch historical data.")
        sys.exit(1)
        
    logging.info(f"Successfully loaded {len(candles)} candles.")
    return candles

def main():
    print("==================================================")
    print("   BTC ALERTS MVP — BACKTEST ENGINE")
    print("==================================================")
    
    # 1. Fetch History
    candles = get_history(limit=1000) # Maximize history
    
    # 2. Run Replays
    print("\n>>> RUNNING REPLAYS <<<")
    results = {}
    
    for tf in ["5m", "15m", "1h"]:
        print(f"Testing {tf} strategy...", end=" ", flush=True)
        try:
            metrics = replay_symbol_timeframe("BTC", tf, candles)
            results[tf] = metrics
            print("DONE")
        except Exception as e:
            print(f"FAILED ({e})")
    
    # 3. Report
    print("\n==================================================")
    print("   PERFORMANCE REPORT (Last ~3 Days)")
    print("==================================================")
    print(f"{'TIMEFRAME':<10} | {'ALERTS':<8} | {'TRADES':<8} | {'WIN RATE':<10} | {'EXPECTANCY'}")
    print("-" * 65)
    
    for tf, m in results.items():
        win_rate = f"{m.directional_hit_proxy * 100:.1f}%"
        # Rough expectancy calc: (WinRate * Reward) - (LossRate * Risk)
        # Assuming avg Reward 1.5R and Risk 1.0R for this estimation
        ev = (m.directional_hit_proxy * 1.5) - ((1.0 - m.directional_hit_proxy) * 1.0)
        ev_color = "🟢" if ev > 0.2 else "🔴" if ev < 0 else "⚪"
        
        print(f"{tf:<10} | {m.alerts:<8} | {m.trades:<8} | {win_rate:<10} | {ev_color} {ev:.2f}R")
        
    print("==================================================")
    print("\nNOTE: This backtest uses Price Action Only.")
    print("      (Fear&Greed, Derivatives, and Macro Context are mocked as Neutral)")
    print("      Real performance generally improves with these filters enabled.")
    print("==================================================")

if __name__ == "__main__":
    main()
