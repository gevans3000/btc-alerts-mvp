# BTC Alerts MVP — Phase Roadmap for AI Agents

**Project:** PID-129 — EMBER Autonomous Trading Intelligence
**Current State:** v5.0 Autonomous
**Last Updated:** 2026-02-18

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

## 🚀 Future Roadmap

### Phase 6: Multi-Asset Expansion 🎯 NEXT
- **What:** Apply EMBER logic to ETH and SOL.
- **Why:** Diversification of high-confidence signals.
- **Plan:** Abstract `engine.py` to handle asset-specific configs.

### Phase 7: Live Execution Bridge
- **What:** Low-latency order execution via Bitunix/Bybit API.
- **Why:** Moving from paper trading to live capital.
- **Safety:** Hard position limits and 2FA-secured keys.

---
_v5.0 | EMBER Collective_
