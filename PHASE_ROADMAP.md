# BTC Alerts MVP — Phase Roadmap for AI Agents

**Project:** PID-129 — EMBER Autonomous Trading Intelligence
**Current State:** v18.0 Precision
**Last Updated:** 2026-02-26

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

## 🚀 Future Roadmap

### Phase 18: Dashboard Precision & Signal Refinement ✅ DONE
> Full spec: `Phase_18.md` — 7-step implementation plan

**Core problem:** Engine computes rich intelligence (POC/VAH/VAL, AVWAP, PDH/PDL, BOS/CHoCH, RVol, Auto R:R) but none of it is surfaced to the trader. Fixed via WebSocket context restoration.

#### Step 1 — Verdict Center: Key Levels Panel (P0)
- ✅ Wire `session_levels` (PDH/PDL/Session H/L) into new levels sub-panel
- ✅ Wire `volume_profile` (POC/VAH/VAL) into levels panel
- ✅ Wire `avwap` (price + ABOVE/BELOW/AT) into levels panel
- ✅ Wire `structure` (BOS/CHoCH event + pivot high/low) into levels panel

#### Step 2 — Live Tape: Volatility Context Strip (P0)
- ✅ Add RVol cell (relative volume vs 20-bar avg, color-coded by threshold)
- ✅ Add Vol Regime badge (LOW=blue / NORMAL=white / EXPANSION=orange)

#### Step 3 — Alert Table: Trade Plan Column (P0)
- ✅ Replace "Trigger: None" column with "Trade Plan" (Entry / SL / TP per alert)
- ✅ Pull from `decision_trace.context.auto_rr` — already computed by engine

#### Step 4 — Two New Radar Probes (P1)
- ✅ **VP Status probe**: 🟢 ABOVE_VALUE / 🔴 BELOW_VALUE / 🟡 LVN_NEARBY / ⚫ INSIDE_VALUE
- ✅ **Auto R:R probe**: 🟢 EXCELLENT (≥2.0) / 🟡 ADEQUATE (≥1.2) / 🔴 POOR (<1.2)

#### Step 5 — Volume Impulse Polarity Split (P1)
- ✅ Split `VOLUME_IMPULSE` code into `VOLUME_IMPULSE_BULL` / `VOLUME_IMPULSE_BEAR` based on candle close vs open
- ✅ Update radar probe mapping for Volume Impulse probe

#### Step 6 — Expansion Detector Badge (P2)
- ✅ Detect ATR percentile transition (crossed from <50 to >70) → emit `ATR_EXPANSION_ONSET`
- ✅ Show pulsing ⚡ EXPANSION badge in Live Tape when onset detected

#### Step 7 — Confidence Score Audit (P2)
- ✅ Audit why peak confidence is 56 despite Phase 17 intel layers
- ✅ Inspect `score_breakdown` on live snapshot, check `CONFLUENCE_RULES["A+"]` gate
- ✅ Adjust thresholds to allow valid A+ setups to reach ≥70 confidence (Lowered to 45/25)
- ✅ **Verified**: Dashboard live update bug fixed (context restoration)
- ✅ **Verified**: Gating logic fixed (abs score comparison corrected)


---
_v18.0 | EMBER Collective_
