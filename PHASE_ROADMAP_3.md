# BTC Alerts MVP — Roadmap Part 3: Intelligence & Scale

*Phases 32–39 extend the signal engine with new data sources, attribution, notifications, and risk management — then scale to multi-asset.*

> **Prerequisite:** Phases 1–31 (signal engine + execution optimization) should be solidly deployed before starting this roadmap.

---

## Phase 32: On-Chain Edge

Exchange flow data signals accumulation vs distribution before price moves.

- Track BTC exchange net flows via Blockchain.com free API (inflows − outflows)
- Large inflow spike → distribution (bearish); large outflow → accumulation (bullish)
- New probe `intelligence/onchain.py`: returns directional bias + confidence delta
- Refresh every 15 minutes (on-chain data is slow; no need for 5m polling)
- Gate: only apply when net flow exceeds ±500 BTC/day (filter noise)

---

## Phase 33: Performance Attribution

Know which probes actually predict, and weight them accordingly.

- For each closed trade, record which probes were active and their directional vote
- After 50+ trades, compute per-probe hit rate and average R contribution
- Auto-adjust probe weights in `CONFLUENCE_RULES` (probes with <40% hit rate get 0.5× weight)
- Weekly report: `reports/probe_attribution.json` with ranked probe effectiveness
- Dashboard panel: probe leaderboard (best → worst predictors)

---

## Phase 34: Push Notifications

A+ signals are useless if you're not watching the dashboard.

- Telegram bot: send A+ alerts with entry/SL/TP/confidence/recipe
- Include 1-tap "Execute" deep link back to dashboard
- Rate limit: max 6 alerts per hour (prevent spam in choppy markets)
- Daily summary at market close: trades taken, P&L, top signal missed
- Config: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars

---

## Phase 35: Circuit Breakers & Risk Limits

Prevent catastrophic sessions before they happen.

- Daily loss limit: halt execution after −3R cumulative in a session
- Drawdown breaker: if account drops −5% from peak, switch to WATCH-only for 24h
- Correlation guard: if 2+ open positions share >0.7 correlation, block new entries
- Volatility pause: if 5m ATR spikes >3× its 20-period average, pause for 15 minutes
- All limits configurable in `config.py` under `RISK_LIMITS`

---

## Phase 36: Multi-Asset Expansion

Apply the same engine to ETH and SOL.

- Abstract `engine.py` to accept a `symbol` parameter
- Reuse all probes — only `collectors/` endpoints need per-asset config
- Separate `TIMEFRAME_RULES` per asset in `config.py`
- Dashboard: tabbed view (BTC | ETH | SOL) with independent signal tables
- Cross-asset filter: if BTC is in freefall, suppress altcoin longs

---

## Phase 37: Walk-Forward Optimization

Rolling validation to prevent overfitting before nightly auto-tune.

- Every 7 days (or on-demand), run 30-day rolling backtest against historical data
- Proposed `TIMEFRAME_RULES` adjustments from auto-tune are tested against this window before apply
- Only apply auto-tune deltas if walk-forward P&L exceeds threshold (e.g., +0.5R)
- Store rejected tunings in `reports/rejected_tunings.json` for audit trail
- Prevents stale-regime overfitting that whipsaws execution

---

## Phase 38: TradingView Webhook Ingest

Blend retail confluence into the signal engine.

- Accept TradingView Pine Script alerts via webhook (`/api/tradingview` endpoint)
- Parse alert JSON: symbol, timeframe, signal (LONG/SHORT/CLOSE), severity (optional)
- Add as 14th probe `intelligence/tradingview.py`: returns binary directional vote (high confidence only)
- Weight this probe lightly in confluence (retail signals are noisy, but useful for confirmation)
- Dashboard alert: shows which TradingView alerts fed into each decision
- Rate limit: max 20 TradingView ingest per 5-minute window

---

## Phase 39: Session Journal & Replay

Auditable record of every trade with context.

- Per-signal, record in new `logs/journal/` JSONL: entry time, rationale snapshot (active probes), screenshot URL, manual notes (optional)
- Post-trade, append outcome: exit time, exit price, P&L, actual vs expected R
- Daily journal report: `reports/journal_YYYYMMDD.md` with summary stats and top trade narrative
- Replay feature: dashboard can load a past alert and show "what would you trade today?" as a backtest
- Enables root-cause analysis of missed signals and false exits

---

## Implementation Priority

| Phase | Value | Effort | Do When |
|-------|-------|--------|---------|
| 32 — On-Chain Edge | Medium | Medium | Incremental alpha, good early addition |
| 33 — Performance Attribution | Medium | Medium | After 50+ trades for statistical significance |
| 34 — Push Notifications | High | Low | High-value engagement layer |
| 35 — Circuit Breakers | High | Low | Prevents catastrophe, deploy early |
| 36 — Multi-Asset | Low | High | Only after BTC system is proven profitable |
| 37 — Walk-Forward Optimization | High | Medium | Critical guard against overfitting |
| 38 — TradingView Webhook | Medium | Low | Nice-to-have retail confirmation |
| 39 — Session Journal & Replay | Medium | Medium | Essential for performance audit |

---

## Data Source Matrix (Phases 32–39)

| Category | Primary | Backup 1 | Backup 2 | Last Resort |
|----------|---------|----------|----------|-------------|
| Price | Kraken | OKX | Bitunix | CoinGecko/FreeCryptoAPI |
| Orderbook | OKX | Bitunix | Bitstamp | — |
| Funding/OI | OKX | Bitunix | — | — |
| Flows | OKX | — | — | — |
| On-Chain | Blockchain.com | — | — | — |
| Macro | Yahoo Finance | — | — | — |
| Sentiment | Alternative.me | RSS/CryptoPanic | — | — |
| TradingView | Webhook Ingest | — | — | — |

---

_v3.0 | EMBER | Long-horizon intelligence and scale_
