# Phase 18: Dashboard Precision & Signal Refinement

**Status:** ✅ COMPLETE

**Goal:** Surface all computed intelligence onto the dashboard so the trader sees the full context needed for a profitable BTC long/short futures decision from a single screen.

---

## What Was Done

### Step 1 ✅ — engine.py: Context fields expanded
All sub-steps applied. Correctly serializes `volume_profile`, `structure`, `session_levels`, `volume_impulse`, and `auto_rr` into `decision_trace.context`.

### Step 2 ✅ — Volume Impulse polarity split
Split `VOLUME_IMPULSE` into `VOLUME_IMPULSE_BULL` / `VOLUME_IMPULSE_BEAR`. Added `ATR_EXPANSION_ONSET` detection.

### Step 3 ✅ — Key Levels panel added
Added dynamically updating HTML panel for PDH, PDL, POC, VAH, VAL, AVWAP, and Pivot points. Expanded to include **Bid/Ask Walls** and **Liquidity Targets**.

### Step 4 ✅ — RVol + Vol Regime cells added
Added live stat-cards to the Tape. Correctly color-coded for expansion vs. low volume.

### Step 5 ✅ — Limit Lifecycle to Top 10
Modified `render_lifecycle_panel` in `generate_dashboard.py` to only show the top 10 most urgent unresolved trades to reduce noise.

### Step 6 ✅ — 15 Radar Probes
Added `VP Status` and `Auto R:R` probes. Updated Momentum to use directional impulse. Total 15 probes active in logic.

### Step 7 ✅ — FIX: Confidence/Tier Gating (engine.py)
**FIXED:** Prevented confidence=1 signals from showing as "A+ TRADE". In `_tier_and_action()`, we now use `abs(total_score)` and gate correctly against `trade_long` thresholds only.

### TASK 8 ✅ — Fix Dashboard Live Data
**FIXED:** `dashboard_server.py` no longer strips critical context. Added `sentiment`, `macro_correlation`, and `liquidity` to the keep-set for full institutional context.

### TASK 9 ✅ — Add Position Size Calculator
**FIXED:** Implemented **Adaptive Risk Management**. Execution matrix now displays "Suggested Risk" (2.0% for A+, 0.5% for B) and calculates the exact **BTC Quantity** based on entry/stop distance.

### TASK 10 ✅ — Lower Confidence Thresholds
**FIXED:** Tuned `config.py` to use realistic thresholds (~45 for 5m, ~35 for 1h) to ensure A+ signals trigger in current market volatility.

### TASK 11 ✅ — Institutional Context Sentinel
**ADDED:** Surfaced **Pillar 1 (Macro)** and **Pillar 2 (Order Flow/OI)** onto the Live Tape. The dashboard now tracks DXY Trend, Sentiment Score, OI Regime, and Taker Ratio in real-time.

---

## Verification Checklist
- [x] Key Levels show real prices on live WebSocket refresh.
- [x] RVol shows "1.2x" etc. on live refresh.
- [x] Execution Matrix shows "A+ TRADE" only for scores > 45.
- [x] Position sizing (Risk % and BTC Qty) is visible.
- [x] Macro/OI Sentinel is visible on the Live Tape.

---
_Phase 18 Blueprint | EMBER PID-129 | 2026-02-26_

