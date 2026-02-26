# BTC Alerts MVP — Phase Roadmap for AI Agents

**Project:** PID-129 — EMBER Autonomous Trading Intelligence
**Current State:** v5.0 Autonomous
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

## 🚀 Future Roadmap

### Phase 13: Dashboard Perfection ✅ DONE
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

## 🚀 Future Roadmap

### Phase 17: Confluence Indicator Minimum Stack ✅ DONE
- ✅ **Market Structure**: BOS/CHoCH detection
- ✅ **Liquidity Sweeps**: Equal Highs/Lows + Session Sweep detection
- ✅ **Anchored VWAP**: Dynamic S/R from swing points
- ✅ **OI Classifier**: Price-OI relationship logic (New Longs/Shorts)
- ✅ **Auto R:R**: Intelligence-based risk assessment targets
- ✅ **Expanded Radar**: 3 new dashboard probes (Structure, Levels, AVWAP)

---
_v15.0 | EMBER Collective_
