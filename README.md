# BTC Alerts MVP 🚀

A high-frequency Bitcoin alert system optimized for 5-minute long/short opportunities with free public data sources.

## Features
- **BTC Multi-Timeframe Context**: Kraken OHLC on 5m/15m/1h with HTF trend gating.
- **Adaptive Technicals**: RSI, Bollinger Bands, EMA trend, ATR-aware volatility regime (compression/expansion).
- **Market Structure Detection**: Break of structure, failed breakout/fakeout, reclaim detection.
- **SPX Risk Filter**: Yahoo Finance 5m SPX trend context to modulate BTC conviction.
- **Stateful Alert Lifecycle**: Dedupe, cooldown, and meaningful state-change alerting.
- **Sentiment + News**: Fear & Greed + crypto RSS catalyst scans.

## Free Data Sources Used
- Kraken public API (ticker + OHLC)
- CoinGecko public API (BTC spot fallback)
- Alternative.me Fear & Greed API
- CoinDesk + Cointelegraph RSS feeds
- Yahoo Finance chart endpoint for SPX (`^GSPC`)

## Fallback Behavior
- Any source can fail independently; engine continues in degraded mode.
- Degraded feeds are reflected in `quality` (e.g., `degraded:spx,derivatives`).
- If Telegram env vars are missing, alerts print to stdout.

## Getting Started
1. **Setup environment variables** (optional for Telegram):
   ```env
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```
2. **Run once**:
   ```bash
   ./run.sh --once
   ```
3. **Run continuously on 5m clock**:
   ```bash
   ./run.sh
   ```

## Requirements
- Python 3.12+
- `httpx`
- `python-dotenv`
