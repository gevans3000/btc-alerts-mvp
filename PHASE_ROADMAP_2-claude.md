# BTC Alerts MVP — Roadmap Part 2: Execution & Edge

*Phases 1–28 built the signal engine. Everything below is what's NOT yet built.*

> **Already operational (do NOT re-implement):** price aggregation (7 sources), orderbook depth, funding/OI, taker ratio, macro DXY/Gold/SPX/VIX, sentiment F&G+RSS, volume profile, squeeze, liquidity walls, confluence scoring, recipes, auto-tune. All live in `collectors/` and `intelligence/`.

---

## Phase 29: Dynamic Position Sizing

Size positions by edge strength instead of flat risk.

- Fractional Kelly: `f = (WR × avgWin - (1-WR) × avgLoss) / avgWin`, capped at half-Kelly
- A+ trades → up to 2% risk; B trades → 0.5% risk (if ever un-gated)
- Pull sizing from rolling 30-trade window per regime (trend vs range)
- Hard ceiling: never risk >3% of account on any single trade

---

## Phase 30: Active Trade Management

Once in a trade, manage it instead of set-and-forget.

- Move SL to breakeven after +1R
- Trail stop using 2× ATR on the entry timeframe
- Partial exit: close 50% at TP1, trail remainder to TP2
- If funding flips against position >0.03%, tighten stop to 0.5× ATR
- All logic in a new `tools/trade_manager.py` polling every 60s

---

## Phase 31: Liquidation Heatmap

New data source — liquidation clusters reveal where price is magnetized.

- Estimate liquidation levels from OI + leverage distribution (OKX API provides leverage tiers)
- Build simplified heatmap: heavy liquidation zones above/below current price
- Feed into `auto_rr.py`: set TP targets near liquidation clusters (liquidity magnets)
- Feed into `detectors.py`: avoid entries where nearby liquidation cluster is against trade direction
- Fallback: derive from historical wicks + volume profile LVNs

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

## Implementation Priority

| Phase | Value | Effort | Do When |
|-------|-------|--------|---------|
| 29 — Position Sizing | High | Low | First — immediate edge improvement |
| 30 — Trade Management | High | Medium | Second — stops profit leakage |
| 34 — Push Notifications | High | Low | Third — solves the "not watching" problem |
| 35 — Circuit Breakers | High | Low | Fourth — prevents ruin |
| 31 — Liquidation Heatmap | Medium | Medium | When core execution is solid |
| 33 — Performance Attribution | Medium | Medium | After 50+ trades for statistical significance |
| 32 — On-Chain Edge | Medium | Medium | Incremental alpha, not urgent |
| 36 — Multi-Asset | Low | High | Only after BTC system is proven profitable |

---

## Data Source Matrix (Active)

| Category | Primary | Backup 1 | Backup 2 | Last Resort |
|----------|---------|----------|----------|-------------|
| Price | Kraken | OKX | Bitunix | CoinGecko/FreeCryptoAPI |
| Orderbook | OKX | Bitunix | Bitstamp | — |
| Funding/OI | OKX | Bitunix | — | — |
| Flows | OKX | — | — | — |
| Macro | Yahoo Finance | — | — | — |
| Sentiment | Alternative.me | RSS/CryptoPanic | — | — |
| On-Chain | Blockchain.com | — | — | — |

---

_v2.0 | EMBER | Signal engine complete — now optimize execution._
