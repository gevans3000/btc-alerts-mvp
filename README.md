# BTC Alerts MVP 🚀

High-signal long/short opportunity alerts for **BTC** (primary) and **SPX proxy** (secondary), optimized for **5m / 15m / 1h** timeframes.

**Project:** PID-129 — EMBER Progressive Capability Loop
**Status:** Production-Ready (v1.1)
**Last Updated:** 2026-02-16

---

## Overview

This system generates **LONG/SHORT/NO-TRADE** alerts with **0-100 confidence scores**, specific **entry zones**, and **dynamic trade plans** (TP1/TP2, invalidation, R:R).

### Key Features

- **Multi-timeframe analysis:** 5m / 15m / 1h (candles, indicators, regimes)
- **Advanced indicators:** RSI divergence, candle patterns (engulfing/pin bars), volume delta, swing levels
- **Session-aware scoring:** Different strategy weights for Asia, Europe, US, Weekend
- **Confluence gating:** Tier A+ requires 3+ confirming factors
- **Macro risk filter:** VIX-aware gating (spikes or extreme levels block breakouts)
- **Dynamic TP/SL:** Adjusted by volatility regime and swing levels
- **OpenClaw governance:** Multi-platform support (systemd/Mac, PowerShell/Windows), health checks, watchdogs, scorecards
- **Remote operations:** Full control from Mac mini to Windows PC / Nitro 5

### Quick Start

```bash
# Mac / Linux
./run.sh --once

# Windows
.\run.ps1 --once
```

This fetches data, computes scores, and prints the best setup.

---

## Architecture

```
BTC Alerts MVP (PID-129)
├── app.py                    # Flask/CLI application (main entry)
├── engine.py                 # Signal engine (scoring, detectors, arbitration)
├── config.py                 # Configuration & thresholds
├── utils.py                  # Utility functions (indicators, patterns, stats)
├── collectors/               # Data collectors (Kraken, Bybit, Yahoo, etc.)
│   ├── base.py              # BudgetManager, HTTP retry wrapper
│   ├── price.py             # Price snapshots, candles, macro context
│   ├── derivatives.py       # Derivatives data (OI, funding rates)
│   ├── flows.py             # Flow data (account ratios, crowding)
│   └── social.py            # Fear & Greed, news headlines
├── scripts/
│   └── pid-129/
│       ├── healthcheck.sh    # Health check script (gatekeeper)
│       └── generate_scorecard.py  # Daily scorecard generator
├── logs/
│   ├── pid-129-alerts.jsonl  # Alert history (JSONL)
│   ├── pid-129-health.log    # Health check logs
│   └── pid-129-watchdog.log  # Watchdog logs
├── reports/
│   └── pid-129-daily-scorecard.md  # Daily summary
├── GOVERNANCE.md             # PID-129 OpenClaw governance contract
├── PHASE_ROADMAP.md          # Phase roadmap for AI agents
└── run.sh                    # Bootstrap script (venv, install, run)
```

---

## Usage

### Run Once (Test Mode)

```bash
./run.sh --once
```

**Example Output:**
```text
==================================================
  MARKET OVERVIEW: BTC
==================================================
  TIMEFRAME  | ACTION     | DIRECTION  | SCORE
--------------------------------------------------
  5m         | SKIP       | SHORT      | 23
  15m        | SKIP       | SHORT      | 28
  1h         | TRADE      | LONG       | 85
==================================================

==================================================
  BEST SETUP: BTC (1h)
==================================================
  • ACTION:      TRADE (A+)
  • DIRECTION:   LONG
  • CONFIDENCE:  85/100
  • STRATEGY:    TREND_CONTINUATION
--------------------------------------------------
  • ENTRY ZONE:  95,200-95,400
  • TARGET 1:    $96,800.00
  • TARGET 2:    $98,500.00
  • STOP LOSS:   $94,500.00
  • R:R RATIO:   2.30
--------------------------------------------------
  • REASONS:     Momentum supports LONG setup, RSI_DIVERGENCE
==================================================
```

### Run Continuously (Service Mode)

```bash
# Start Service (Mac/Linux)
./scripts/pid-129/install_services.sh
systemctl --user start pid-129-btc-alerts.service

# Start Service (Windows)
.\run.ps1 --loop
```

### Health Check

```bash
# Local (Mac/Linux)
./scripts/pid-129/healthcheck.sh

# Local (Windows)
.\scripts\pid-129\healthcheck.ps1

# Remote (example)
ssh <target> "<path>/scripts/pid-129/healthcheck.sh"
```

### Generate Daily Scorecard

```bash
./scripts/pid-129/generate_scorecard.py
```

Output: `reports/pid-129-daily-scorecard.md`

---

## Configuration

Tune thresholds centrally in `config.py`:

### Regime Detection
```python
REGIME = {
    "adx_trend": 24,
    "slope_trend": 0.003,
    "atr_rank_chop": 70,
    "adx_chop": 20,
}
```

### Detector Thresholds
```python
DETECTORS = {
    "donchian_lookback": 20,
    "zscore_period": 20,
    "zscore_extreme": 1.8,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "volume_multiplier": 1.4,
}
```

### Timeframe Rules
```python
TIMEFRAME_RULES = {
    "5m": {"min_rr": 1.35, "trade_long": 74, "trade_short": 26, "watch_long": 60, "watch_short": 40},
    "15m": {"min_rr": 1.25, "trade_long": 72, "trade_short": 28, "watch_long": 58, "watch_short": 42},
    "1h": {"min_rr": 1.15, "trade_long": 68, "trade_short": 32, "watch_long": 56, "watch_short": 44},
}
```

### Session Weights
```python
SESSION_WEIGHTS = {
    "asia": {"BREAKOUT": 0.5, "MEAN_REVERSION": 1.3, "TREND_CONTINUATION": 0.7, "VOLATILITY_EXPANSION": 0.6},
    "europe": {"BREAKOUT": 1.2, "MEAN_REVERSION": 0.9, "TREND_CONTINUATION": 1.0, "VOLATILITY_EXPANSION": 1.1},
    "us": {"BREAKOUT": 1.1, "MEAN_REVERSION": 0.8, "TREND_CONTINUATION": 1.3, "VOLATILITY_EXPANSION": 1.2},
    "weekend": {"BREAKOUT": 0.6, "MEAN_REVERSION": 1.1, "TREND_CONTINUATION": 0.7, "VOLATILITY_EXPANSION": 0.5},
    "unknown": {"BREAKOUT": 1.0, "MEAN_REVERSION": 1.0, "TREND_CONTINUATION": 1.0, "VOLATILITY_EXPANSION": 1.0},
}
```

### TP/SL Multipliers
```python
TP_MULTIPLIERS = {
    "trend": {"tp1": 1.8, "tp2": 3.0, "inv": 1.1},
    "range": {"tp1": 1.2, "tp2": 2.0, "inv": 0.9},
    "vol_chop": {"tp1": 1.0, "tp2": 1.6, "inv": 0.8},
    "default": {"tp1": 1.6, "tp2": 2.8, "inv": 1.1},
}
```

---

## Indicators & Strategies

### Technical Indicators
- **EMA:** Exponential Moving Average (9/21)
- **RSI:** Relative Strength Index (14-period)
- **RSI Divergence:** Bullish/bearish divergence detection
- **Bollinger Bands:** 20-period, 2σ
- **ADX:** Average Directional Index (14-period)
- **ATR:** Average True Range (14-period)
- **VWAP:** Volume Weighted Average Price
- **Donchian Break:** 20-period breakouts
- **Z-Score:** Statistical deviation

### Candle Patterns
- **Engulfing:** Bullish/bearish engulfing candles
- **Pin Bar:** Hammer/shooting star

### Strategies
- **BREAKOUT:** Price breaking key levels
- **MEAN_REVERSION:** Reversion to average
- **TREND_CONTINUATION:** Trend following
- **VOLATILITY_EXPANSION:** Volatility expanding

### Session Weights
- **Asia (00-08 UTC):** Lower breakout probability
- **Europe (08-13 UTC):** Breakout session
- **US (13-21 UTC):** Trend continuation, highest volume
- **Weekend:** Low liquidity, wider stops

---

## Alert Schema (JSONL)

```json
{
  "pid": "129",
  "symbol": "BTCUSD",
  "bias": "LONG|SHORT|NO-TRADE",
  "confidence": 85,
  "strategy": "TREND_CONTINUATION",
  "entry": 95300.0,
  "tp1": 96800.0,
  "tp2": 98500.0,
  "invalidation": 94500.0,
  "risk": "low",
  "reason": ["MOMENTUM_SUPPORTS_LONG", "RSI_DIVERGENCE"],
  "telegram_failed": false,
  "timestamp": "2026-02-16T10:00:00Z"
}
```

---

## Testing

```bash
# Run all tests
PYTHONPATH=. python3 tests/test_utils_engine.py

# Run with coverage (optional)
pip install pytest-cov
pytest tests/ --cov=. --cov-report=html
```

---

## OpenClaw Governance

### Systemd Services

**Main Service** (`pid-129-btc-alerts.service`):
- Runs alert loop continuously
- Restarts on failure (10s backoff)
- Logs to `logs/service.log`

**Watchdog** (`pid-129-watchdog.service`):
- Runs health check every cycle
- Restarts service if unhealthy
- Logs to `logs/pid-129-watchdog.log`

### Health Check Gate

**Script:** `scripts/pid-129/healthcheck.sh`

**Checks:**
1. ✅ Service running status
2. ✅ Log files exist
3. ✅ Data freshness (alert timestamps)
4. ✅ Recent alerts (last 30 minutes)
5. ✅ Python venv available
6. ✅ Required directories exist

**Exit Codes:**
- `0` = HEALTHY
- `1` = UNHEALTHY
- `2` = CHECK FAILED

### Remote Operations (Mac mini → Nitro 5)

```bash
# Status check
openclaw ssh nitro5 "systemctl --user status pid-129-btc-alerts.service"

# View logs
openclaw ssh nitro5 "journalctl --user -u pid-129-btc-alerts.service -n 200"

# Restart service
openclaw ssh nitro5 "systemctl --user restart pid-129-btc-alerts.service"

# Manual alert cycle
openclaw ssh nitro5 "cd /Users/superg/btc-alerts-mvp && .venv/bin/python3 app.py --once"

# Health check
openclaw ssh nitro5 "./scripts/pid-129/healthcheck.sh"

# Generate scorecard
openclaw ssh nitro5 "./scripts/pid-129/generate_scorecard.py"
```

### Daily Scorecard

**Schedule:** Midnight UTC daily
**Generator:** `scripts/pid-129/generate_scorecard.py`
**Output:** `reports/pid-129-daily-scorecard.md`

**Includes:**
- Total alerts (24h)
- LONG/SHORT/NO-TRADE breakdown
- Confidence distribution
- Strategy breakdown
- Reason code breakdown
- Telegram send status
- Insights (bias detection, quality patterns)
- Recent alerts (last 5)

---

## Failure & Outcome Matrix

| Failure Mode | Detection | Action | Escalation |
|--------------|-----------|--------|------------|
| Service not running | Health check | Restart service | Log + notify EMBER |
| Service crashloop | Health check + logs | Restart + inspect logs | Notify EMBER |
| Missing credentials | Health check + logs | Pause only this step | Trigger onboarding prompt |
| API error | Alert generation | Retry 3x + NO-TRADE fallback | Log + notify EMBER |
| Market data stale | Health check | Suppress signal + NO-TRADE | Log + notify EMBER |
| Telegram send failure | Alert generation | Retry with backoff | Queue local alert + notify EMBER |
| Disk/log pressure | Health check | Rotate/compress logs | Log + notify EMBER |

---

## Phased Improvements

This project follows a **2-hour progressive capability loop** (EMBER's PID-129). See **PHASE_ROADMAP.md** for the complete roadmap:

### Current Phase: Phase 1
**Core Signal Quality Improvements**
- A. Advanced Technical Indicators
- B. Enhanced Market Regime Classification
- C. Better Trade Plan Accuracy

### Future Phases
- Phase 2: Operational Excellence (logging, replay, tests)
- Phase 3: Advanced Features (multi-exchange, ML, paper trading)
- Phase 4: Production Hardening (security, reliability, performance)

### Execution Guidelines
1. Read `GOVERNANCE.md` for PID-129 scope
2. Pick ONE sub-phase from Phase 1
3. Execute improvement
4. Evaluate before/after metrics
5. Document changes
6. Emit strict output contract (STATUS, IMPROVEMENT, DELTA, GRADE, NEXT_STEP, EVIDENCE)

---

## Free Data Sources

- **BTC Price:** Kraken → CoinGecko
- **BTC Candles:** Kraken → Bybit
- **Derivatives:** Bybit → OKX
- **SPX:** Yahoo Finance (`^GSPC`, `SPY`, `^VIX`, `NQ=F`)
- **Fear & Greed:** Alternative.me API
- **News:** CoinDesk + Cointelegraph RSS feeds

---

## License

MIT License — Use at your own risk. Do not use for financial decisions without proper validation.

---

## References

- **Governance:** `GOVERNANCE.md` (PID-129 OpenClaw contract)
- **Phase Roadmap:** `PHASE_ROADMAP.md` (Improvement phases for AI agents)
- **PID-129 Charter:** `clawd/ops/pid-129-status.md`
- **Daily Scorecard:** `reports/pid-129-daily-scorecard.md`
- **Agent Playbook:** (Referenced in PHASE_ROADMAP.md)

---

**Last Updated:** 2026-02-16
**Version:** 1.1
**Status:** Production-Ready
