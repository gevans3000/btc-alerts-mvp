# BTC Alerts MVP 🚀
**PURPOSE:** to hae my dashboard give me the best info for me to trade profitably with bitcoin futures

High-signal long/short opportunity alerts for **BTC** (primary) and **SPX proxy** (secondary), optimized for **5m / 15m / 1h** timeframes.

**Project:** PID-129 — EMBER Autonomous Trading Intelligence
**Status:** v15.0 Resilient (Multi-Provider Fallback + Hardened Dashboard)
**Last Updated:** 2026-02-26

---

## Overview

This system generates **LONG/SHORT/NO-TRADE** alerts with **0-100 confidence scores**, specific **entry zones**, and **dynamic trade plans** (TP1/TP2, invalidation, R:R). It is now fully autonomous, tuning its own thresholds nightly and generating morning briefings.

### Key Features

- **Autonomous Operations:** 6 AM Morning Briefing, Nightly Self-Tuning, and Automated Pipeline.
- **Universal Provider Resilience:** Automatic fallback between 5+ API providers (Kraken, Bybit, OKX, Bitunix, FreeCryptoAPI) with zero data loss.
- **6-Layer Intelligence:** Volume Profile (POC), Liquidity Walls, Macro (DXY/Gold), Squeeze, Sentiment, and Confluence Heatmaps.
- **Hardened Monitoring:** Real-time Dashboard with WebSocket V2, optimized for low Latency and high availability.
- **Operations:** [OPERATOR.md](OPERATOR.md) (ON/OFF switch, Morning Briefing, Auto-Tuning).
- **OpenClaw governance:** Multi-platform support, health checks, watchdogs, scorecards.

---

## 🚀 Quick Start

```powershell
# 1. Start the system (loop mode)
.\run.ps1 --loop

# 2. Daily Morning Briefing (6 AM ET)
# Check reports/morning_briefing.md

# 3. Manual Toggle
python scripts/toggle.py status
python scripts/toggle.py off
python scripts/toggle.py on
```

# 4. View Dashboard (Hardened WS V2)
# Start the server (runs on http://localhost:8000)
python scripts/pid-129/dashboard_server.py
# (The dashboard.html connects automatically even if opened as a local file)

---

## Architecture

```
BTC Alerts MVP (PID-129)
├── app.py                    # Main Loop & CLI (with ON/OFF check)
├── engine.py                 # Core Scoring & Intelligence Arbitration
├── config.py                 # Central Tunables (Self-Adjusting)
├── OPERATOR.md               # User & Agent Operational Guide
├── scripts/
│   ├── toggle.py             # ON/OFF System Switch
│   ├── morning_briefing.py   # Daily 6 AM Briefing Generator
│   ├── pipeline.ps1          # Nightly Automation Pipeline
│   └── pid-129/              # Legacy Scorecard & Dashboard tools
├── tools/
│   ├── auto_tune.py          # Threshold Self-Improvement Engine
│   └── backtest.py           # Historical Verification Tool
├── intelligence/             # Modular Intelligence Layers
│   ├── volume_profile.py     # POC & Binning logic
│   ├── liquidity.py          # Orderbook wall detection
│   └── confluence.py         # Signal Heatmap & Aggregation
├── logs/                     # JSONL Source of Truth
└── reports/                  # Markdown & JSON Briefings
```

---

## Configuration

Tune thresholds centrally in `config.py`. Note that `TIMEFRAME_RULES` are auto-adjusted by `auto_tune.py` based on last 7 days of performance.

### Regime Detection
```python
REGIME = {
    "adx_trend": 24,
    "slope_trend": 0.003,
    "atr_rank_chop": 70,
    "adx_chop": 20,
}
```

### Timeframe Rules (Self-Adjusting)
```python
TIMEFRAME_RULES = {
    "1h": {"min_rr": 1.15, "trade_long": 68, "trade_short": 32, ...},
}
```

---

## Testing

```bash
# Run all core intelligence tests
PYTHONPATH=. python -m pytest tests/
```

---

## OpenClaw Governance

This project follows the **PID-129 Governance Contract** for AI-human pair programming.

**Schedule:** 
- **6:00 AM ET:** Morning Briefing & Pipeline Execution.
- **Continuous:** 5-minute monitoring loop.

---

## Failure & Outcome Matrix

| Failure Mode | Detection | Action |
|--------------|-----------|--------|
| API error | Alert generation | Retry 3x + NO-TRADE fallback |
| Market data stale | Health check | Suppress signal + NO-TRADE |
| System Disabled | `DISABLED` file | Sleep & skip cycle |

---

## Phased Improvements

This project is in **Phase 15 (v15.0)**:
- ✅ Phase 1-5: Autonomy (Morning Briefing, Auto-Tuning)
- ✅ Phase 6-11: Dashboard & Confluence Radar
- ✅ Phase 12: Real-time Data Integration
- ✅ Phase 13-14: Dashboard Perfection & Data Density
- ✅ Phase 15: Universal Provider Fallback (Resilience)

---

## References

- **Operations:** `OPERATOR.md`
- **Roadmap:** `PHASE_ROADMAP.md`
- **Current Blueprint:** `Phase_15.md`
- **Current Stats:** `reports/morning_briefing.md`

---

**Last Updated:** 2026-02-26
**Version:** 15.0
**Status:** Resilient & Autonomous
