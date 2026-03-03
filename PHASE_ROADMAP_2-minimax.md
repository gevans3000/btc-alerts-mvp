# BTC Alerts MVP — Future Roadmap Part 2: Data & Execution Optimization

*Focus: Maximum free API coverage with geo-compliant sources for the best dashboard-driven trading decisions.*

---

## Phase 34: Multi-Source Price Aggregation 📅 PRIORITY

**Objective:** Get the most reliable BTC price from multiple geo-compliant sources with intelligent failover.

**Tasks:**
- Consolidate Kraken → OKX → Bybit → Bitunix → Coinbase → Bitstamp → CoinGecko
- Add **CoinCap** (no API key needed) as free backup price source
- Add **CryptoCompare** free tier for volume/price confirmation
- Cache prices with 30-second staleness indicator
- Show "price consensus" deviation on dashboard (alert if sources diverge >0.5%)

**Free Limits Available:**
| Source | Calls/min | Use Case |
|--------|-----------|----------|
| Kraken | 24 | Primary price |
| OKX | 30 | Backup price + funding |
| Bybit | 24 | Price + derivatives |
| Bitunix | 100 | High-frequency data |
| CoinGecko | 10 | Slow backup |
| CoinCap | ∞ | No-auth backup |

---

## Phase 35: Orderbook Liquidity Intelligence 📅 PRIORITY

**Objective:** Real-time microstructure for spread/slippage estimation.

**Tasks:**
- Chain: Bybit → OKX → Bitunix → Bitstamp
- Calculate: spread (bps), top-of-book depth, impact estimate for 5k/10k sweeps
- Display "EXECUTE MODE" on dashboard: FAST / DEFENSIVE / BLOCKED
- Auto-block market orders when spread >3bps or impact >80bps

---

## Phase 36: Derivatives Context (Funding + OI) 📅 PRIORITY

**Objective:** Cross-exchange funding rate and open interest for regime detection.

**Tasks:**
- Fetch Bybit funding rate + OI change (every 5min)
- Fetch OKX funding rate + OI change (every 5min)
- Calculate "funding delta" between exchanges (arbitrage signal)
- Show on dashboard: funding_rate, oi_change_pct, basis_pct
- Alert when funding extremely elevated (|funding| > 0.05%)

**Free Limits:**
| Source | Calls/min | Data |
|--------|-----------|------|
| Bybit | 24 | Funding, OI, mark/index |
| OKX | 30 | Funding, OI, basis |

---

## Phase 37: Order Flow (Taker Ratio + Crowding) 📅 PRIORITY

**Objective:** Real-time long/short ratio and crowding indicator.

**Tasks:**
- Fetch Bybit account ratio (buy/sell, long/short)
- Fetch OKX long/short ratio
- Calculate crowding_score = weighted taker_ratio + ls_ratio
- Display: taker_ratio, long_short_ratio, crowding_score
- Dashboard color coding: GREEN (0.8-1.2) / AMBER / RED

---

## Phase 38: Macro Correlatives (DXY + Gold + SPX + VIX) 📅 PRIORITY

**Objective:** Higher-timeframe directional bias to filter signals.

**Tasks:**
- Fetch DXY (1D candles) - Yahoo Finance
- Fetch Gold/GC=F (1D candles) - Yahoo Finance
- Fetch SPX (1D candles) - Yahoo Finance  
- Fetch VIX (5m candles) - Yahoo Finance
- Calculate HTF bias: if DXY up + Gold down + SPX down → cap LONGs
- Dashboard: Show macro_trend indicator per session

**Free Limits:**
| Source | Calls/min | Data |
|--------|-----------|------|
| Yahoo | 20 | All macro assets |

---

## Phase 39: Sentiment Layer (Fear&Greed + News) 📅 MEDIUM

**Objective:** Market sentiment edge from free sources.

**Tasks:**
- Fetch Alternative.me Fear & Greed Index (5 calls/5min)
- Aggregate RSS feeds: CoinTelegraph, CoinDesk, Decrypt, Bitcoin Magazine
- Parse Reddit r/Bitcoin, r/CryptoCurrency for trending topics
- Dashboard: Display F&G value + label, top 5 headlines with source

---

## Phase 40: Multi-Timeframe Candle Expansion 📅 MEDIUM

**Objective:** Complete the TF stack for structure trading.

**Tasks:**
- Current: 5m, 15m, 1h, 4h (via Kraken/Bybit/OKX)
- **Add:** 2h, 6h, 12h, 1D candles
- Fetch from Kraken (best for higher TFs)
- Cache candles with 5-minute refresh
- Dashboard: Show which TFs have valid data

---

## Phase 41: The Dashboard Operator Panel 📅 PRIORITY

**Objective:** Unified execution-ready dashboard showing best data.

**Tasks:**
- **Data Health Bar:** Show which sources are LIVE / STALE / FAILED
- **Price Consensus:** Show all available prices with deviation %
- **Flows Panel:** taker_ratio, crowding, funding (color-coded)
- **Microstructure Panel:** spread, depth, execute mode (FAST/DEFENSIVE/BLOCKED)
- **Profit Preflight:** GREEN/AMBER/RED signal with blockers list
- **Signal Table:** Top 3 LONG + Top 3 SHORT candidates with R:R + confidence

**Key Metrics to Display:**
```
┌─────────────────────────────────────────────────────────┐
│ PRICE: $92,450 [Kraken]  spread: $2.50 (1bp)  MODE: FAST
│ FLOW: taker=1.32 (BULLISH)  crowding=+2.1  funding=+0.01%
│ OI:   +3.2% (expanding)    basis: -0.02%
├─────────────────────────────────────────────────────────┤
│ DATA SOURCES: ✓Kraken ✓OKX ✓Bybit ✓Bitunix ✓CoinGecko
├─────────────────────────────────────────────────────────┤
│ BEST LONG: confidence=78 R:R=2.4 age=45s recipe=BOS_LIQ
│ GATE: GREEN ✓ → EXECUTE READY
└─────────────────────────────────────────────────────────┘
```

---

## Phase 42: Data Quorum & Fallback Logic 📅 PRIORITY

**Objective:** Graceful degradation when APIs fail.

**Tasks:**
- Define minimum viable sources: price + orderbook + flows + derivatives
- If <3/4 sources healthy → show AMBER warning
- If <2/4 sources healthy → show RED alert, disable execution
- Auto-switch to backup sources when primary fails
- Log source failures for debugging

---

## Phase 43: Budget Manager Rate Limit Optimization 📅 LOW

**Objective:** Maximize data extraction within free tier limits.

**Tasks:**
- Track API calls per source in `.budget.json`
- Distribute calls across the 5-minute cycle (no bursts)
- Priority queue: Price/Orderbook (high freq) → Flows/Derivatives (medium) → Macro (low)
- Auto-blacklist sources that return 403 errors for 5 minutes
- Dashboard: Show "budget remaining" per source

---

## Phase 44: Self-Tuning & Auto-Optimization 📅 FUTURE

**Objective:** System learns which sources/data are most predictive.

**Tasks:**
- Track win rate per signal with specific source configuration
- Weight sources by historical correlation to price movement
- Auto-disable low-value sources during low-confidence periods
- Weekly report: which data sources contributed to wins

---

## Removed from Original Roadmap

| Original Phase | Reason Removed |
|---------------|----------------|
| Phase 34 (Auto-Kelly) | Position sizing - not data related |
| Phase 35 (1-Click Execution) | Execution layer - separate roadmap |
| Phase 36 (Slippage Defense) | Already implemented in Phase 35 |
| Phase 37 (Trailing Stop) | Trade management - separate roadmap |
| Phase 38 (PnL Feedback) | Already exists in auto_tune.py |
| Phase 39 (God Button) | Redundant - confluence already exists |
| Phase 40 (30-Day Trial) | Validation step, not phase |
| Phase 41 (Daily Valve) | Covered by Phase 38 (Macro) |

---

## Data Source Matrix

| Category | Primary | Backup 1 | Backup 2 | Backup 3 |
|----------|--------|----------|----------|----------|
| Price | Kraken | OKX | Bitunix | CoinCap |
| Orderbook | Bybit | OKX | Bitunix | Bitstamp |
| Funding/OI | Bybit | OKX | Bitunix | - |
| Flows | Bybit | OKX | - | - |
| Macro | Yahoo | - | - | - |
| Sentiment | Alt.me | RSS feeds | - | - |

---

## Implementation Order

1. **Phase 34** → Price aggregation + CoinCap fallback
2. **Phase 35** → Orderbook + microstructure
3. **Phase 36** → Derivatives (funding/OI)
4. **Phase 37** → Order flow (taker ratio)
5. **Phase 38** → Macro context (DXY/Gold/SPX/VIX)
6. **Phase 39** → Sentiment layer
7. **Phase 40** → Additional TFs
8. **Phase 41** → Dashboard operator panel
9. **Phase 42** → Quorum + fallback logic
10. **Phase 43** → Budget optimization
11. **Phase 44** → Self-tuning

---

_v44.0 | EMBER Collective | Data-First Trading Intelligence_
