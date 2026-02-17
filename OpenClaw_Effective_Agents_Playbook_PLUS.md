# OpenClaw Effective Agents Playbook PLUS: Paper Trading & Strategy Mastery

> **Objective:** transform the BTC Alerts MVP from a code repository into a profit-generating weapon through disciplined paper trading and iterative strategy refinement.

This playbook is designed for the **Trader** (User) to collaborate with the **Agent** (AI) to rigorously test, validate, and improve trading strategies using "Paper Trading Only" on Bitcoin.

---

## 🧭 The Philosophy: "Earn the Right to Trade"

Before a single satoshi is risked, we must prove the edge exists. We do this through a phased approach that escalates commitment only as performance is validated.

**Golden Rule:** *We do not move to the next phase until the current phase yields a profitable expectancy over 20+ samples.*

---

##  Phase 1: The Observer (Signal Calibration)
**Goal:** Validate that the alerts match "common sense" technical analysis and are firing at the right times.

### 📝 Operations
1. **Run the Engine Continuously:** Keep the alerts running on your dashboard/terminal.
2. **Chart Verification:** When an alert fires (e.g., "LONG BTC 1h"), immediately open your charting platform (TradingView).
3. **The "Sniff Test":**
    - Does the logical reason provided (e.g., "RSI Divergence") exist on the chart?
    - Is the entry zone realistic?
    - Are we trading *into* immediate resistance?

### 🛠️ Agent Optimization Tasks
If alerts feel "off":
- **Too Noise:** Ask Agent to *raise* `CONFIDENCE_THRESHOLD` in `config.py`.
- **Too Late:** Ask Agent to *lower* `DONCHIAN_LOOKBACK` or make triggers more sensitive.
- **Wrong Direction:** Ask Agent to check `Trend Detection` logic in `engine.py`.

**Exit Criteria:** 90% of alerts look "sensible" on the chart, even if they wouldn't all be winners.

---

## Phase 2: The Manual Paper Trader (The Journal)
**Goal:** Simulate execution to measure "Human + Machine" performance. The alert is just a setup; your execution is the trigger.

### 📝 Operations
1. **Setup a Spreadsheet/Journal:** Columns: `Date`, `Type (Long/Short)`, `Entry Price`, `Stop Loss`, `Take Profit`, `Outcome (Win/Loss)`, `R-Multiple`.
2. **Execution Rules:**
    - When an alert fires with Confidence > 75, **RECORD** a trade.
    - strictly adhere to the `Entry Zone` provided by the alert.
    - strictly adhere to `TP1`, `TP2`, and `Invalidation` levels.
3. **The "Sleep Test":** Let the trades run. Do not manually intervene unless the system generates a "CLOSE" or opposing signal.

### 🛠️ Agent Optimization Tasks
- **Review the Scorecard:** Use `generate_scorecard.py` to see the system's raw stats.
- **Analyze Losers:** Group losing trades. Is there a pattern? (e.g., "Always loses during Asia session").
- **Tweak Weights:** If Asia is losing, ask Agent to *lower* `SESSION_WEIGHTS['asia']` in `config.py`.

**Exit Criteria:** 20 verified paper trades with a positive Expectancy (Average R > 0.5 per trade).

---

## Phase 3: The Architect (Strategy Tuning)
**Goal:** Customize the engine to fit *your* specific trading style (e.g., Scalping vs. Swing).

### 🔍 Strategy Profiles
Decide which profile you want to optimize for and instruct the Agent to tune `config.py` accordingly.

#### Profile A: "The Sniper" (Low Frequency, High Win Rate)
- **Focus:** 1H / 4H Timeframes.
- **Config Changes:**
    - Increase `CONFIDENCE_THRESHOLD` to 80+.
    - Require `CONFLUENCE_GATING` (must have 3+ indicators).
    - Tighten `RISK_REWARD` requirements (min 2.0).

#### Profile B: "The Grinder" (High Frequency, Mean Reversion)
- **Focus:** 5m / 15m Timeframes.
- **Config Changes:**
    - Enable `MEAN_REVERSION` strategies.
    - Widen `ENTRY_ZONES`.
    - Use loose invalidations but quick TP1s.

### 🛠️ Agent Optimization Tasks
- **Backtesting (Mental):** "Agent, look at the last 10 alerts. If we had applied 'Sniper' settings, how many would we have missed? How many losers would we have avoided?"

---

## Phase 4: Automated Paper Simulation (The Machine)
**Goal:** Remove human execution error and run 24/7 simulation.

### 📝 Operations
1. **Activate Phase 3C (Roadmap):** Instruct Agent to build the `PaperTradingEngine`.
2. **Virtual Wallet:** The system initializes with $10,000 fake USDT.
3. **Auto-Execution:** The engine "executes" trades internally when price hits entry zones.
4. **PnL Dashboard:** A new command `./show-pnl.sh` will report the bot's performance.

### 🛠️ Agent Optimization Tasks
- **Drift Analysis:** Compare the *Automated* PnL vs. your *Manual* PnL from Phase 2.
    - If Manual > Automated: You are adding value (discretion).
    - If Automated > Manual: You are the bottleneck. Trust the bot.

---

## 🚀 How to Request Help
When asking for strategy help, use this format to get the best results:

> "Agent, I am in **Phase 2**. I noticed we are getting stopped out frequently on **15m Longs** during the **NY Open**. Can you analyze the volatility settings in `config.py` and suggest a tweak to widen our stops for that specific time?"

---

## Current Recommended Routine
1. **Morning:** `./run.sh --once` to get the lay of the land.
2. **During Day:** Keep `logs/pid-129-alerts.jsonl` open or tail it.
3. **Evening:** Run `generate_scorecard.py` and review the day's "Paper PnL".
4. **Weekend:** Deep dive into `config.py` adjustments.
