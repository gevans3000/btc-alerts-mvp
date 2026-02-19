# v5 ACTION PLAN — MORNING BRIEFING + SELF-TUNING + AUTOMATION

> **Goal:** Wake up at 6 AM to a Telegram message telling you exactly what BTC is doing
> and what to watch for today. The system tunes itself nightly based on its own results.
> Other agents can trigger the full pipeline with one command.
>
> **3 Phases. Do them in order. Each phase is independent and testable.**

---

## Phase A: Morning Briefing Generator

**What:** A script that reads all current system state and produces a plain-English
briefing with actionable levels. Output goes to Telegram + markdown file + JSON
(so other agents can consume it).

**Time estimate:** 30 minutes.

### Step A.1 — Create `scripts/morning_briefing.py`

Create this file exactly as written. Do not modify any logic.

```python
#!/usr/bin/env python3
"""
Morning Briefing Generator.
Reads latest alert data, intelligence layers, and performance stats.
Produces a plain-English briefing with actionable levels.

Usage: PYTHONPATH=. python scripts/morning_briefing.py
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
if not (BASE_DIR / "logs").exists():
    BASE_DIR = Path.cwd()
ALERTS_FILE = BASE_DIR / "logs" / "pid-129-alerts.jsonl"
AUDIT_FILE = BASE_DIR / "logs" / "audit.jsonl"
PORTFOLIO_FILE = BASE_DIR / "data" / "paper_portfolio.json"
OUTPUT_MD = BASE_DIR / "reports" / "morning_briefing.md"
OUTPUT_JSON = BASE_DIR / "reports" / "morning_briefing.json"


def _load_alerts(hours=24):
    """Load alerts from the last N hours."""
    if not ALERTS_FILE.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    alerts = []
    for line in ALERTS_FILE.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            a = json.loads(line)
            ts = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
            if ts >= cutoff:
                alerts.append(a)
        except (json.JSONDecodeError, KeyError):
            continue
    return alerts


def _load_latest_trace():
    """Get decision_trace from the most recent alert that has one."""
    if not ALERTS_FILE.exists():
        return {}
    lines = ALERTS_FILE.read_text().strip().split("\n")
    for line in reversed(lines):
        try:
            a = json.loads(line)
            if "decision_trace" in a and a["decision_trace"]:
                return a["decision_trace"]
        except (json.JSONDecodeError, KeyError):
            continue
    return {}


def _load_portfolio():
    """Load paper portfolio stats."""
    if not PORTFOLIO_FILE.exists():
        return None
    try:
        return json.loads(PORTFOLIO_FILE.read_text())
    except:
        return None


def _regime_emoji(regime):
    """Return emoji for regime type."""
    return {
        "trend": "📈",
        "range": "📊",
        "chop": "🌊",
        "vol_chop": "⚡",
    }.get(regime, "❓")


def _direction_sentence(direction, confidence):
    """Turn direction + confidence into English."""
    if direction == "LONG" and confidence >= 15:
        return "leaning bullish with moderate conviction"
    elif direction == "LONG":
        return "slightly bullish but low conviction"
    elif direction == "SHORT" and confidence >= 15:
        return "leaning bearish with moderate conviction"
    elif direction == "SHORT":
        return "slightly bearish but low conviction"
    return "neutral with no clear edge"


def _overnight_recap(alerts):
    """Summarize overnight activity."""
    if not alerts:
        return "No signals fired overnight."

    resolved = [a for a in alerts if a.get("resolved")]
    pending = [a for a in alerts if not a.get("resolved")]
    wins = [a for a in resolved if a.get("outcome", "").startswith("WIN")]
    losses = [a for a in resolved if a.get("outcome") == "LOSS"]

    parts = [f"{len(alerts)} signals fired overnight."]
    if resolved:
        parts.append(f"{len(wins)}W / {len(losses)}L resolved.")
    if pending:
        parts.append(f"{len(pending)} still pending.")

    # Best signal
    best = max(alerts, key=lambda a: a.get("confidence", 0))
    parts.append(
        f"Best signal: {best.get('direction')} {best.get('strategy')} "
        f"on {best.get('timeframe')} (confidence {best.get('confidence')})."
    )
    return " ".join(parts)


def generate_briefing():
    """Main briefing generation logic."""
    now = datetime.now(timezone.utc)
    alerts_24h = _load_alerts(hours=24)
    alerts_7d = _load_alerts(hours=168)
    trace = _load_latest_trace()
    portfolio = _load_portfolio()
    ctx = trace.get("context", {})

    # --- Extract intelligence ---
    # Price
    price = trace.get("price", 0.0)

    # Regime
    regime = trace.get("regime", "unknown")
    regime_icon = _regime_emoji(regime)

    # Squeeze
    squeeze = ctx.get("squeeze", "NONE")

    # POC
    vp = ctx.get("volume_profile", {})
    poc = vp.get("poc", 0)
    near_poc = vp.get("near_poc", False)

    # Liquidity
    liq = ctx.get("liquidity", {})
    bid_walls = liq.get("bid_walls", 0)
    ask_walls = liq.get("ask_walls", 0)

    # Macro
    macro = ctx.get("macro_correlation", {})
    dxy = macro.get("dxy", "neutral")
    gold = macro.get("gold", "neutral")

    # Confluence
    conf = ctx.get("confluence", {})
    strength = conf.get("strength", "WEAK")
    bull_count = conf.get("bullish_count", 0)
    bear_count = conf.get("bearish_count", 0)
    net = conf.get("net", 0)

    # Sentiment
    sent = ctx.get("sentiment", {})
    sent_score = sent.get("score", 0.0)

    # Direction from most recent alert
    latest_direction = "NEUTRAL"
    latest_confidence = 0
    if alerts_24h:
        latest = alerts_24h[-1]
        latest_direction = latest.get("direction", "NEUTRAL")
        latest_confidence = latest.get("confidence", 0)

    # --- Performance stats (7-day) ---
    resolved_7d = [a for a in alerts_7d if a.get("resolved")]
    wins_7d = [a for a in resolved_7d if a.get("outcome", "").startswith("WIN")]
    win_rate = (len(wins_7d) / len(resolved_7d) * 100) if resolved_7d else 0
    total_r = sum(a.get("r_multiple", 0) for a in resolved_7d)

    # --- Portfolio ---
    balance = 10000.0
    if portfolio:
        balance = portfolio.get("balance", 10000.0)
    pnl_pct = ((balance - 10000) / 10000) * 100

    # --- Build the briefing ---
    overnight = _overnight_recap(alerts_24h)
    bias_sentence = _direction_sentence(latest_direction, latest_confidence)

    # Actionable sentence
    if strength == "STRONG" and net > 0:
        action = f"Multiple bullish signals agree. Look for long entries on pullbacks to POC (${poc:,.0f}) or bid walls."
    elif strength == "STRONG" and net < 0:
        action = f"Multiple bearish signals agree. Consider shorts on rallies toward ask walls or if VWAP rejects."
    elif squeeze == "SQUEEZE_FIRE":
        action = "Squeeze just fired — expect a sharp directional move. Wait for direction confirmation before entering."
    elif squeeze == "SQUEEZE_ON":
        action = "Squeeze is building. Prepare for a breakout. Set alerts at POC and liquidity walls."
    elif regime == "chop" or regime == "vol_chop":
        action = "Market is choppy. Avoid trend trades. Only consider mean-reversion setups with tight stops."
    elif regime == "range":
        action = "Market is ranging. Fade the extremes. Buy near bid walls, sell near ask walls."
    elif regime == "trend" and latest_direction == "LONG":
        action = f"Trending bullish. Look for pullback entries on 15m/1h. Invalidation below ${poc:,.0f}."
    elif regime == "trend" and latest_direction == "SHORT":
        action = f"Trending bearish. Short on relief rallies. Invalidation above ${poc:,.0f}."
    else:
        action = "No clear edge. Stay flat and wait for confluence to develop."

    briefing_md = f"""# ☀️ Morning Briefing — {now.strftime("%A, %B %d %Y")}

**Generated:** {now.strftime("%Y-%m-%d %H:%M UTC")}

---

## 📍 Current State

- **BTC Price:** ${price:,.2f}
- **Regime:** {regime_icon} {regime.upper()}
- **Squeeze:** {squeeze}
- **System Bias:** {bias_sentence}

## 🧠 Intelligence Snapshot

| Layer | Reading |
|:------|:--------|
| POC (Price of Control) | ${poc:,.0f} ({'**AT POC**' if near_poc else 'away'}) |
| Liquidity | {bid_walls} bid walls / {ask_walls} ask walls |
| DXY | {dxy} |
| Gold | {gold} |
| Sentiment Score | {sent_score:.2f} |
| Confluence | {strength} ({bull_count}🟢 vs {bear_count}🔴, net={net:+d}) |

## 🌙 Overnight Recap

{overnight}

## 📊 7-Day Performance

- **Win Rate:** {win_rate:.0f}% ({len(wins_7d)}W / {len(resolved_7d) - len(wins_7d)}L of {len(resolved_7d)} resolved)
- **Total P&L:** {total_r:+.2f}R
- **Paper Balance:** ${balance:,.2f} ({pnl_pct:+.1f}%)

## 🎯 What To Do Today

> {action}

---
_Auto-generated by EMBER v5. Do not edit._
"""

    # JSON output for other agents
    briefing_json = {
        "generated_utc": now.isoformat(),
        "price": price,
        "regime": regime,
        "squeeze": squeeze,
        "direction": latest_direction,
        "confidence": latest_confidence,
        "poc": poc,
        "near_poc": near_poc,
        "bid_walls": bid_walls,
        "ask_walls": ask_walls,
        "dxy": dxy,
        "gold": gold,
        "confluence_strength": strength,
        "confluence_net": net,
        "sentiment_score": sent_score,
        "win_rate_7d": round(win_rate, 1),
        "total_r_7d": round(total_r, 2),
        "balance": balance,
        "action": action,
        "overnight_recap": overnight,
    }

    return briefing_md, briefing_json


def main():
    # Ensure output directory exists
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)

    briefing_md, briefing_json = generate_briefing()

    # Write markdown
    OUTPUT_MD.write_text(briefing_md, encoding="utf-8")
    print(f"Briefing written to {OUTPUT_MD}")

    # Write JSON
    OUTPUT_JSON.write_text(json.dumps(briefing_json, indent=2), encoding="utf-8")
    print(f"JSON written to {OUTPUT_JSON}")

    # Send to Telegram if configured
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        import httpx
        # Telegram has a 4096 char limit. Send the action + key stats only.
        tg_msg = (
            f"☀️ *EMBER Morning Briefing*\n\n"
            f"BTC: ${briefing_json['price']:,.0f} | {briefing_json['regime'].upper()}\n"
            f"Squeeze: {briefing_json['squeeze']}\n"
            f"Confluence: {briefing_json['confluence_strength']} "
            f"({briefing_json['confluence_net']:+d} net)\n"
            f"POC: ${briefing_json['poc']:,.0f}\n"
            f"7d: {briefing_json['win_rate_7d']:.0f}% WR | {briefing_json['total_r_7d']:+.1f}R\n\n"
            f"🎯 {briefing_json['action']}"
        )
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": tg_msg, "parse_mode": "Markdown"},
                timeout=10,
            )
            print(f"Telegram sent: {resp.status_code}")
        except Exception as e:
            print(f"Telegram failed: {e}")
    else:
        print("Telegram not configured. Printing briefing to console:")
        print(briefing_md)


if __name__ == "__main__":
    main()
```

### Step A.2 — Test the briefing

Run this command. It must not crash and must produce two output files.

```bash
PYTHONPATH=. python scripts/morning_briefing.py
```

Verify:
1. `reports/morning_briefing.md` exists and contains readable content
2. `reports/morning_briefing.json` exists and is valid JSON
3. Console output shows either Telegram success or the printed briefing
4. The "What To Do Today" section contains a specific, actionable sentence (not "N/A")

### Step A.3 — Smoke test with a fresh cycle

Run the full pipeline to ensure fresh data flows into the briefing:

```bash
PYTHONPATH=. python app.py --once
PYTHONPATH=. python scripts/morning_briefing.py
```

Open `reports/morning_briefing.md` and confirm:
- Price is current (within the last few minutes)
- Intelligence table has actual values, not all zeros
- Overnight recap counts at least 1 signal

**Phase A is done when the briefing prints and all fields are populated.**

---

## Phase B: Threshold Auto-Tuner

**What:** A nightly script that reads the system's own outcome data and adjusts
`TIMEFRAME_RULES` thresholds in `config.py` if performance warrants it.
This is how the system improves itself over time.

**Time estimate:** 30 minutes.

### Step B.1 — Create `tools/auto_tune.py`

Create this file exactly as written. Do not modify any logic.

```python
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
    for line in ALERTS_FILE.read_text().strip().split("\n"):
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
    return resolved


def _current_thresholds():
    """Parse current TIMEFRAME_RULES from config.py."""
    content = CONFIG_FILE.read_text()
    # Extract the TIMEFRAME_RULES block
    match = re.search(
        r'TIMEFRAME_RULES\s*=\s*\{([^}]+)\}',
        content,
        re.DOTALL
    )
    if not match:
        print("ERROR: Could not find TIMEFRAME_RULES in config.py")
        sys.exit(1)

    rules = {}
    for line in match.group(1).strip().split("\n"):
        line = line.strip().rstrip(",")
        if not line or line.startswith("#"):
            continue
        # Parse: "5m":  {"min_rr": 1.35, "trade_long": 78, ...}
        tf_match = re.match(r'"(\w+)":\s*(\{.+\})', line)
        if tf_match:
            tf = tf_match.group(1)
            rules[tf] = json.loads(tf_match.group(2).replace("'", '"'))
    return rules


def _write_thresholds(rules):
    """Write updated TIMEFRAME_RULES back to config.py."""
    content = CONFIG_FILE.read_text()

    # Build new block
    lines = []
    for tf in ["5m", "15m", "1h"]:
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
    CONFIG_FILE.write_text(new_content)


def _log_tune(action, details):
    """Append a tune event to the log."""
    TUNE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **details,
    }
    with open(TUNE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Auto-tune scoring thresholds")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--days", type=int, default=7, help="Lookback period in days")
    args = parser.parse_args()

    resolved = _load_resolved(args.days)
    rules = _current_thresholds()

    print(f"=== AUTO-TUNER ===")
    print(f"Resolved trades (last {args.days}d): {len(resolved)}")

    # Not enough data to tune
    if len(resolved) < 5:
        print("Not enough resolved trades to tune. Need >= 5. Skipping.")
        _log_tune("SKIP", {"reason": "insufficient_data", "resolved_count": len(resolved)})
        return

    # Calculate metrics
    wins = [a for a in resolved if a.get("outcome", "").startswith("WIN")]
    losses = [a for a in resolved if a.get("outcome") == "LOSS"]
    win_rate = len(wins) / len(resolved) * 100
    total_r = sum(a.get("r_multiple", 0) for a in resolved)
    avg_r = total_r / len(resolved)

    print(f"Win rate: {win_rate:.1f}%")
    print(f"Total R: {total_r:+.2f}")
    print(f"Avg R: {avg_r:+.2f}")

    # --- Decision logic ---
    adjustment = 0
    reason = ""

    # Case 1: Win rate very high but system too selective (nothing triggers in backtest)
    # → Loosen thresholds to get more signals
    if win_rate >= 75 and avg_r > 0:
        adjustment = -2  # Lower trade_long, raise trade_short → MORE signals
        reason = f"High win rate ({win_rate:.0f}%) with positive R. Loosening to capture more."

    # Case 2: Win rate below 50% → Tighten thresholds
    elif win_rate < 50:
        adjustment = 2   # Raise trade_long, lower trade_short → FEWER signals
        reason = f"Low win rate ({win_rate:.0f}%). Tightening to be more selective."

    # Case 3: Negative R despite wins → Something is off, tighten slightly
    elif total_r < 0:
        adjustment = 1
        reason = f"Negative total R ({total_r:+.2f}) despite {win_rate:.0f}% WR. Slight tightening."

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
    GUARD_TRADE_LONG_MIN = 60   # Never go below 60 for trade_long
    GUARD_TRADE_LONG_MAX = 85   # Never go above 85
    GUARD_TRADE_SHORT_MIN = 15  # Never go below 15 for trade_short
    GUARD_TRADE_SHORT_MAX = 40  # Never go above 40

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
```

### Step B.2 — Test with dry-run

This MUST be run with `--dry-run` first to verify the logic without touching `config.py`.

```bash
PYTHONPATH=. python tools/auto_tune.py --dry-run
```

Verify:
1. It prints the number of resolved trades
2. It prints the win rate and total R
3. It prints a decision (SKIP, NO_CHANGE, or an adjustment)
4. If an adjustment is proposed, the `Proposed changes` table shows valid numbers
5. It says `--dry-run: No changes written.`

### Step B.3 — Test for real

Run without `--dry-run`. Then verify config.py was updated correctly.

```bash
PYTHONPATH=. python tools/auto_tune.py
```

Verify:
1. `config.py` still has valid `TIMEFRAME_RULES` (open and check)
2. `logs/auto_tune.jsonl` exists and has the logged event
3. Run the validation: `PYTHONPATH=. python -c "from config import validate_config; validate_config(); print('OK')"`

### Step B.4 — Test the guardrails

Run the auto-tuner 20 times in a row. Thresholds must stay within guardrails.

```bash
for ($i=0; $i -lt 20; $i++) { python tools/auto_tune.py }
python -c "from config import validate_config; validate_config(); print('Guardrails held')"
```

If `validate_config()` throws, the guardrails are broken. Fix the min/max constants.

**Phase B is done when auto_tune.py runs without crashing and config.py stays valid.**

---

## Phase C: Automation Pipeline

**What:** A single PowerShell script that chains the entire pipeline together,
plus a Windows Scheduled Task to run it at 6 AM ET daily.

**Time estimate:** 15 minutes.

### Step C.1 — Create `scripts/pipeline.ps1`

This script runs the full nightly + morning pipeline. It is designed to be
called by Windows Task Scheduler, by other agents, or manually.

```powershell
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

# Step 1: Run one alert cycle (collects data, scores, sends alerts)
Write-Host "[$timestamp] Step 1: Alert cycle..." -ForegroundColor Yellow
python app.py --once
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: app.py exited with code $LASTEXITCODE" -ForegroundColor Red
}

# Step 2: Generate scorecard (performance stats)
Write-Host "[$timestamp] Step 2: Scorecard..." -ForegroundColor Yellow
python scripts/pid-129/generate_scorecard.py

# Step 3: Generate dashboard (HTML report)
Write-Host "[$timestamp] Step 3: Dashboard..." -ForegroundColor Yellow
python scripts/pid-129/generate_dashboard.py

# Step 4: Auto-tune thresholds (self-improvement)
Write-Host "[$timestamp] Step 4: Auto-tune..." -ForegroundColor Yellow
python tools/auto_tune.py

# Step 5: Generate morning briefing (actionable summary)
Write-Host "[$timestamp] Step 5: Morning briefing..." -ForegroundColor Yellow
python scripts/morning_briefing.py

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$timestamp] === EMBER Pipeline Complete ===" -ForegroundColor Green
```

### Step C.2 — Test the pipeline

Run the full pipeline once manually:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/pipeline.ps1
```

Verify:
1. All 5 steps print without fatal errors
2. `reports/morning_briefing.md` was updated (check the timestamp inside)
3. `reports/pid-129-daily-scorecard.md` was updated
4. `dashboard.html` was updated
5. `logs/auto_tune.jsonl` has a new entry

### Step C.3 — Register Windows Scheduled Task

Create a scheduled task that runs the pipeline at 6:00 AM ET every day.

**Run this command in an ELEVATED (Admin) PowerShell prompt:**

```powershell
$ProjectRoot = "c:\Users\lovel\trading\btc-alerts-mvp"
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\pipeline.ps1`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At "6:00AM"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "EMBER_MorningPipeline" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Runs BTC alert pipeline and generates morning briefing at 6 AM" `
    -RunLevel Limited
```

### Step C.4 — Verify the scheduled task

```powershell
Get-ScheduledTask -TaskName "EMBER_MorningPipeline" | Select-Object TaskName, State, LastRunTime
```

Verify:
1. Task shows as `Ready`
2. You can manually trigger it: `Start-ScheduledTask -TaskName "EMBER_MorningPipeline"`
3. After triggering, check `reports/morning_briefing.md` got updated

**Phase C is done when the scheduled task exists and runs the full pipeline successfully.**

---

## Final Verification Checklist

Run all of these. Every one must pass.

```bash
# Phase A — Briefing
PYTHONPATH=. python scripts/morning_briefing.py
# Check: reports/morning_briefing.md and .json exist

# Phase B — Auto-tuner
PYTHONPATH=. python tools/auto_tune.py --dry-run
# Check: prints stats and a decision

# Phase C — Full pipeline
powershell -ExecutionPolicy Bypass -File scripts/pipeline.ps1
# Check: all 5 steps complete

# Regression — old tests still pass
PYTHONPATH=. python -m pytest tests/test_volume_profile.py tests/test_liquidity.py tests/test_macro_correlation.py tests/test_confluence.py -v

# Config validation
PYTHONPATH=. python -c "from config import validate_config; validate_config(); print('Config OK')"
```

---

## Definition of Done (v5.0)

- [ ] `scripts/morning_briefing.py` produces markdown + JSON + sends Telegram
- [ ] Briefing has: price, regime, POC, liquidity, DXY, confluence, action sentence
- [ ] `tools/auto_tune.py` reads outcomes and adjusts `TIMEFRAME_RULES`
- [ ] Auto-tuner has guardrails (min/max bounds on thresholds)
- [ ] `logs/auto_tune.jsonl` records every tuning decision
- [ ] `scripts/pipeline.ps1` chains all steps: cycle → scorecard → dashboard → tune → briefing
- [ ] Windows Scheduled Task `EMBER_MorningPipeline` registered for 6 AM ET
- [ ] Other agents can trigger via: `PYTHONPATH=. python scripts/morning_briefing.py`
- [ ] Other agents can read: `reports/morning_briefing.json` for structured data
- [ ] All existing tests pass
- [ ] Zero paid APIs

---

_v5.0: 3 phases. 1 scheduled task. Morning briefing + self-tuning engine. Ship it._
