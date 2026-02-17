# BTC Alerts MVP — Action Plan v1.3: From Signals to Profit

**Project:** PID-129 — EMBER Progressive Capability Loop
**Created:** 2026-02-17
**Current Version:** v1.2 (Signal Latching & Strategic Gating)
**Target Version:** v2.0 (Self-Validating Paper Trading System)

---

## Executive Summary

The system currently generates trading signals with positive expectancy (~0.33R on 5m),
but the backtest methodology is flawed (higher timeframes evaluated too frequently),
there is no outcome tracking, and no automated paper trading. This plan addresses
every gap in a strict dependency order — each phase unlocks the next.

### Current State (Honest Assessment)

| Component            | Status | Confidence |
|:---------------------|:-------|:-----------|
| Price Data Collection | ✅ Working | HIGH — Kraken + Bybit fallback |
| Engine Logic (v1.2)  | ✅ Working | MEDIUM — logic is sound but under-filtered |
| Signal Latching      | ✅ Working | HIGH — prevents spam on same candle |
| Backtest Tool        | ⚠️ Flawed | LOW — HT frames evaluated on 5m cadence |
| Outcome Tracking     | ❌ Missing | N/A |
| Paper Trading        | ❌ Missing | N/A |
| Equity Dashboard     | ❌ Missing | N/A |
| Regime Filtering     | ⚠️ Weak | LOW — too many signals pass through |
| HTF Bias Lock        | ❌ Missing | N/A |

### Target State (v2.0)

A system where:
1. The backtest produces **trustworthy** metrics (verified signal counts per timeframe).
2. Each alert is **tracked to outcome** (Win/Loss/Breakeven with R-multiple).
3. A **paper trading engine** runs 24/7, simulating execution with virtual capital.
4. A **live dashboard** shows equity curve, win rate, and drawdown in real time.
5. Signal quality is **high enough** that a human could actually trade the alerts profitably.

---

## Phase 1: Backtest Fidelity (TRUST THE NUMBERS)

**Priority:** 🔴 CRITICAL — Everything downstream depends on accurate metrics.
**Estimated Time:** 1–2 hours
**Files:** `tools/replay.py`, `tools/run_backtest.py`

### Problem

The current replay loop iterates over every 5m candle and evaluates ALL timeframes
on each iteration. This means:
- The **1h strategy** is scored 12x per hour (once per 5m bar) instead of 1x.
- The **15m strategy** is scored 3x per 15m bar instead of 1x.
- Result: 423 "1h alerts" in 3 days — should be ~30-50 at most.

### Tasks

#### 1.1 — Timeframe-Cadence Gating in Replay Loop
- [ ] Add cadence tracking to `replay_symbol_timeframe()`.
- [ ] For timeframe "15m": only evaluate when the candle index is a multiple of 3 
      (every 3rd 5m candle = one 15m bar).
- [ ] For timeframe "1h": only evaluate when the candle index is a multiple of 12
      (every 12th 5m candle = one 1h bar).
- [ ] For timeframe "5m": evaluate every candle (no change).

#### 1.2 — Context Stream Accuracy
- [ ] Verify `_context_streams()` in `replay.py` correctly aggregates candles.
- [ ] Ensure the 15m context stream for a 5m replay only updates on 15m boundaries.
- [ ] Ensure the 1h context stream for a 5m/15m replay only updates on 1h boundaries.

#### 1.3 — Backtest Validation
- [ ] Run the corrected backtest and compare signal counts:
  - **5m:** Expect 10-30 alerts per 3 days (similar to current).
  - **15m:** Expect 20-60 alerts per 3 days (down from 268).
  - **1h:** Expect 10-40 alerts per 3 days (down from 423).
- [ ] If signal counts are still unreasonably high, investigate engine thresholds.
- [ ] Document the corrected metrics in this file under "Evidence" section.

#### 1.4 — Extended History
- [ ] Investigate fetching more than 721 candles (current Kraken limit).
- [ ] Try Bybit for deeper history (up to 1000 candles = ~3.5 days).
- [ ] Consider fetching 1h candles directly from exchange APIs for longer history
      (720 x 1h candles = 30 days of data).

### Success Criteria
- [ ] 1h alert count drops below 50 per 3-day window.
- [ ] Win rate metrics are recalculated on correct cadence.
- [ ] Backtest report is trusted enough to make config decisions from.

### Evidence
_(To be filled after completion)_

---

## Phase 2: Signal Quality — The Regime Governor

**Priority:** 🟠 HIGH — Reduces noise, improves win rate.
**Estimated Time:** 2–3 hours
**Files:** `engine.py`, `config.py`, `utils.py`
**Depends on:** Phase 1 (need accurate metrics to measure improvement)

### Problem

The engine fires signals in ALL market conditions. During low-volatility "chop" zones,
signals are essentially coin flips. We need a "Governor" that throttles signal generation
during unfavorable conditions.

### Tasks

#### 2.1 — Regime Classification Improvement
- [ ] Review `_regime()` function in engine.py.
- [ ] Add a "CHOP" regime that is distinct from "range" — characterized by:
  - ADX < 20 AND ATR percentile < 30 (low volatility, no trend).
  - In CHOP regime, automatically raise confidence thresholds by +15 points.
- [ ] Add regime persistence: require 3 consecutive candles in a regime before switching.
      This prevents regime "flickering" (trend → chop → trend on adjacent candles).

#### 2.2 — HTF Bias Lock
- [ ] Implement Higher Timeframe Direction Lock:
  - 5m signals MUST agree with 15m trend direction (or be NEUTRAL).
  - 15m signals MUST agree with 1h trend direction (or be NEUTRAL).
  - If a 5m wants to go LONG but 1h trend is clearly SHORT → auto-SKIP.
- [ ] Add a `htf_conflict` blocker that logs when this filtering occurs.
- [ ] Make the lock configurable in `config.py` (can be disabled for testing).

#### 2.3 — Session-Aware Filtering
- [ ] Review `SESSION_WEIGHTS` in config.py.
- [ ] Add a "dead zone" filter: suppress ALL signals during the following periods:
  - Weekday 20:00-22:00 UTC (transition between US close and Asia open).
  - Weekend: raise all thresholds by +10 (lower liquidity = less reliable signals).
- [ ] Make dead zones configurable.

#### 2.4 — Volume Confirmation Gate
- [ ] Require volume to be above the 20-period average for any TRADE-level signal.
- [ ] WATCH signals can fire on low volume, but TRADE requires volume confirmation.
- [ ] Log when volume gate suppresses a signal.

### Success Criteria
- [ ] Re-run backtest (Phase 1 corrected version).
- [ ] Win rate improves from ~50% to ≥55% on all timeframes.
- [ ] Total alert count reduces by ≥40% compared to Phase 1 baseline.
- [ ] No increase in missed "obvious" winning setups (spot-check 10 trades).

### Evidence
_(To be filled after completion)_

---

## Phase 3: Outcome Tracking — The Memory

**Priority:** 🟠 HIGH — Without this, we can never know if we're winning.
**Estimated Time:** 2–3 hours
**Files:** `app.py`, new `tools/outcome_tracker.py`
**Depends on:** Phase 1 (accurate signals), Phase 2 (quality signals)

### Problem

The system sends alerts but never looks back to see if they were right. We need a
closed feedback loop: Alert → Track → Evaluate → Learn.

### Tasks

#### 3.1 — Alert Persistence with Outcome Fields
- [ ] Ensure every non-SKIP alert is written to `logs/pid-129-alerts.jsonl`.
- [ ] Add outcome fields to the JSONL schema:
  ```json
  {
    "alert_id": "uuid",
    "timestamp": "ISO8601",
    "symbol": "BTC",
    "timeframe": "5m",
    "direction": "LONG",
    "entry_price": 60000.0,
    "tp1": 60500.0,
    "tp2": 61000.0,
    "invalidation": 59500.0,
    "confidence": 78,
    "tier": "A+",
    "outcome": null,
    "outcome_timestamp": null,
    "outcome_price": null,
    "r_multiple": null,
    "resolved": false
  }
  ```

#### 3.2 — Outcome Resolution Engine
- [ ] Create `tools/outcome_tracker.py`.
- [ ] On each cycle (or on-demand), scan all unresolved alerts in the JSONL.
- [ ] For each unresolved alert, fetch the current BTC price and check:
  - Did price hit TP1? → Mark as WIN (1R or actual R-multiple).
  - Did price hit TP2? → Mark as BIG WIN (2R+).
  - Did price hit Invalidation (SL)? → Mark as LOSS (-1R).
  - Has it been open for > max_duration (e.g., 4h for 5m, 24h for 1h)? → Mark as TIMEOUT (0R).
- [ ] Write the resolved outcome back to the JSONL (update in place or append resolution).

#### 3.3 — Outcome Summary Report
- [ ] Add a `--outcomes` flag to `generate_scorecard.py` or create a separate report.
- [ ] Report should include:
  - Total trades resolved.
  - Win rate (%).
  - Average R-multiple.
  - Expectancy = (WinRate × AvgWin) - (LossRate × AvgLoss).
  - Best trade (highest R).
  - Worst trade (lowest R).
  - Trade distribution by timeframe, session, and strategy type.
- [ ] Output as both terminal text and markdown file.

#### 3.4 — Integration with Live Loop
- [ ] In `app.py`, after sending an alert, also write it to the JSONL with outcome=null.
- [ ] Optionally run outcome resolution at the end of each 5-minute cycle.
- [ ] When an alert resolves (TP1 hit), send a follow-up Telegram message:
  `"✅ BTC 5m LONG hit TP1 (+1.5R) | Entry: $60,000 → Exit: $60,500"`

### Success Criteria
- [ ] Every alert has a tracked outcome within its max_duration.
- [ ] Outcome report matches manual verification (spot-check 10 trades).
- [ ] Win rate and expectancy are calculated automatically.

### Evidence
_(To be filled after completion)_

---

## Phase 4: Paper Trading Engine — The Virtual Trader

**Priority:** 🟡 MEDIUM — The culmination of all prior work.
**Estimated Time:** 3–4 hours
**Files:** new `tools/paper_trader.py`, updates to `app.py`
**Depends on:** Phase 3 (outcome tracking must work first)

### Problem

Even with outcome tracking, we don't simulate realistic execution. A paper trader
adds position sizing, portfolio management, and drawdown tracking.

### Tasks

#### 4.1 — Virtual Portfolio
- [ ] Create `tools/paper_trader.py` with a `Portfolio` class:
  ```python
  class Portfolio:
      balance: float = 10_000.0  # Starting virtual USDT
      positions: List[Position] = []
      closed_trades: List[Trade] = []
      max_drawdown: float = 0.0
      peak_balance: float = 10_000.0
  ```
- [ ] Position sizing: risk 1% of balance per trade ($100 on $10k).
- [ ] Max concurrent positions: 3 (prevents over-exposure).
- [ ] Persist portfolio state to `data/paper_portfolio.json`.

#### 4.2 — Trade Execution Simulation
- [ ] When a TRADE-tier alert fires:
  - Check if we have capacity (< 3 open positions).
  - Check if we don't already have a position in the same direction/timeframe.
  - "Enter" at the alert's entry price (midpoint of entry zone).
  - Set SL at invalidation level, TP at TP1.
- [ ] On each price update:
  - Check all open positions against current price.
  - If price hits TP1: close position, record profit.
  - If price hits SL: close position, record loss.
  - If position exceeds max duration: close at market, record result.

#### 4.3 — Portfolio Metrics
- [ ] Track and report:
  - Current balance.
  - Total P&L (absolute and %).
  - Win/Loss/Breakeven counts.
  - Win rate.
  - Average winner vs average loser.
  - Profit factor (gross profit / gross loss).
  - Max drawdown (peak-to-trough).
  - Sharpe ratio approximation.
  - Equity curve data points (balance at each trade close).

#### 4.4 — CLI Interface
- [ ] `python tools/paper_trader.py status` — Show current portfolio state.
- [ ] `python tools/paper_trader.py reset` — Reset to $10k starting balance.
- [ ] `python tools/paper_trader.py report` — Full performance report.
- [ ] Integrate into `run.sh` so it runs alongside the alert loop.

### Success Criteria
- [ ] Paper trader runs for 48 hours without errors.
- [ ] All trades are logged with entry, exit, and R-multiple.
- [ ] Portfolio balance updates correctly on each trade close.
- [ ] Max drawdown tracking works (verified with manual calculation).

### Evidence
_(To be filled after completion)_

---

## Phase 5: Live Dashboard — The Command Center

**Priority:** 🟡 MEDIUM — Visual proof that the system works.
**Estimated Time:** 2–3 hours
**Files:** `dashboard.html`, `scripts/pid-129/generate_dashboard.py`
**Depends on:** Phase 4 (needs portfolio data to display)

### Tasks

#### 5.1 — Equity Curve Visualization
- [ ] Read equity curve data from `data/paper_portfolio.json`.
- [ ] Render an SVG or Canvas chart showing balance over time.
- [ ] Color code: green when above starting balance, red when below.
- [ ] Show max drawdown period highlighted.

#### 5.2 — Live Signal Feed
- [ ] Show the last 20 alerts with their outcomes (Win/Loss/Pending).
- [ ] Color code by outcome: 🟢 Win, 🔴 Loss, ⚪ Pending.
- [ ] Show the R-multiple for resolved trades.

#### 5.3 — Performance Scoreboard
- [ ] Display key metrics in large, readable cards:
  - Virtual Balance (with +/- from start).
  - Win Rate (%).
  - Expectancy (R per trade).
  - Max Drawdown (%).
  - Total Trades.
  - Best/Worst Trade.
- [ ] Auto-refresh every 5 minutes (meta refresh or JS interval).

#### 5.4 — Strategy Breakdown
- [ ] Pie chart or table showing performance by:
  - Timeframe (5m vs 15m vs 1h).
  - Strategy type (Breakout vs Mean Reversion vs Trend Continuation).
  - Session (Asia vs Europe vs US).
- [ ] Highlight which combinations are profitable and which are losing money.

### Success Criteria
- [ ] Dashboard loads in browser and displays real data.
- [ ] Equity curve updates after each trade resolution.
- [ ] All metrics match the CLI report from Phase 4.

### Evidence
_(To be filled after completion)_

---

## Phase 6: Hardening & Graduation

**Priority:** 🟢 FINAL — Polish and lock down.
**Estimated Time:** 2 hours
**Files:** Various
**Depends on:** Phases 1–5

### Tasks

#### 6.1 — Test Suite Expansion
- [ ] Add tests for outcome tracker (mock price data, verify resolution).
- [ ] Add tests for paper trader (mock trades, verify P&L calculation).
- [ ] Add integration test: alert → outcome → portfolio update.
- [ ] Ensure all tests pass: `PYTHONPATH=. python3 -m pytest tests/`.

#### 6.2 — Configuration Locking
- [ ] After Phase 2 tuning, document the "Golden Config" in config.py with comments.
- [ ] Add a `config_v1.3_baseline.py` snapshot so we can always revert.
- [ ] Document what each parameter does and its acceptable range.

#### 6.3 — Operational Runbook
- [ ] Update `OpenClaw_Effective_Agents_Playbook_PLUS.md` with:
  - How to start the paper trader.
  - How to read the dashboard.
  - How to interpret the equity curve.
  - When to tune parameters vs when to trust the system.
  - Red flags that mean "stop trading and investigate."

#### 6.4 — Definition of Done (v2.0)
The project is COMPLETE when ALL of the following are true:
- [ ] Backtest produces accurate, trusted metrics (Phase 1).
- [ ] Win rate ≥ 55% on at least one timeframe (Phase 2).
- [ ] Every alert has a tracked outcome (Phase 3).
- [ ] Paper trader has run for ≥ 7 days with positive expectancy (Phase 4).
- [ ] Dashboard shows equity curve and all metrics (Phase 5).
- [ ] All tests pass (Phase 6).
- [ ] Playbook is updated and operational (Phase 6).

---

## Execution Order & Dependencies

```
Phase 1: Backtest Fidelity ──────────────────────┐
    │                                              │
    ▼                                              │
Phase 2: Signal Quality ─────────────────────┐    │
    │                                         │    │
    ▼                                         │    │
Phase 3: Outcome Tracking ──────────────┐    │    │
    │                                    │    │    │
    ▼                                    │    │    │
Phase 4: Paper Trading Engine ─────┐    │    │    │
    │                               │    │    │    │
    ▼                               │    │    │    │
Phase 5: Live Dashboard ──────┐    │    │    │    │
    │                          │    │    │    │    │
    ▼                          ▼    ▼    ▼    ▼    ▼
Phase 6: Hardening & Graduation (requires ALL above)
```

**Total Estimated Time:** 12–17 hours across all phases.
**Recommended Pace:** 1 phase per session (2–3 hour sessions).
**Target Completion:** ~1 week of focused sessions.

---

## Quick Reference Commands

```bash
# Run corrected backtest (after Phase 1)
PYTHONPATH=. python3 tools/run_backtest.py

# Run tests
PYTHONPATH=. python3 tests/test_utils_engine.py

# Run live alerts (single cycle)
./run.sh --once

# Run continuous monitoring
./run.sh

# Generate scorecard
python3 scripts/pid-129/generate_scorecard.py

# Generate dashboard
python3 scripts/pid-129/generate_dashboard.py

# Paper trader status (after Phase 4)
python3 tools/paper_trader.py status

# Paper trader report (after Phase 4)
python3 tools/paper_trader.py report
```

---

## Risk Register

| Risk | Impact | Mitigation |
|:-----|:-------|:-----------|
| Backtest still shows inflated counts after Phase 1 | HIGH | Cross-validate with manual chart review |
| Win rate doesn't improve after Phase 2 tuning | HIGH | Consider the strategy fundamentally flawed; pivot to ML |
| Exchange API changes break data collection | MEDIUM | Multiple fallback providers already in place |
| Paper trader has bugs that mistrack P&L | HIGH | Extensive unit tests + manual spot-checks |
| Over-optimization (curve fitting) | HIGH | Use walk-forward validation: tune on first half, test on second |
| User loses interest before Phase 4 | MEDIUM | Each phase produces a visible, satisfying deliverable |

---

_This document is the single source of truth for remaining work.
Update the checkboxes as tasks are completed._
_Last updated: 2026-02-17T08:42:00-05:00_
