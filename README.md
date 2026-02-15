# BTC Alerts MVP 🚀

A high-frequency Bitcoin alert system optimized for 5-minute long/short opportunities with free public data sources.

## Features
- **BTC Multi-Timeframe Context**: Kraken OHLC on 5m/15m/1h with HTF trend gating.
- **Adaptive Technicals**: RSI, Bollinger Bands, EMA trend, ATR-aware volatility regime, and VWAP context.
- **Structure Confirmation**: Swing pivot break + retest confirmation (vs wick-only breaks).
- **Derivatives + Flow Context**: Funding, OI change, basis, and crowding/squeeze proxy from free futures endpoints.
- **Macro Risk Filter**: Yahoo Finance SPX + VIX + NQ confirmation.
- **Session-Aware Logic**: Asia/Europe/US/weekend adaptive scoring.
- **Alert Tiers + Gates**: A+ / B / NO-TRADE with blockers (`HTF conflict`, `Low R:R`, `Data quality degraded`).
- **Stateful Alert Lifecycle**: Dedupe, cooldown, and tier-aware state-change alerting.

## Free Data Sources Used
- Kraken public API (ticker + OHLC)
- CoinGecko public API (BTC spot fallback)
- Binance Futures public endpoints (funding, OI, positioning ratios)
- Bybit public endpoints (derivatives fallback)
- Alternative.me Fear & Greed API
- CoinDesk + Cointelegraph RSS feeds
- Yahoo Finance chart endpoints (`^GSPC`, `^VIX`, `NQ=F`)

## Fallback Behavior
- Any source can fail independently; engine continues in degraded mode.
- Degraded feeds are reflected in `quality` (e.g., `degraded:derivatives,flows,vix`).
- If Telegram env vars are missing, alerts print to stdout.

## Alert Output
Each alert includes:
- Action (`TRADE`, `WATCH`, `SKIP`) and tier (`A+`, `B`, `NO-TRADE`)
- Direction (`LONG`, `SHORT`, `NEUTRAL`) and confidence score
- Entry zone, invalidation, TP1/TP2, and R:R
- Top reasons and blockers
- Data quality status

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
