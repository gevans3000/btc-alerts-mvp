"""
Standalone historical backtest tool.
Usage: PYTHONPATH=. python tools/backtest.py --limit 200 --output reports/backtest_results.csv
"""
import argparse
import csv
import logging
import os
import sys
import time
from datetime import datetime, timezone

from collectors.base import BudgetManager
from collectors.price import _fetch_kraken_ohlc, PriceSnapshot
from collectors.social import FearGreedSnapshot
from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from engine import compute_score
from intelligence import IntelligenceBundle
from intelligence.squeeze import detect_squeeze

logger = logging.getLogger(__name__)


def _dummy_fg():
    return FearGreedSnapshot(value=50, label="Neutral", healthy=False)


def _dummy_deriv():
    return DerivativesSnapshot(0.0, 0.0, 0.0, source="backtest", healthy=False, meta={"provider": "backtest"})


def _dummy_flows():
    return FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="backtest", meta={"provider": "backtest"})


def _run_backtest(candles_1h, window=40):
    """Slide a window across 1h candles and score each position."""
    results = []

    for i in range(window, len(candles_1h)):
        wc = candles_1h[i - window : i]

        intel = IntelligenceBundle()
        try:
            intel.squeeze = detect_squeeze(wc)
        except Exception:
            pass

        price = PriceSnapshot(
            price=wc[-1].close,
            timestamp=float(wc[-1].ts),
            source="backtest",
        )

        try:
            score = compute_score(
                symbol="BTC",
                timeframe="1h",
                price=price,
                candles=wc,
                candles_15m=[],
                candles_1h=wc,
                fg=_dummy_fg(),
                news=[],
                derivatives=_dummy_deriv(),
                flows=_dummy_flows(),
                macro={"spx": [], "vix": [], "nq": [], "dxy": [], "gold": []},
                intel=intel,
            )

            results.append({
                "timestamp": wc[-1].ts,
                "price": wc[-1].close,
                "confidence": score.confidence,
                "tier": score.tier,
                "action": score.action,
                "direction": score.direction,
                "strategy": score.strategy_type,
                "regime": score.regime,
                "reason_codes": "|".join(score.reason_codes),
            })
        except Exception as e:
            logger.warning(f"Score failed at index {i}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description="BTC Alert Historical Backtest")
    parser.add_argument("--limit", type=int, default=500, help="Number of 1h candles")
    parser.add_argument("--output", type=str, default="reports/backtest_results.csv")
    args = parser.parse_args()

    bm = BudgetManager(".backtest_budget.json")

    print(f"Fetching {args.limit} 1h candles from Kraken...")
    # interval=60 for 1h candles
    candles = _fetch_kraken_ohlc(bm, interval=60, limit=args.limit)

    if len(candles) < 50:
        print(f"ERROR: Only got {len(candles)} candles. Need >= 50.")
        sys.exit(1)

    print(f"Got {len(candles)} candles. Running backtest...")
    results = _run_backtest(candles)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", newline="") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

    total = len(results)
    trades = sum(1 for r in results if r["action"] == "TRADE")
    watches = sum(1 for r in results if r["action"] == "WATCH")
    longs = sum(1 for r in results if r["direction"] == "LONG")
    shorts = sum(1 for r in results if r["direction"] == "SHORT")

    print(f"\n=== BACKTEST RESULTS ===")
    print(f"Total windows: {total}")
    print(f"TRADE: {trades} | WATCH: {watches}")
    print(f"LONG: {longs} | SHORT: {shorts}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
