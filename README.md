# BTC Alerts MVP 🚀

High-signal long/short opportunity alerts for **BTC** (primary) and **SPX proxy** (secondary), optimized for **5m / 15m / 1h**.

## New in v1.1 (Phase 1 & 2 Improvements)
- **Advanced Indicators**: Added VWAP, RTI (Relative Trend), RSI Divergence, and Volume Delta.
- **Pattern Recognition**: Bullish/Bearish Engulfing and Hammer/Shooting Star pin bars.
- **Dynamic S/R Levels**: Support and Resistance detected from swing points for smart TP/SL placement.
- **Session-Aware Weighting**: Different strategy weights for Asia, Europe, US, and Weekend sessions.
- **Confluence Gating**: Tier A+ alerts now require higher confluence (e.g., trend + momentum + vol + pattern).
- **Macro Risk Filter**: VIX-aware gating (spikes or extreme levels block breakouts).

## Features
- **Regime classifier**: trend vs range vs volatility-chop gating.
- **4 base strategy detectors**: breakout, trend continuation, mean reversion, volatility expansion.
- **Conflict arbitration**: opposing setup suppression with `CONFLICT_SUPPRESSED` and HTF tie-breaking.
- **Multi-timeframe alignment**: entries validated against HTF (15m/1h) bias.
- **Confidence model (0-100)** with per-factor breakdown and reason codes.
- **Smart Trade Plan**: entry zone, invalidation, TP1/TP2, R:R adjusted by regime and S/R levels.
- **Stateful dedupe/cooldowns**: smart cooldowns and TP1 transition logic to minimize noise.

## Free Data Sources
- Kraken public API (spot ticker + OHLC)
- Bybit public API (spot candles, derivatives, account-ratio flow)
- OKX public API (derivatives fallback)
- CoinGecko public API (BTC spot fallback)
- Yahoo Finance chart endpoints (`^GSPC`, `SPY`, `^VIX`, `NQ=F`)
- Alternative.me Fear & Greed API
- CoinDesk + Cointelegraph RSS feeds

## Provider + Fallback Policy
- Shared HTTP retry/backoff wrapper for collectors.
- BTC price: Kraken → CoinGecko.
- BTC candles: Kraken → Bybit.
- Derivatives: Bybit → OKX.
- SPX: direct `^GSPC` first, fallback to `SPY` proxy by timeframe.

## Config + Tuning
Tune thresholds centrally in `config.py`:
- regime thresholds (`REGIME`)
- detector thresholds (`DETECTORS`)
- timeframe gates and R:R (`TIMEFRAME_RULES`)
- session weights (`SESSION_WEIGHTS`)
- confluence requirements (`CONFLUENCE_RULES`)
- dynamic TP multipliers (`TP_MULTIPLIERS`)

Recommended tuning loop:
1. Replay on historical candles (`tools/replay.py`)
2. Adjust `config.py`
3. Run tests (`tests/test_utils_engine.py`)
4. Run `app.py --once`

## Testing
```bash
PYTHONPATH=. python3 tests/test_utils_engine.py
```

## Requirements
- Python 3.9+
- `httpx`
- `python-dotenv`
