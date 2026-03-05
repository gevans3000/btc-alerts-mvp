# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**BTC Alerts MVP** (PID-129 — EMBER Autonomous Trading Intelligence) generates LONG/SHORT/NO-TRADE signals for Bitcoin futures on 5m/15m/1h timeframes, with 0–100 confidence scores, entry/exit levels, and dynamic R:R plans. It is fully autonomous: self-tuning nightly, generating morning briefings at 6 AM ET, and running a continuous 5-minute monitoring loop.

## Commands

```bash
# Run one snapshot cycle
python app.py --once          # or: .\run.ps1 --once

# Run continuous 5-min monitoring loop
.\run.ps1 --loop              # Windows
./run.sh --loop               # Linux/Mac

# Run all tests
PYTHONPATH=. python -m pytest tests/ -v

# Run a single test file
PYTHONPATH=. python -m pytest tests/test_confluence.py -v

# Start the WebSocket dashboard server (http://localhost:8002)
python scripts/pid-129/dashboard_server.py

# Generate morning briefing
python scripts/morning_briefing.py

# Nightly self-tuning (adjusts TIMEFRAME_RULES based on last 7 days)
python tools/auto_tune.py

# Backtest
python tools/run_backtest.py --symbol BTC --limit 1000 --since 2025-02-01 --to 2025-02-28

# System on/off toggle
python scripts/toggle.py status|on|off

# Validate config.py tunables
python -c "from config import validate_config; validate_config()"
```

## Architecture

### Signal Pipeline

```
Data Collection (collectors/) → engine.py scoring → Alert output
     ↑                                ↑
config.py tunables          intelligence/ probes (13+)
```

1. **`app.py`** — main event loop: checks the ON/OFF flag (`DISABLED` file), fetches data every 5 minutes, calls `engine.py`, writes to `logs/pid-129-alerts.jsonl`.
2. **`engine.py`** — orchestrates intelligence probes, applies the multiplier (7.0x), normalizes to 0–100 confidence, gates on `TIMEFRAME_RULES`, applies Phase 27 vetoes (macro, flow, chop), and emits the alert dict.
3. **`config.py`** — single source of truth for all tunables. `TIMEFRAME_RULES` are auto-adjusted nightly by `tools/auto_tune.py`. Always modify thresholds here, never hardcode them.
4. **`intelligence/`** — 13+ modular probes. Each returns a point delta and a boolean signal. If a probe fails (API error, stale data), the system degrades gracefully and notes it in the alert's `degraded` field.
5. **`collectors/`** — async multi-provider data fetchers with automatic failover (Bybit → OKX → Bitunix → Kraken → FreeCryptoAPI). `collectors/base.py` hosts `BudgetManager` for rate-limiting and source blacklisting.

### Scoring Flow

```
Raw probe points → × 7.0 multiplier → normalize to 0-100
→ TIMEFRAME_RULES gate (trade_long/trade_short thresholds)
→ Confluence rubric gate (A+: ≥5/6 probes, B: ≥3/6)
→ Phase 27 vetoes: macro (1h/4h bias), flow (taker ratio), chop (value area)
→ min_rr enforcement before emitting TRADE tier
→ Alert written to logs/pid-129-alerts.jsonl
```

### Intelligence Probes (in `intelligence/`)

| File | What it detects |
|------|----------------|
| `structure.py` | BOS / CHoCH market structure breaks |
| `session_levels.py` | PDH/PDL, session high/low |
| `sweeps.py` | Equal Highs/Lows liquidity sweeps |
| `anchored_vwap.py` | Dynamic VWAP support/resistance |
| `volume_impulse.py` | Relative volume & ATR percentile |
| `oi_classifier.py` | Price-OI relationship regime |
| `volume_profile.py` | POC, VAH/VAL, LVN |
| `auto_rr.py` | Risk/reward targeting |
| `squeeze.py` | Bollinger Band + Keltner squeeze |
| `liquidity.py` | Orderbook bid/ask wall detection |
| `macro_correlation.py` | DXY & Gold trend bias |
| `sentiment.py` | News + Fear & Greed scoring |
| `confluence.py` | Heatmap aggregation across probes |
| `recipes.py` | High-conviction patterns (HTF_REVERSAL, BOS_CONTINUATION) |
| `detectors.py` | Technical candidate detection & arbitration |

### Key Data Flows

- **Logs (source of truth):** `logs/pid-129-alerts.jsonl` — append-only JSONL, one alert per line with full decision trace.
- **DNA / learning state:** `dna/dna.json` — written by `auto_tune.py`, read by `config.py` on startup.
- **Dashboard state:** `data/dashboard_overrides.json` — user filter preferences persisted across sessions.
- **Paper portfolio:** `data/paper_portfolio.json` — simulated account state updated by `tools/paper_trader.py`.
- **Morning briefing:** `reports/morning_briefing.md` and `.json` — regenerated daily at 6 AM ET.

## Configuration

All tunables live in `config.py`. Key sections:
- `TIMEFRAME_RULES` — per-timeframe confidence thresholds and min R:R; auto-adjusted nightly.
- `INTELLIGENCE_FLAGS` — feature flags to enable/disable individual probes.
- `CONFLUENCE_RULES` — point minimums for A+ and B tiers.
- `REGIME` — ADX/slope/ATR thresholds for trend vs. chop detection.

Run `validate_config()` after any manual edits to catch invalid threshold relationships.

## Governance (GOVERNANCE.md)

This project follows the PID-129 2-hour progressive improvement cycle. Each Claude session should:
1. Load current state from `logs/pid-129-alerts.jsonl` and `reports/morning_briefing.md`.
2. Complete exactly one meaningful improvement per cycle.
3. Write durable evidence to `reports/pid-129-cycle-YYYYMMDD-HHMM.md`.
4. Emit the standard output contract: `STATUS / SUBJECT / IMPROVEMENT / DELTA / GRADE / NEXT_STEP / EVIDENCE`.

Completion is blocked until test gates T1–T10 in `GOVERNANCE.md` all pass.

## Phase Documentation

- `PHASE_ROADMAP.md` — master roadmap; Phases 1–26 complete, 27+ active.
- `Phase_NN.md` files — detailed spec for each phase (source of truth for intent).
- `phase_checkups.md` — recent bug fixes and verification checklist.
- `OPERATOR.md` — dashboard operation manual (Triple Green process).
