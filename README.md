# BTC Alerts MVP 🚀

High-signal long/short opportunity alerts for **BTC** (primary) and **SPX proxy** (secondary), optimized for **5m / 15m / 1h**.

## Features
- **Regime classifier**: trend vs range vs volatility-chop gating.
- **4 strategy detectors**: breakout, trend continuation, mean reversion, volatility expansion.
- **Conflict arbitration**: opposing setup suppression with `CONFLICT_SUPPRESSED` reason code.
- **Multi-timeframe alignment**: 5m/15m entries validated against 1h bias.
- **Confidence model (0-100)** with per-factor breakdown and reason codes.
- **ATR-normalized trade plan**: entry zone, invalidation, TP1/TP2, R:R.
- **Stateful dedupe/cooldowns** for low-noise alerts.
- **Transport-ready JSON payloads** (Telegram-ready, integration optional).
- **Decision traces** for fired/filtered alert diagnostics.

## Free Data Sources (No Binance)
- Kraken public API (spot ticker + OHLC)
- Bybit public API (spot candles, derivatives, account-ratio flow)
- OKX public API (derivatives fallback)
- CoinGecko public API (BTC spot fallback)
- Yahoo Finance chart endpoints (`^GSPC`, `SPY`, `^VIX`, `NQ=F`)
- Alternative.me Fear & Greed API
- CoinDesk + Cointelegraph RSS feeds

## Provider + Fallback Policy
- Shared HTTP retry/backoff wrapper is used for collectors.
- BTC price: Kraken → CoinGecko.
- BTC candles: Kraken → Bybit.
- Derivatives: Bybit → OKX.
- SPX: direct `^GSPC` first, fallback to `SPY` proxy by timeframe.

## Config + Tuning
Tune thresholds centrally in `config.py`:
- regime thresholds (`REGIME`)
- detector thresholds (`DETECTORS`)
- timeframe gates and R:R (`TIMEFRAME_RULES`)
- stale limits (`STALE_SECONDS`)
- cooldowns (`COOLDOWN_SECONDS`)

Recommended loop:
1. Replay on historical candles (`tools/replay.py`)
2. Adjust `config.py`
3. Run tests
4. Run `app.py --once`

## Alert Output Shape
Each alert includes:
- `symbol`, `timeframe`, `action`, `tier`, `direction`, `strategy_type`
- `confidence_score`
- `entry_zone`, `invalidation_level`, `tp1`, `tp2`, `rr_ratio`
- `context` (regime/session/quality/providers)
- `reason_codes`, `score_breakdown`, `blockers`
- `decision_trace`

## Getting Started
1. Optional Telegram env vars:
   ```env
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```
2. Run once:
   ```bash
   ./run.sh --once
   ```
3. Run continuously (5m loop):
   ```bash
   ./run.sh
   ```

## Testing
- `pytest -q`
- `python -m unittest discover -s tests -q`

## Requirements
- Python 3.12+
- `httpx`
- `python-dotenv`
