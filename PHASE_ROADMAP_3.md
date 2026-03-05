# BTC Alerts MVP — Roadmap Part 3: Calibration, Edge & Risk

> **Instructions for AI agents:** Each phase below is self-contained. Complete phases in order. Every task specifies exact files, functions, and acceptance criteria. Run `PYTHONPATH=. python -m pytest tests/ -v` after each phase to verify nothing breaks. Read CLAUDE.md before starting.

---

## Current State (Baseline)

- Phases 1–28: COMPLETE
- A+ signals are profitable (WR=66.7%, AvgR=+0.166)
- B tier loses money (WR=42.2%, AvgR=-0.155) — executor already gates on A+ only
- Recipes fire correctly (HTF_REVERSAL, BOS_CONTINUATION, VOL_EXPANSION)
- R:R values are realistic (3.8–4.2 range)
- 13+ intelligence probes operational in `intelligence/`
- Signal pipeline: `app.py` → `engine.py` → probes → `logs/pid-129-alerts.jsonl`

---

## Phase 29: Confidence Calibration Fix [COMPLETE]

**Problem:** The 61–80 confidence bin loses money (-0.37R avg) while 41–60 wins (+0.22R). Higher confidence should mean higher profitability.

**Goal:** Recalibrate so confidence correlates with actual win rate.

### Task 29.1 — Add calibration analysis script [COMPLETE]

Create `tools/calibration_report.py`:

```python
"""
Read logs/pid-129-alerts.jsonl.
Group alerts by confidence bins: 0-20, 21-40, 41-60, 61-80, 81-100.
For each bin, compute: count, win_rate, avg_r, total_r.
Print a table. Also output to reports/calibration_report.json.
Only include alerts where outcome is not None (resolved trades).
"""
```

**File:** `tools/calibration_report.py` (new file)
**Reads:** `logs/pid-129-alerts.jsonl`
**Writes:** `reports/calibration_report.json`
**Test:** Run the script. It should print a table with 5 bins. Verify the numbers match the JSONL data.

### Task 29.2 — Fix scoring inversion in engine.py [COMPLETE]

After running the calibration report, identify which probes contribute most to the 61–80 bin. The fix:

**File:** `config.py`
**What to change:** In the `CONFLUENCE_RULES` dict, add a new key:

```python
CONFLUENCE_RULES = {
    "A_PLUS_MIN_PROBES": 5,
    "A_PLUS_MIN_RUBRIC": 6.0,
    "B_MIN_PROBES": 3,
    "B_MIN_RUBRIC": 4.0,
    # ADD THIS:
    "CONFIDENCE_FLOOR_FOR_TRADE": 45,   # alerts below this confidence → NO-TRADE
    "CONFIDENCE_CAP": 85,               # cap raw confidence to prevent overconfidence
}
```

**File:** `engine.py` — in the function that computes final confidence (search for `normalize` or `SCORE_MULTIPLIER = 7.0`), add after the normalization step:

```python
# Cap confidence to prevent overconfidence
confidence = min(confidence, CONFLUENCE_RULES.get("CONFIDENCE_CAP", 85))
```

**Acceptance criteria:**
- `python tools/calibration_report.py` runs without errors
- Confidence values in new alerts never exceed 85
- Existing tests still pass

---

## Phase 30: Circuit Breakers (Risk Safety) [COMPLETE]

**Problem:** No protection against consecutive losses draining the account.

**Goal:** Automatically pause trading after hitting loss limits.

### Task 30.1 — Daily loss circuit breaker [COMPLETE]

**File:** `tools/executor.py`
**What to add:** Before executing any trade, check cumulative R for today:

```python
def _check_circuit_breaker(self) -> bool:
    """Return True if trading is allowed, False if breaker tripped."""
    import json
    from datetime import datetime, date

    DAILY_LOSS_LIMIT_R = -3.0  # halt after losing 3R in one day

    try:
        with open("data/paper_portfolio.json", "r") as f:
            portfolio = json.load(f)
        today = date.today().isoformat()
        today_trades = [
            t for t in portfolio.get("closed_trades", [])
            if t.get("close_time", "").startswith(today)
        ]
        daily_r = sum(t.get("realized_r", 0) for t in today_trades)
        if daily_r <= DAILY_LOSS_LIMIT_R:
            print(f"CIRCUIT BREAKER: Daily R = {daily_r:.2f}, limit = {DAILY_LOSS_LIMIT_R}. Halting.")
            return False
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # no portfolio file = no trades = OK to trade
    return True
```

Call `_check_circuit_breaker()` at the top of the execute method. If it returns `False`, log the skip and return without trading.

### Task 30.2 — Max open positions cap [COMPLETE]

**File:** `tools/executor.py`
**What to add:** Before opening a new position, count current open positions:

```python
MAX_OPEN_POSITIONS = 3  # never have more than 3 positions open at once
```

Check `len(portfolio.get("open_trades", []))` and skip if >= MAX_OPEN_POSITIONS.

**Acceptance criteria:**
- After -3R in a day, executor logs "CIRCUIT BREAKER" and refuses new trades
- Never more than 3 positions open simultaneously
- Existing tests still pass

---

## Phase 31: CVD (Cumulative Volume Delta) Probe

**Problem:** Taker ratio alone is too blunt. CVD divergence is a high-alpha reversal signal.

**Goal:** Add CVD calculation and use it as a confirmation/veto signal.

### Task 31.1 — Add CVD to flows collector

**File:** `collectors/flows.py`
**What to add:** A new function (or extend the existing fetch function):

```python
def compute_cvd(trades_or_candles: list) -> dict:
    """
    Compute Cumulative Volume Delta from recent candle data.

    For each candle:
      buy_volume = volume * (close - low) / (high - low)  if high != low else volume * 0.5
      sell_volume = volume - buy_volume
      delta = buy_volume - sell_volume

    CVD = cumulative sum of delta over the window.

    Returns:
        {
            "cvd_value": float,         # current CVD
            "cvd_slope": float,         # slope of last 5 CVD values (positive = buying pressure)
            "cvd_price_divergence": bool # True if price rising but CVD falling, or vice versa
        }
    """
```

Use the OHLCV candle data that `collectors/price.py` already fetches. The CVD probe should take the same candles list.

### Task 31.2 — Add CVD intelligence probe

**File:** `intelligence/cvd_probe.py` (new file)

```python
"""
CVD Intelligence Probe

Input: CVD dict from collectors/flows.py compute_cvd()
Output: (points: int, signal: bool)

Rules:
- CVD divergence from price (price up, CVD down or vice versa): -2 points (bearish/bullish warning)
- Strong CVD slope aligned with direction: +1 point
- No divergence, neutral slope: 0 points
"""
```

### Task 31.3 — Wire CVD into engine.py

**File:** `engine.py`
**Where:** In the section where other probes are called (near lines 276–349), add:

```python
# CVD probe
try:
    from intelligence.cvd_probe import score_cvd
    cvd_data = flow_snapshot.get("cvd", {})  # or compute from candles
    cvd_pts, cvd_signal = score_cvd(cvd_data, direction)
    points += cvd_pts
    context["cvd"] = cvd_data
except Exception as e:
    degraded.append("cvd")
```

**File:** `config.py` — add `"cvd"` to `INTELLIGENCE_FLAGS` dict (default `True`).

**Acceptance criteria:**
- `from intelligence.cvd_probe import score_cvd` works
- CVD data appears in alert `decision_trace.context.cvd`
- If CVD data unavailable, probe degrades gracefully (no crash)
- Existing tests still pass

---

## Phase 32: Probe Performance Attribution

**Problem:** We don't know which probes actually predict winners. Some may be noise.

**Goal:** Track per-probe hit rates and auto-weight accordingly.

### Task 32.1 — Probe attribution tracker

**File:** `tools/probe_attribution.py` (new file)

```python
"""
Read logs/pid-129-alerts.jsonl.
For each resolved trade (outcome != None):
  - Look at decision_trace.codes to see which probes fired
  - Track per-probe: times_fired, times_winner, times_loser, avg_r_when_fired

Output: reports/probe_attribution.json with a dict like:
{
    "structure_bos": {"fired": 45, "wins": 28, "losses": 17, "win_rate": 0.622, "avg_r": 0.31},
    "squeeze_fire": {"fired": 12, "wins": 4, "losses": 8, "win_rate": 0.333, "avg_r": -0.18},
    ...
}

Also print a sorted table showing best→worst probes.
"""
```

### Task 32.2 — Dashboard probe leaderboard

**File:** `scripts/pid-129/generate_dashboard.py`
**What to add:** A new section in the generated HTML that reads `reports/probe_attribution.json` and shows a small table:

| Probe | Fires | WR% | Avg R |
|-------|-------|-----|-------|

Color green if WR > 55%, red if WR < 40%, white otherwise.

**Acceptance criteria:**
- `python tools/probe_attribution.py` runs and creates the JSON report
- Dashboard shows the probe leaderboard table
- Existing tests still pass

---

## Phase 33: Liquidation Level Estimates

**Problem:** Not knowing where liquidation clusters sit means missing key price magnets.

**Goal:** Estimate liquidation levels from OI and funding data.

### Task 33.1 — Liquidation estimator

**File:** `intelligence/liquidation_estimate.py` (new file)

```python
"""
Liquidation Level Estimator

Uses: current price, funding rate, open interest from collectors/derivatives.py

Estimates where leveraged positions would get liquidated:
  - For longs at common leverages (10x, 25x, 50x):
      liq_price = entry * (1 - 1/leverage + maintenance_margin)
  - For shorts at common leverages:
      liq_price = entry * (1 + 1/leverage - maintenance_margin)

Assumes entry price = current price (recent entries).
maintenance_margin = 0.005 (0.5%, standard for BTC perps)

Returns:
{
    "long_liq_levels": [{"leverage": 10, "price": 95000}, ...],
    "short_liq_levels": [{"leverage": 10, "price": 105000}, ...],
    "nearest_liq_cluster": "above" or "below",  # where most liquidations would happen
    "magnetic_direction": "LONG" or "SHORT"      # price tends to move toward liquidity
}

Scoring:
  - If magnetic_direction aligns with trade direction: +1 point
  - If nearest_liq_cluster is very close (<1% from price): +1 point (high conviction move coming)
  - If magnetic_direction opposes trade direction: -1 point
"""
```

### Task 33.2 — Wire into engine.py

Same pattern as CVD probe (Task 31.3). Add to the probe call section, wrap in try/except, append to `degraded` on failure.

**Acceptance criteria:**
- Liquidation estimates appear in `decision_trace.context.liquidation`
- No crash if derivatives data is missing
- Existing tests still pass

---

## Phase 34: Walk-Forward Validation for Auto-Tune

**Problem:** `tools/auto_tune.py` adjusts thresholds nightly but could overfit to recent noise.

**Goal:** Validate proposed changes against out-of-sample data before applying.

### Task 34.1 — Add validation step to auto_tune.py

**File:** `tools/auto_tune.py`
**What to change:** Before writing new values to `dna/dna.json`, add a validation step:

```python
def validate_proposed_changes(current_rules: dict, proposed_rules: dict) -> bool:
    """
    Sanity checks before applying auto-tune changes:
    1. No threshold changes more than 15% from current value
    2. trade_long > watch_long (for all timeframes)
    3. trade_short > watch_short (for all timeframes)
    4. min_rr stays between 1.0 and 2.5
    If any check fails, log the violation and return False (keep current values).
    """
```

Call this function before the final write. If it returns `False`, skip the update and log why.

**Acceptance criteria:**
- Auto-tune with extreme values (e.g., min_rr=0.5) gets rejected
- Normal auto-tune still applies correctly
- Existing tests still pass

---

## Phase 35: Telegram Alerts for A+ Signals

**Problem:** Must watch the dashboard to catch A+ signals.

**Goal:** Push A+ alerts to Telegram so you never miss a high-conviction setup.

### Task 35.1 — Telegram notifier

**File:** `tools/telegram_notify.py` (new file)

```python
"""
Send A+ alerts to Telegram.

Requires environment variables:
  TELEGRAM_BOT_TOKEN — from @BotFather
  TELEGRAM_CHAT_ID — your chat/group ID

Usage: called from app.py after an A+ alert is generated.

Message format:
  🟢 LONG BTC 5m | Confidence: 78 | A+
  Entry: $97,500 | TP1: $98,200 | TP2: $99,100
  Invalidation: $96,800 | R:R: 3.86
  Strategy: BOS_CONTINUATION
  Probes: structure_bos, squeeze_fire, cvd_aligned

If env vars not set, log a debug message and skip (no crash).
"""

import os
import json
import urllib.request

def send_alert(alert: dict) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    direction_emoji = "🟢" if alert.get("direction") == "LONG" else "🔴"
    msg = (
        f"{direction_emoji} {alert['direction']} {alert['symbol']} {alert['timeframe']} "
        f"| Conf: {alert['confidence']} | {alert['tier']}\n"
        f"Entry: ${alert['entry_price']:,.0f} | TP1: ${alert['tp1']:,.0f} | TP2: ${alert['tp2']:,.0f}\n"
        f"Invalidation: ${alert['invalidation']:,.0f} | R:R: {alert['rr_ratio']:.2f}\n"
        f"Strategy: {alert.get('strategy', 'N/A')}"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False
```

### Task 35.2 — Wire into app.py

**File:** `app.py`
**Where:** After the alert is written to `logs/pid-129-alerts.jsonl`, add:

```python
# Send Telegram notification for A+ alerts
if alert.get("tier") == "A+" and alert.get("action") == "TRADE":
    try:
        from tools.telegram_notify import send_alert
        send_alert(alert)
    except Exception:
        pass  # non-critical, never crash the main loop
```

**Acceptance criteria:**
- With `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` set, A+ alerts send to Telegram
- Without env vars, no crash, just silent skip
- Existing tests still pass

---

## Phase 36: Position Stagger & Dynamic R:R

**Problem:** Multiple positions opening at the same price with identical R:R (the "10 identical setups" issue).

**Goal:** Stagger entries and vary R:R per position.

### Task 36.1 — Duplicate entry prevention

**File:** `tools/executor.py`
**What to add:** Before opening a new trade, check if there's already an open trade in the same direction within 0.3% of the entry price:

```python
def _is_duplicate_entry(self, alert: dict, open_trades: list) -> bool:
    """Return True if a similar position already exists."""
    for trade in open_trades:
        if trade.get("direction") != alert.get("direction"):
            continue
        entry_diff = abs(trade["entry_price"] - alert["entry_price"]) / alert["entry_price"]
        if entry_diff < 0.003:  # within 0.3%
            return True
    return False
```

### Task 36.2 — Timeframe-based R:R variation

**File:** `config.py` — the `TP_MULTIPLIERS` dict already has per-regime values. Add per-timeframe adjustments:

```python
TIMEFRAME_TP_SCALE = {
    "5m":  0.8,   # tighter targets on 5m
    "15m": 1.0,   # baseline
    "1h":  1.3,   # wider targets on 1h
}
```

**File:** `engine.py` — where TP levels are calculated (search for `tp1` and `tp2` assignments), multiply the ATR-based target by `TIMEFRAME_TP_SCALE[timeframe]`.

**Acceptance criteria:**
- No two open positions in the same direction within 0.3% of each other
- 5m trades have tighter TP targets, 1h trades have wider ones
- Existing tests still pass

---

## Implementation Priority Summary

| Phase | What | Effort | Impact | Depends On |
|-------|------|--------|--------|------------|
| 29 | Confidence calibration fix | Small | **Critical** | — |
| 30 | Circuit breakers (risk safety) | Small | **Critical** | — |
| 31 | CVD probe (new alpha signal) | Medium | **High** | — |
| 32 | Probe attribution tracking | Medium | **High** | — |
| 33 | Liquidation level estimates | Medium | **Medium** | — |
| 34 | Walk-forward auto-tune guard | Small | **High** | — |
| 35 | Telegram A+ notifications | Small | **Medium** | — |
| 36 | Position stagger & dynamic R:R | Small | **High** | 30 |

**Phases 29 and 30 are the most important.** They fix real problems that are currently losing money or risking blowup. Do them first.

**Phases 31–33 add new edge.** CVD divergence and liquidation clusters are among the highest-alpha signals in crypto.

**Phases 34–36 are hardening.** They prevent overfitting, ensure you never miss signals, and stop duplicate entries.

---

## Rules for Implementing Agents

1. **Read CLAUDE.md first.** It has the full architecture reference.
2. **Read the file you're editing** before making changes. Understand the existing patterns.
3. **Follow existing code style.** Look at how other probes in `intelligence/` are structured — match that pattern.
4. **Wrap all new probe calls in try/except** and append to the `degraded` list on failure. This is how every probe works.
5. **Run tests after every change:** `PYTHONPATH=. python -m pytest tests/ -v`
6. **Run one cycle to verify:** `python app.py --once`
7. **Never hardcode thresholds** — put them in `config.py`.
8. **New files go in the right directory:** probes in `intelligence/`, data fetchers in `collectors/`, analysis scripts in `tools/`, server code in `scripts/pid-129/`.

---

_v5.0 | EMBER | Calibration, Risk, Alpha & Hardening Roadmap_
