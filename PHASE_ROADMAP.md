# BTC Alerts MVP — Phase Roadmap for AI Agents

**Project:** PID-129 — EMBER Autonomous Trading Intelligence
**Current State:** v28.0 Execution Integration (Starting)
**Last Updated:** 2026-02-28

---

## Phase 1: Core Signal Quality ✅ DONE
- ✅ Advanced Technical Indicators (RSI Div, Patterns)
- ✅ Enhanced Market Regime Classification
- ✅ Better Trade Plan Accuracy (Dynamic TP/SL)

## Phase 2: Operational Excellence ✅ DONE
- ✅ Structured Decision Trace Logging
- ✅ Persistent Alert History (JSONL)
- ✅ Outcome Tracking (TP/SL Hits)

## Phase 3: Verification & Simulation ✅ DONE
- ✅ Historical Backtester (`tools/backtest.py`)
- ✅ Paper Trading Integration
- ✅ Confluence Signal Heatmap

## Phase 4: Production Hardening ✅ DONE
- ✅ Intelligent Dashboard (HTML)
- ✅ Multi-Layer Monitoring (Cycle timing, Health)
- ✅ Standardized CLI & PowerShell Interfaces

## Phase 5: Autonomy & Self-Improvement ✅ DONE
- ✅ **Morning Briefing**: Daily 6 AM actionable summary (`scripts/morning_briefing.py`).
- ✅ **Auto-Tuner**: Threshold self-adjustment engine (`tools/auto_tune.py`).
- ✅ **Scheduled Pipeline**: 6 AM ET automated sweep (`scripts/pipeline.ps1`).
- ✅ **Operator Gate**: ON/OFF Toggle Switch (`scripts/toggle.py`).

---

## Phase 6: Multi-Asset Expansion ✅ DONE
- ✅ Logic applied to BTC, ETH, SOL
- ✅ Asset-specific configuration handling

## Phase 7: Live Execution Bridge ✅ DONE
- ✅ Risk Management & Position Sizing
- ✅ Bitunix/Bybit API Integration
- ✅ Execution Safety Gates

## Phase 8-11: Dashboard & Intelligence ✅ DONE
- ✅ Premium UI/UX Aesthetics
- ✅ Real-time WebSocket Feed
- ✅ Confluence Radar Architecture
- ✅ Performance Analytics

## Phase 12: Radar Data Integration ✅ DONE
- ✅ Fixed Code Trace Serialization
- ✅ Live Orderbook Collector
- ✅ Real-time Probe Signal Mapping

---

## Phase 13: Dashboard Perfection ✅ DONE
- ✅ Live Tape Win Rate & PF Logic
- ✅ Radar Probe Threshold Tuning
- ✅ Improved Spread Estimation

## Phase 14: Data Density & Trade Edge ✅ DONE
- ✅ Enhanced Radar Active Probes (8/10 active)
- ✅ VIX & Macro Correlation Resilience
- ✅ ML Conviction Logic Optimization

## Phase 15: Universal Provider Fallback ✅ DONE
- ✅ **Collector Resilience**: Multi-provider chain (Bybit → OKX → Bitunix)
- ✅ **Budget Management**: Advanced rate-limiting + automatic source-failover
- ✅ **FreeCryptoAPI Integration**: Fallback BTC price source
- ✅ **Hardened Dashboard**: WebSocket Server V2 (Optimized caching, frame handling)

---

## Phase 16: Stabilization & Bug Sweep ✅ DONE
- ✅ Fixed `config.py` TIMEFRAME_RULES syntax
- ✅ Restored Orderbook radar probe (passed BudgetManager)
- ✅ Corrected SHORT confidence logic (abs score)
- ✅ Hardened app.py fallbacks (fixed constructor signatures)
- ✅ Reduced WS Payload Size (15 alerts + context stripping)
- ✅ Synced Live Tape 'Risk Gate' with Verdict Center logic

---

## Phase 17: Confluence Indicator Minimum Stack ✅ DONE
- ✅ **Market Structure**: BOS/CHoCH detection
- ✅ **Liquidity Sweeps**: Equal Highs/Lows + Session Sweep detection
- ✅ **Anchored VWAP**: Dynamic S/R from swing points
- ✅ **OI Classifier**: Price-OI relationship logic (New Longs/Shorts)
- ✅ **Auto R:R**: Intelligence-based risk assessment targets
- ✅ **Expanded Radar**: 3 new dashboard probes (Structure, Levels, AVWAP)

---

## Phase 18: Dashboard Precision & Signal Refinement ✅ DONE
- ✅ **Verdict Center**: Key Levels Panel (P0)
- ✅ **Live Tape**: Volatility Context Strip (P0)
- ✅ **Alert Table**: Trade Plan Column (P0)
- ✅ **Two New Radar Probes**: VP Status & Auto R:R
- ✅ **Volume Impulse**: Polarity Split (Bull/Bear)
- ✅ **Expansion Detector**: ATR Percentile
- ✅ **Confidence Score Audit**: Adjusted gating thresholds

## Phase 19: Wake Up Every Confluence Probe ✅ DONE
- ✅ **Score Normalization**: 3x multiplier
- ✅ **A+ Guard**: Downgrade stale alerts
- ✅ **Graduated Execution**: TF Details ("2/3 aligned")
- ✅ **Auto-Close Stale Trades**: NEUTRAL status logic
- ✅ **Probe Activation**: Restored and tuned 10+ radar metrics

## Phase 20: Real Alerts & Probe Diagnostics ✅ DONE
- ✅ **Score Calibration**: Multiplier set to 7.0
- ✅ **Diagnostics**: Tooltips and inline WHY-text to all 15 probes
- ✅ **Signal History**: "Recent Signals" panel
- ✅ **Accuracy Badge**: "Edge (last 20)" tracking

## Phase 21: Cyber-Terminal Upgrade ✅ DONE
- ✅ **Advanced Aesthetics**: Deep glassmorphism styling
- ✅ **Numeric Precision**: Tabular monospaced typography
- ✅ **Living Elements**: Micro-animations for signal pulsing

## Phase 22: Alert Recipe Layer ✅ DONE
- ✅ **High-Conviction Patterns**: HTF_REVERSAL, BOS_CONTINUATION
- ✅ **Validation Checklist**: 5-Question gating
- ✅ **Weighted Rubric**: 6-point quantitative confluence
- ✅ **Bot Schema**: Standardized JSON output

---

## Phase 23: Signal Fidelity & Alert Logic Polish ✅ DONE
- ✅ **Persisted Metadata**: Execution price and entry zones available for the dashboard
- ✅ **Enhanced HTF Confirmation**: Filtered for last 3 HTF candles to eliminate stale bias
- ✅ **Corrected Recipe R:R**: Utilized execution price rather than last traded price

## Phase 24: Advanced UI Data Linking ✅ DONE
- ✅ **Analytic Surfacing**: Display Directional Edge, Unrealized PnL, & Drawdown stats
- ✅ **UI Interactivity**: Fully functioning Mute / Signal Floor control integrations via `/api/command`
- ✅ **Socket Payload Adjustments**: Synchronized REST + WS formats for the front end

## Phase 25: Trade Copilot & Market X-Ray ✅ DONE
- ✅ **Regime-Aware Auto-Pilot**: Tuned strategy parameters dependent on volatility
- ✅ **Trade Management Copilot**: Standby vs Active status displays on open positions
- ✅ **Order Flow X-Ray**: Extracted BS-Severity (Buy/Sell Imbalance) codes into UI
- ✅ **Drawdown Circuit Breaker**: Auto-disable triggers during major portfolio dips

## Phase 26: Live-Readiness Hardening (The Final Gate) ✅ DONE
- ✅ **Data Auditing**: Eliminated all `—` and `NaN` blank fields
- ✅ **Anti-Flicker State Caching**: Persisted `decision_trace.context` across socket updates
- ✅ **Staleness Warnings**: Integrated `DATA STALE` UI alarms (if alerts pause > 5m)
- ✅ **Free API Alpha Injection**: "Smart Money" injections (Funding, OI Delta) right on the tape

---

## Phase 27: Strict Signal Filtration & Vetoes ✅ DONE
- ✅ Macro Veto (1H/4H Alignment)
- ✅ Order Flow Veto (Taker Ratio Alignment)
- ✅ Volatility & Range Rejection (Chop Filter)
- ✅ MTF Data Plumbing (4H Integration)

---

## 🚀 Future Roadmap: The Path to the "God Button" Dashboard
*The ultimate objective is a singular, perfectly calibrated Bitcoin futures dashboard where a single click yields a mathematically verified, high-confidence LONG or SHORT play.*

### Phase 28: Live Institutional Execution Integration � NEXT
- **Objective:** Transition from dashboard suggestions to robust, zero-click live broker trading pipeline.
- **Tasks:** Build `executor.py` (CCXT), implement adaptive slippage defense, and connect Operator Toggle for LIVE execution.

### Phase 29: Continuous Machine Learning Self-Correction 📅 PLANNED
- **Objective:** AI learns from live PnL outputs to tune confluence parameters every 24h.
- **Tasks:** Build PnL Ingestor, `night_tuner.py` for nocturnal rebalancing, and macro-event suppression gates.

### Phase 30: Absolute Autonomy (v1.0 Production) 📅 PLANNED
- **Objective:** Finalize "EMBER Swarm" into a distributed, containerized (Docker) multi-agent system.
- **Tasks:** Microservice refactoring, Dockerization, and implementation of the Sentinel Watchdog.

### Phase 31: Institutional "Smart Money" Tracking 📅 PLANNED
- **Objective:** Follow the whales.
- **Tasks:** Monitor large on-chain Bitcoin movements to exchange derivative wallets.

### Phase 32: Options Market "Max Pain" Integration 📅 PLANNED
- **Objective:** Anticipate options expiry volatility.
- **Tasks:** Pull Deribit options data to calculate the "Max Pain" price point.

### Phase 33: NLP Sentiment & Macro-Economic Safety Gate 📅 PLANNED
- **Objective:** Prevent the system from buying right before high-impact news.
- **Tasks:** NLP scraping of major economic calendars and X (Twitter) sentiment.

---
_v33.0 | EMBER Collective | Signal Accuracy Reached_
