# BTC Alerts MVP — Roadmap Part 3: Intelligence, Edge & Calibration

## Critical Issues I See Right Now

Before adding features, there are problems in the current data that would hurt profitability:

**1. Calibration Drift is Real and Dangerous.** Your 61-80 confidence bin has a 54.5% WR with **-0.37R avg** on 11 trades. That means your model is actively losing money on trades it rates as fairly confident. Meanwhile, 41-60 bin has 60% WR at +0.22R. This inversion is a red flag — your confidence scoring in that mid-high band is broken and needs retraining or recalibration.

**2. Win Rate (7d) is 0.45%.** That's essentially zero. Combined with Avg R of 1.14, this suggests either very few winners that are large, or a data display bug. If real, you're relying entirely on outsized winners to compensate for a near-zero hit rate — extremely fragile.

**3. Kelly % at 1.44% is Tiny.** With that win rate and R, Kelly is telling you the edge is barely there. You should be trading extremely small (which the $202 daily risk cap seems to enforce).

**4. Data Quorum Insufficient.** Both the best long AND best short candidates show "missing: orderbook, flows, derivatives." This means your system is flying partially blind. The confluence radar shows 0 green / 0 red / 15 gray — nearly everything is gray/unknown. You can't make high-conviction trades without data.

**5. 10 Active Trades All "Fresh Setup" with Identical R:R of 1.36.** Having 10 open positions (9 LONG + 1 SHORT) all showing as "Fresh setup" with the exact same planned R:R feels like the system is over-entering. There's no staggered management happening.

---

## What to Add for More Profitable Trades

Here are the highest-impact additions, ranked by how directly they would improve your P&L:

### Tier 1 — Immediate Edge Improvements

**Liquidation Heatmap / Cluster Data.** You have bid/ask walls and equal highs/lows, but you're missing actual liquidation cluster levels from exchanges. Knowing where large clusters of leveraged stops sit (e.g., from Coinglass or Hyblock-style data) tells you where price is magnetically drawn to. This is one of the highest-alpha data sources in crypto. Add a visual strip showing liquidation density above and below current price.

**CVD (Cumulative Volume Delta) on the Tape.** Your Taker Ratio (1.00) is flat, but a live CVD line or delta bar would show you the net aggression in real-time. A divergence between price going up while CVD is falling is one of the most reliable short-term reversal signals. This belongs in the Live Tape section.

**Open Interest by Exchange Breakdown.** You have aggregate OI Delta (-0.04%), but showing which exchanges are driving OI changes matters. If Binance OI is surging while Bybit is flat, that's a different setup than uniform OI growth. A small stacked bar or table would do.

**Realized vs Unrealized PnL Distinction on Positions.** Your Execution Copilot shows unrealized PnL, but you should also track realized PnL from partial fills/scales. This helps the copilot give better "take profit" advice when you've already banked some R.

---

## Implementation Roadmap (Revised)

*Phases 32–44 focus on fixing calibration drift, adding Tier 1 alpha data, hardening risk, and finally scaling.*

### Phase 32: Immediate Calibration & Quorum Fixes
**Priority:** Emergency
- **Confidence Recalibration:** Investigate the scoring inversion (61-80 bin underperforming 41-60). Adjust multipliers in `engine.py` to ensure higher confidence correlates with higher WR/R.
- **Data Quorum Hardening:** Fix the "missing: orderbook, flows, derivatives" bug. Ensure the dashboard accurately reflects collector health.
- **Position Management:** Prevent the "10 identical setup" flood. Implement a max-open-positions cap per timeframe and ensure R:R targets are dynamically staggered.

### Phase 33: Liquidation & CVD Integration (Tier 1 Alpha)
**Priority:** High
- **Liquidation Clusters:** Integrate estimated liquidation levels into the `collectors/derivatives.py` and display as a density strip on the dashboard.
- **Live CVD:** Add Cumulative Volume Delta to the `collectors/flows.py` and display on the Live Tape to catch absorption/exhaustion.

### Phase 34: OI Breakdown & Realized PnL
**Priority:** Medium
- **Exchange OI Table:** Breakdown OI changes by Binance/OKX/Bybit to identify leader/lagger dynamics.
- **PnL Tracking:** Update `tools/paper_trader.py` to track realized PnL separately from unrealized for better copilot exit advice.

### Phase 35: Circuit Breakers & Risk Limits
**Priority:** High (Safety)
- **Daily Loss Limit:** Halt execution after −3R cumulative loss in a session.
- **Drawdown Breaker:** Switch to WATCH-only for 24h if account drops −5% from peak.
- **Correlation Guard:** Block new entries if 2+ open positions share >0.7 correlation.

### Phase 36: Performance Attribution
**Priority:** Medium
- **Probe Effectiveness:** Track which 17+ probes actually predict winners. Auto-adjust weights for probes with <40% hit rate.
- **Probe Leaderboard:** Display best/worst-performing probes on the dashboard.

### Phase 37: Walk-Forward Optimization
**Priority:** Medium
- **Auto-Tune Validation:** Run 30-day rolling backtests before applying `auto_tune.py` deltas to prevent overfitting to local noise.

### Phase 38: Session Journal & Replay
**Priority:** Medium
- **Automated Journaling:** Record entry rationale, active probes, and screenshots for every trade into `logs/journal/`.
- **Strategy Replay:** Enable "Replay" mode on the dashboard to review past setups and exit decisions.

### Phase 39: Push Notifications
**Priority:** Low (UX)
- **Telegram/Discord Bot:** Send A+ alerts with 1-tap deep links back to the dashboard for execution.

### Phase 40: On-Chain Edge
**Priority:** Low
- **Exchange Flows:** Track large BTC inflows/outflows via Blockchain.com API as a macro accumulation/distribution probe.

### Phase 41: TradingView Webhook Ingest
**Priority:** Low
- **Retail Confluence:** Accept TradingView Pine Script alerts as an additional confirmation probe.

### Phase 42: Multi-Asset Expansion
**Priority:** Low (Scaling)
- **ETH/SOL Rollout:** Expand the proven BTC engine to other high-liquidity assets once BTC profitability is stabilized.

---

## Implementation Priority Summary

| Phase | Category | Effort | Impact |
|-------|----------|--------|--------|
| 32 | Fixes | Med | **Critical** |
| 35 | Risk | Low | **High** |
| 33 | Alpha | Med | **High** |
| 34 | Stats | Low | Med |
| 36 | Attribution| Med | Med |
| 37 | Safety | Med | High |

---

_v4.0 | EMBER | Calibration, Tier 1 Alpha, and Risk Hardening_
