#!/usr/bin/env python3
"""
Auto-Tuner: Adjusts scoring thresholds based on recent performance.
Reads outcome data from alerts log, calculates win rate and signal selectivity,
then adjusts TIMEFRAME_RULES in config.py if performance warrants it.

Usage: PYTHONPATH=. python tools/auto_tune.py
       PYTHONPATH=. python tools/auto_tune.py --dry-run   (preview only, no writes)
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ALERTS_FILE = BASE_DIR / "logs" / "pid-129-alerts.jsonl"
CONFIG_FILE = BASE_DIR / "config.py"
TUNE_LOG = BASE_DIR / "logs" / "auto_tune.jsonl"


def _load_resolved(days=7):
    """Load resolved alerts from the last N days."""
    if not ALERTS_FILE.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    resolved = []
    try:
        content = ALERTS_FILE.read_text(encoding="utf-8").strip()
        for line in content.split("\n"):
            if not line.strip():
                continue
            try:
                a = json.loads(line)
                if not a.get("resolved"):
                    continue
                ts = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    resolved.append(a)
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception:
        pass
    return resolved


def _current_thresholds():
    """Parse current TIMEFRAME_RULES from config.py."""
    content = CONFIG_FILE.read_text(encoding="utf-8")
    # Extract the TIMEFRAME_RULES block (start with name, end with } on its own line)
    match = re.search(
        r'TIMEFRAME_RULES\s*=\s*\{(.*?)\n\}',
        content,
        re.DOTALL
    )
    if not match:
        # Try finding the first block if the above fails
        match = re.search(r'TIMEFRAME_RULES\s*=\s*\{(.*?)\}', content, re.DOTALL)
        
    if not match:
        print("ERROR: Could not find TIMEFRAME_RULES in config.py")
        sys.exit(1)

    rules = {}
    rule_text = match.group(1).strip()
    # Find each timeframe line
    for tf in ["5m", "15m", "1h"]:
        tf_match = re.search(rf'"{tf}"\s*:\s*(\{{[^}}]+\}})', rule_text)
        if tf_match:
            try:
                blob = tf_match.group(1).replace("'", '"')
                rules[tf] = json.loads(blob)
            except json.JSONDecodeError:
                continue
    return rules


def _write_thresholds(rules):
    """Write updated TIMEFRAME_RULES back to config.py."""
    content = CONFIG_FILE.read_text(encoding="utf-8")

    # Build new block
    lines = []
    for tf in ["5m", "15m", "1h"]:
        if tf not in rules: continue
        r = rules[tf]
        lines.append(
            f'    "{tf}":  {{"min_rr": {r["min_rr"]}, '
            f'"trade_long": {r["trade_long"]}, "trade_short": {r["trade_short"]}, '
            f'"watch_long": {r["watch_long"]}, "watch_short": {r["watch_short"]}}},'
        )
    new_block = "TIMEFRAME_RULES = {\n" + "\n".join(lines) + "\n}"

    # Replace in file
    new_content = re.sub(
        r'TIMEFRAME_RULES\s*=\s*\{[^}]+\}',
        new_block,
        content,
        flags=re.DOTALL
    )
    CONFIG_FILE.write_text(new_content, encoding="utf-8")


def _log_tune(action, details):
    """Append a tune event to the log."""
    TUNE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **details,
    }
    with open(TUNE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Auto-tune scoring thresholds")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--days", type=int, default=7, help="Lookback period in days")
    parser.add_argument("--force", action="store_true", help="Tune even if data is thin")
    args = parser.parse_args()

    resolved = _load_resolved(args.days)
    rules = _current_thresholds()

    if not rules:
        print("ERROR: No rules parsed from config.py.")
        return

    print(f"=== AUTO-TUNER ===")
    print(f"Resolved trades (last {args.days}d): {len(resolved)}")

    # Not enough data to tune
    min_data = 1 if args.force else 5
    if len(resolved) < min_data:
        print(f"Not enough resolved trades to tune. Need >= {min_data}. Skipping.")
        _log_tune("SKIP", {"reason": "insufficient_data", "resolved_count": len(resolved)})
        return

    # Calculate metrics
    wins = [a for a in resolved if a.get("outcome", "").startswith("WIN")]
    losses = [a for a in resolved if a.get("outcome") == "LOSS"]
    win_rate = (len(wins) / len(resolved) * 100) if resolved else 0
    total_r = sum(a.get("r_multiple", 0) for a in resolved)
    avg_r = (total_r / len(resolved)) if resolved else 0

    print(f"Win rate: {win_rate:.1f}%")
    print(f"Total R: {total_r:+.2f}")
    print(f"Avg R: {avg_r:+.2f}")

    # --- Decision logic ---
    adjustment = 0
    reason = ""

    # Case 1: Win rate very high but system too selective
    # Highly aggressive loosening if we have 0 trades in backtest (we can't easily check backtest here, but we can see peak confidence from audit)
    # Since we know peak is 50 and threshold is 78, we are far off.
    
    if win_rate >= 75 and avg_r >= 0:
        adjustment = -4  # Loosen by 4 points (aggressive)
        reason = f"High win rate ({win_rate:.0f}%) with positive R. Loosening to capture more signals."

    # Case 2: Win rate below 50% → Tighten thresholds
    elif win_rate < 50:
        adjustment = 4   # Tighten by 4 points
        reason = f"Low win rate ({win_rate:.0f}%). Tightening to be more selective."

    # Case 3: Negative R despite wins → Something is off, tighten slightly
    elif total_r < 0:
        adjustment = 2
        reason = f"Negative total R ({total_r:+.2f}) despite {win_rate:.0f}% WR. Tightening thresholds."

    # Case 4: System is performing well — no change
    else:
        print(f"System performing within bounds. No adjustment needed.")
        _log_tune("NO_CHANGE", {
            "win_rate": round(win_rate, 1),
            "total_r": round(total_r, 2),
            "avg_r": round(avg_r, 2),
        })
        return

    print(f"\nDecision: {reason}")
    print(f"Adjustment: {adjustment:+d} points")

    # Apply adjustment with guardrails
    GUARD_TRADE_LONG_MIN = 45   # Drop minimum to 45 given peak is 50
    GUARD_TRADE_LONG_MAX = 85   
    GUARD_TRADE_SHORT_MIN = 15  
    GUARD_TRADE_SHORT_MAX = 55  

    old_rules = json.loads(json.dumps(rules))  # Deep copy
    for tf in rules:
        rules[tf]["trade_long"] = max(
            GUARD_TRADE_LONG_MIN,
            min(GUARD_TRADE_LONG_MAX, rules[tf]["trade_long"] + adjustment)
        )
        rules[tf]["trade_short"] = max(
            GUARD_TRADE_SHORT_MIN,
            min(GUARD_TRADE_SHORT_MAX, rules[tf]["trade_short"] - adjustment)
        )
        # Keep watch thresholds 14-16 pts away from trade thresholds
        rules[tf]["watch_long"] = rules[tf]["trade_long"] - 16
        rules[tf]["watch_short"] = rules[tf]["trade_short"] + 16

    print(f"\nProposed changes:")
    for tf in ["5m", "15m", "1h"]:
        if tf not in rules: continue
        old = old_rules[tf]
        new = rules[tf]
        print(f"  {tf}: trade_long {old['trade_long']} → {new['trade_long']}, "
              f"trade_short {old['trade_short']} → {new['trade_short']}")

    if args.dry_run:
        print("\n--dry-run: No changes written.")
        return

    _write_thresholds(rules)
    print(f"\n✅ config.py updated.")

    _log_tune("ADJUSTED", {
        "reason": reason,
        "adjustment": adjustment,
        "win_rate": round(win_rate, 1),
        "total_r": round(total_r, 2),
        "old_rules": old_rules,
        "new_rules": rules,
    })
    print(f"Tune log appended to {TUNE_LOG}")


if __name__ == "__main__":
    main()
