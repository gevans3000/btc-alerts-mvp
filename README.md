# BTC Alerts MVP 🚀 (EMBER Intelligence)

**PURPOSE:** A high-precision, autonomous trading intelligence engine designed to maximize profitable Bitcoin (BTC) futures trades through multi-timeframe market microstructure analysis.

---

## 🛰️ Project PID-129: EMBER Core
- **Status:** v31.0 "A+ Tier" Hardened
- **Current Truth:** Fully autonomous monitoring with weighted confluence scoring and directional seasoning.
- **Primary Focus:** High-conviction signals (A+) while filtering B-tier noise.

---

## 🧠 Key Features

- **Weighted Confluence (Phase 29):** Prioritizes **Structure (BOS/CHoCH)** and **Location (Key Levels)** with higher math weights, ensuring trade quality over quantity.
- **High-Conviction Recipes (Phase 30):** Specialized patterns including `RANGE_BREAKOUT`, `MOMENTUM_DIVERGENCE`, and `FUNDING_FLUSH` for precise entries.
- **Microstructure Seasoning (Phase 31):** Dynamic thresholds that adjust based on **Funding Rates**, **Open Interest crowding**, and **HTF Cascade** alignment (4H/1H/15m).
- **Hardened Execution Dashboard:** Real-time WebSocket V2 terminal at [localhost:8002](http://localhost:8002) with circuit breakers and liquidation targets.
- **Autonomous Lifecycle:** Daily 6 AM morning briefings, nightly self-tuning (`auto_tune.py`), and 24/7 scanning.

---

## � Quick Start

```powershell
# 1. Start the monitoring loop (5-minute cycles)
.\run.ps1 --loop

# 2. View the Live Dashboard (Strategic Command)
python scripts/pid-129/dashboard_server.py
# Access at: http://localhost:8002

# 3. System Controls
python scripts/toggle.py status  # Check if engine is ON/OFF
python scripts/toggle.py off     # Pause signal generation
```

---

## 🏗️ Architecture

```
BTC Alerts MVP (PID-129)
├── app.py                    # Strategic Loop & CLI
├── engine.py                 # Weighted Scoring & Seasoning Logic
├── config.py                 # Central Source of Truth (Self-Adjusting)
├── PHASES_29_31_COMPLETED.md # Current Strategic Progress Report
├── intelligence/             # Modular Intelligence Layers (17 Probes)
│   ├── structure.py          # BOS/CHoCH Market Structure
│   ├── recipes.py            # RANGE_BREAKOUT, FUNDING_FLUSH, etc.
│   ├── anchored_vwap.py      # Dynamic VWAP & Anchored S/R
│   └── volume_profile.py     # Value Area (POC/VAH/VAL) & LVNs
├── collectors/               # Multi-Provider Async Data (Failover Ready)
│   ├── price.py              # 7+ Source Price Aggregation
│   ├── derivatives.py        # Funding Rates & Open Interest
│   └── flows.py              # Taker Buy/Sell Ratios (Orderflow)
├── tools/                    # Operational Tools
│   ├── auto_tune.py          # Nightly Threshold Self-Correction
│   ├── run_backtest.py       # High-fidelity Historical Verification
│   └── paper_trader.py       # Forward Testing & Portfolio Stats
└── data/                     # State & IPC persistence
```

---

## 🛠️ Configuration & Governance

### Self-Adjusting Logic
The system uses `dna/dna.json` to store learned thresholds. `tools/auto_tune.py` executes nightly to adjust `TIMEFRAME_RULES` in `config.py` based on the previous 7 days of win rate performance.

### Directional Seasoning
Thresholds automatically relax for the "path of least resistance" based on:
- **Funding Rate:** Tighter for crowded sides, looser for the "fade."
- **HTF Cascade:** Bonuses for alignment with 4H and 1H trends.

---

## 📈 Performance Tracking

- **Morning Briefing:** Check `reports/morning_briefing.md` every morning for a summary of the last 24h performance.
- **Resolved Trades:** Full trade history and outcome tracking are stored in `logs/pid-129-alerts.jsonl` and mirrored in the dashboard's `Performance Metrics`.

---

## 🧪 Testing

```bash
# Run full suite (Intelligence + System)
PYTHONPATH=. python -m pytest tests/ -v
```

---

_v31.0 | EMBER | Highest Conviction Trading Intelligence_
