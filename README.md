# BTC Alerts MVP 🚀

A minimal, high-frequency Bitcoin alert system optimized for 5-minute scalping.

## Features
- **Kraken Integration**: Real-time ticker and OHLC data from Kraken.
- **Technical Indicators**: 5m RSI (14), Bollinger Bands (20, 2), and EMA Crosses (9/21).
- **Sentiment Analysis**: Integration with Fear & Greed Index and crypto news RSS feeds.
- **Scalping Logic**: Specialized engine designed to surface Long/Short signals for fast trades.
- **Telegram Notifications**: Easy integration via environment variables.

## Getting Started

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd btc-alerts-mvp
   ```

2. **Setup environment variables**:
   Create a `.env` file with:
   ```env
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

3. **Run the system**:
   The `run.sh` script handles virtual environment creation and dependency installation automatically.
   ```bash
   chmod +x run.sh
   ./run.sh
   ```

## Requirements
- Python 3.12+
- `httpx`
- `python-dotenv`
