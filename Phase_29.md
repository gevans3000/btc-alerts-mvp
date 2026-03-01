# Phase 29 — Continuous Machine Learning Self-Correction

**Status:** 📅 PLANNED
**Goal:** Build a closed-loop system where the trading AI learns from its own live PnL outputs, iteratively tuning its confluence parameters every 24 hours to compensate for macro-drift and changing market regimes.

---

## 1. Context & Architecture Requirements

**Goal 1: The PnL Feedback Loop**
- **Concept:** A model relies on historical backtests. To survive, it must treat every live trade (paper or real) as training data.
- **Execution:** Build a fast SQLite or JSON database `trade_results.db` that logs `Alert_ID`, `Predicted_Win_Prob`, `Actual_Outcome` (Win/Loss), and `Actual_R_Multiplier`.

**Goal 2: The Nocturnal Tuner (Overnight Rebalancing)**
- **Concept:** Markets change behavior. An RSI divergence that worked in Q1 might fail constantly in Q2.
- **Execution:** A scheduled python script replacing `auto_tune.py` that runs at 03:00 AM daily. It evaluates the prior 7 days of trades. If a specific radar probe (e.g., AVWAP) has a 0% predictive accuracy for the week, its weight in the `CONFLUENCE_RULES` is automatically downgraded for the next day. 

**Goal 3: Macro-Drift & Calendar Awareness**
- **Concept:** The system should learn to distrust certain technicals right before CPI or FOMC data drops. 
- **Execution:** Incorporate an economic calendar API flag. If a massive news event is pending, the AI must automatically raise the minimum Confidance Gate from 40 to 65 for 4 hours.

---

## 2. Tasks for the Implementing Agent

### Task 1: Building the PnL Ingestor
1. Create a script that hooks into the exchange API (or paper trading logs) to definitively map a completed trade back to its original `Alert_ID`.
2. Save the final PnL and Max Drawdown during the trade lifecycle.

### Task 2: Building the ML Rebalancer (`night_tuner.py`)
1. Create `night_tuner.py`. It should read `trade_results.db` and run a basic linear regression or feature importance scan across the 15 radar probes vs. the actual win/loss outcome.
2. Have it output a newly generated `weights.json` that the Intelligence Engine reads on startup to prioritize working indicators and de-prioritize failing ones.

### Task 3: Macro-Event Suppression
1. Use an open-source economic calendar library or free API to fetch major (3-star) US economic events.
2. 4 hours before and 1 hour after the event, broadcast a `MACRO_DANGER` state to the engine, temporarily increasing execution thresholds and widening SL margins.

---

## 3. Verification Checklist
- Run a simulated week of mock trade results through `night_tuner.py`. Verify that the generated `weights.json` correctly down-weights a mock indicator engineered to fail 100% of the time.
- Verify the economic calendar system successfully flags upcoming FOMC days and elevates the risk threshold in the console logs.
- Assure all database reads/writes are atomic and do not lock the live trading engine if executed simultaneously.
