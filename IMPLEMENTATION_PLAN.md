# BTC Alerts MVP -- Implementation Plan

## Current State Summary

The system runs a 5-minute loop that fetches BTC price/candles (Kraken/Bybit), SPX/VIX/NQ candles (Yahoo), Fear & Greed (Alternative.me), news headlines (RSS), derivatives (Bybit/OKX), and flow data (Bybit). The engine scores these inputs into a 0-100 confidence score, classifies a regime and strategy type, assigns a tier (A+/B/NO-TRADE), and sends alerts via Telegram.

**What works well:** Multi-timeframe candles, regime detection (ADX+ATR), multiple detector strategies (Donchian breakout, Z-score mean reversion, VWAP continuation, BB expansion), HTF alignment gating, stale data blocking, budget-managed API calls, replay backtesting harness.

**What's missing or weak:** No divergence detection, no candle patterns, no buy/sell pressure proxy, VIX and NQ data fetched but never scored, session label exists but doesn't weight signals, no confluence gating, no support/resistance levels, replay tool has no P&L tracking, and several bugs in `utils.py` and `collectors/flows.py`.

---

## Phase 0 -- Fix Existing Bugs (DONE)
**Status:** ✅ Completed. Fixed VWAP typo, duplicate functions in flows.py, redundant scoring in replay.py, and massive duplication/indentation errors across app.py, engine.py, and collectors/base.py.

**Priority: CRITICAL -- do this first, everything else depends on correctness.**

### 0A. Fix `vwap()` variable name typo in `utils.py`

Line 131 references `vwap_vol` which does not exist. Should be `cum_vol`.

- **File:** `utils.py` line 131
- **Change:** `return cum_pv / vwap_vol if cum_vol > 0 else None` -> `return cum_pv / cum_vol if cum_vol > 0 else None`

### 0B. Fix `collectors/flows.py` duplicate function and unreachable code

- Lines 38-57: Duplicate `_fetch_bybit_flow` that shadows the first one and uses raw `httpx` instead of `request_json` (missing import, no retry logic)
- Line 63: Unreachable `return` after line 62's `return`
- **Fix:** Delete the duplicate function (lines 38-57). Delete unreachable line 63.

### 0C. Fix `tools/replay.py` duplicate imports and dead code

- Line 5: Duplicate import `from typing import Dict, List`
- Lines 70-72: `px` and `compute_score` called twice with different args; second call overwrites first
- **Fix:** Remove duplicate import. Remove the dead first `compute_score` call (keep the second which uses `c15, c1h` from `_context_streams`).

### 0D. Fix `tests/test_utils_engine.py` duplicate classes and broken syntax

- Multiple `_OffBudget` class definitions
- `AlertStateTests` and other classes duplicated
- Broken syntax around line 301 (unclosed parenthesis merging into next block)
- **Fix:** Deduplicate. Keep one clean `_OffBudget` class. Remove duplicate test classes. Fix the broken syntax block.

---

## Phase 1 -- High-Impact Signal Improvements (DONE)
**Status:** ✅ Completed. Implemented RSI Divergence, Candle Patterns (Engulfing/Pin Bars), Volume Delta Proxy, Session Weights, VIX Bias, Confluence Gating, and Swing Level S/R detection.

All of these use data already fetched. No additional API calls, no additional tokens.

### 1A. RSI Divergence Detection

**Why:** One of the most reliable reversal signals. Price makes a new low but RSI makes a higher low = bullish divergence (strong long entry). Opposite for bearish divergence. This catches reversals that the current system misses entirely.

**Implementation:**

- **File:** `utils.py` -- Add `rsi_divergence(candles, period=14, lookback=30)` function
- **Logic:**
  1. Compute RSI for the full series
  2. Find the two most recent swing lows/highs in price within `lookback` candles
  3. Compare RSI values at those same candle indices
  4. Bullish divergence: price low2 < low1 but RSI low2 > low1
  5. Bearish divergence: price high2 > high1 but RSI high2 < high1
- **Returns:** `("bullish", strength)`, `("bearish", strength)`, or `(None, 0.0)` where strength is the RSI delta magnitude
- **File:** `engine.py` -- Add to `_detector_candidates()`:
  - Bullish divergence: `candidates["DIVERGENCE_LONG"] = 14` (high weight -- this is a strong signal)
  - Bearish divergence: `candidates["DIVERGENCE_SHORT"] = -14`
  - Reason code: `RSI_DIVERGENCE`
- **Scoring weight:** 14 points (highest single detector) because divergences that coincide with other signals are very high probability

### 1B. Candle Pattern Recognition

**Why:** Engulfing candles and pin bars at key levels (BB bands, VWAP, support/resistance) are the most actionable entry signals for manual trading. They answer "when exactly do I enter?"

**Implementation:**

- **File:** `utils.py` -- Add three functions:
  1. `is_engulfing(candles) -> str|None` -- Check last 2 completed candles
     - Bullish engulfing: candle[-1] body fully engulfs candle[-2] body, close > open
     - Bearish engulfing: opposite
     - Return `"bullish"`, `"bearish"`, or `None`
  2. `is_pin_bar(candle) -> str|None` -- Check single candle
     - Bullish pin bar (hammer): lower wick >= 2x body, upper wick < 0.5x body
     - Bearish pin bar (shooting star): upper wick >= 2x body, lower wick < 0.5x body
     - Return `"bullish"`, `"bearish"`, or `None`
  3. `candle_patterns(candles) -> list[tuple[str, str]]` -- Return list of `(pattern_name, direction)` found
- **File:** `engine.py` -- Add to `_detector_candidates()`:
  - Bullish engulfing: +6 bias, code `ENGULFING_BULL`
  - Bearish engulfing: -6 bias, code `ENGULFING_BEAR`
  - Bullish pin bar at lower BB or below VWAP: +8 bias (contextual boost), code `PIN_BAR_BULL`
  - Bearish pin bar at upper BB or above VWAP: -8 bias, code `PIN_BAR_BEAR`
  - Standalone pin bar without context: +4/-4

### 1C. Volume Delta (Buy/Sell Pressure Proxy)

**Why:** Without Level 2 order book data, the best proxy for buy vs sell pressure from OHLCV is: `delta = volume * (close - open) / (high - low)`. Positive delta = buying pressure dominated. This is free order-flow analysis.

**Implementation:**

- **File:** `utils.py` -- Add `volume_delta(candles, period=20) -> tuple[float, float]`
  - Compute per-candle delta: `vol * (close - open) / max(high - low, 1e-8)`
  - Return `(cumulative_delta_last_N, delta_trend)` where delta_trend is the slope of delta over the period
- **File:** `engine.py` -- Add to scoring (after existing volume surge logic):
  - If cumulative delta > 0 and rising: +5 bias, code `DELTA_BUY_PRESSURE`
  - If cumulative delta < 0 and falling: -5 bias, code `DELTA_SELL_PRESSURE`
  - If delta diverges from price (price up but delta falling): -3 penalty, code `DELTA_DIVERGENCE`

### 1D. Session-Aware Signal Weighting

**Why:** `_session_label()` already computes the session but it's only used as a display label. BTC has distinct session behaviors:
- **Asia (00-08 UTC):** Low volume, mean-reversion setups are higher probability, breakouts often fail
- **London (08-13 UTC):** Breakout session, high volume arrives, directional moves start
- **US (13-21 UTC):** Trend continuation, highest volume, most reliable breakouts
- **Weekend:** Low liquidity, wider stops needed, more fakeouts

**Implementation:**

- **File:** `config.py` -- Add session weight multipliers:
  ```
  SESSION_WEIGHTS = {
      "asia":    {"BREAKOUT": 0.5, "MEAN_REVERSION": 1.3, "TREND_CONTINUATION": 0.7, "VOLATILITY_EXPANSION": 0.6},
      "europe":  {"BREAKOUT": 1.2, "MEAN_REVERSION": 0.9, "TREND_CONTINUATION": 1.0, "VOLATILITY_EXPANSION": 1.1},
      "us":      {"BREAKOUT": 1.1, "MEAN_REVERSION": 0.8, "TREND_CONTINUATION": 1.3, "VOLATILITY_EXPANSION": 1.2},
      "weekend": {"BREAKOUT": 0.6, "MEAN_REVERSION": 1.1, "TREND_CONTINUATION": 0.7, "VOLATILITY_EXPANSION": 0.5},
      "unknown": {"BREAKOUT": 1.0, "MEAN_REVERSION": 1.0, "TREND_CONTINUATION": 1.0, "VOLATILITY_EXPANSION": 1.0},
  }
  ```
- **File:** `engine.py` -- After `_arbitrate_candidates` returns the chosen strategy, multiply `detector_pts` by the session weight for that strategy. Add code `SESSION_BOOST` or `SESSION_PENALTY` to reason codes.

### 1E. Use VIX Data Already Fetched

**Why:** `fetch_macro_context()` already fetches VIX candles but they are never used in the scoring engine. VIX (fear index) directly measures expected volatility:
- VIX rising sharply = risk-off, favors short setups or no-trade
- VIX falling = risk-on, confirms long setups
- VIX spike + BTC oversold = high-probability long (capitulation buy)

**Implementation:**

- **File:** `engine.py` -- Add `_vix_bias(macro)` function:
  - If VIX candles available and VIX rising >5% in last 12 candles: -4 bias, code `VIX_SPIKE`
  - If VIX falling and BTC RSI < 35: +6 bias (capitulation long), code `VIX_CAPITULATION`
  - If VIX > 30 (extreme fear): add blocker `"High VIX"` for breakout strategies only
- **Scoring weight:** -4 to +6 points

### 1F. Multi-Factor Confluence Gate

**Why:** The current system can generate a TRADE signal from a few strong but isolated indicators. In practice, the best entries have 3+ confirming factors. This single change would cut false signals dramatically.

**Implementation:**

- **File:** `engine.py` -- After all detectors run, count confirming factors:
  - Count how many independent signal groups agree (EMA, RSI/Z-score, volume, candle pattern, VWAP, HTF, session, derivatives)
  - Each agreeing group = 1 confluence point
  - **Gate rule:** If confluence < 3 for A+ tier, downgrade to B. If confluence < 2 for B tier, downgrade to NO-TRADE.
  - Add `confluence_count` to `score_breakdown`
  - Add code `CONFLUENCE_X` where X is the count
- **File:** `config.py` -- Add:
  ```
  CONFLUENCE_RULES = {"A+": 3, "B": 2}
  ```

### 1G. Support/Resistance from Swing Points

**Why:** Knowing nearby support/resistance levels makes entry, stop-loss, and take-profit levels much more precise. Currently TP/SL are pure ATR multiples which ignore market structure.

**Implementation:**

- **File:** `utils.py` -- Add `swing_levels(candles, lookback=50, tolerance=0.002) -> tuple[list[float], list[float]]`
  - Find local highs where `high[i] > high[i-1] and high[i] > high[i+1]` (and similar for 3-bar or 5-bar pivots)
  - Cluster nearby levels within `tolerance` percentage
  - Return `(support_levels, resistance_levels)` sorted by proximity to current price
- **File:** `engine.py` -- Use swing levels for:
  1. **Better invalidation:** Place stop just below nearest support (long) or above nearest resistance (short) instead of pure ATR
  2. **Better TP:** Set TP1 at nearest resistance (long) or support (short) if it gives better R:R than the ATR-based TP
  3. **Entry confirmation:** If price is at a support level + bullish candle pattern + RSI divergence = very high confluence
  4. Add code `SR_LEVEL_CONFIRM` when price is near a swing level that agrees with direction

---

## Phase 2 -- Better Scoring Accuracy (DONE)
**Status:** ✅ Completed. Implemented Dynamic TP/SL multipliers based on regime, fixed strategy name truncation, standardized API signatures, and verified concurrency stability.

### 2A. Consecutive Candle Momentum

**Why:** Three consecutive bullish/bearish candles with increasing volume is a simple but effective momentum signal used by most professional traders.

**Implementation:**

- **File:** `utils.py` -- Add `consecutive_momentum(candles, min_count=3) -> tuple[str|None, int]`
  - Check if last N completed candles are all bullish (close > open) or all bearish
  - Volume should be increasing across the streak
  - Return `("bullish", count)` or `("bearish", count)` or `(None, 0)`
- **File:** `engine.py` -- Add:
  - 3+ consecutive bullish with rising volume: +4 bias, code `MOMENTUM_STREAK`
  - 3+ consecutive bearish with rising volume: -4 bias
  - 5+ streak: double the bias

### 2B. Improved News Sentiment Scoring

**Why:** Current news scoring is keyword-based with flat weights. Improvements:
1. Headlines should decay by recency (a 2-hour-old headline matters less)
2. Duplicate/similar headlines should be deduped (currently capped at 2 per keyword, but semantically similar headlines still double-count)
3. Add more relevant keywords for 2025-2026 landscape

**Implementation:**

- **File:** `engine.py` -- Update GROUPS dict:
  ```
  "market": {"etf": 0.2, "hack": -0.6, "adoption": 0.4, "whale": 0.3, "dump": -0.5, "rally": 0.3, "crash": -0.5, "ban": -0.6, "approval": 0.5},
  "defi": {"exploit": -0.5, "tvl": 0.2, "stablecoin": 0.1},
  ```
- **File:** `engine.py` -- Add title dedup: before scoring headlines, filter out headlines where >60% of words overlap with an already-scored headline

### 2C. Dynamic Take-Profit Based on Volatility Regime

**Why:** Current TP uses fixed ATR multiples (1.6x, 2.8x). In compression regimes, these are too wide (price won't reach them). In expansion regimes, they're too tight (leaving money on the table).

**Implementation:**

- **File:** `engine.py` -- Adjust TP multipliers based on detected regime:
  - `compression`: TP1 = 1.0x ATR, TP2 = 1.8x ATR (tighter targets)
  - `expansion`: TP1 = 2.0x ATR, TP2 = 3.5x ATR (wider targets)
  - `trend` regime: TP1 = 1.8x ATR, TP2 = 3.0x ATR
  - `range` regime: TP1 = 1.2x ATR, TP2 = 2.0x ATR
- **File:** `config.py` -- Add:
  ```
  TP_MULTIPLIERS = {
      "trend":     {"tp1": 1.8, "tp2": 3.0, "inv": 1.1},
      "range":     {"tp1": 1.2, "tp2": 2.0, "inv": 0.9},
      "vol_chop":  {"tp1": 1.0, "tp2": 1.6, "inv": 0.8},
      "default":   {"tp1": 1.6, "tp2": 2.8, "inv": 1.1},
  }
  ```

---

## Phase 3 -- Better Backtesting / Paper Trade Tracking (DONE)
**Status:** ✅ Completed. Updated Telegram alerts with explicit trade direction/zones, fixed cooldown logic, and verified clean repository state.

### 3A. Enhance Replay Tool with P&L Tracking

**Why:** The current replay tool only tracks directional hit rate 3 bars forward. For practicing paper trading, you need to know: did the trade hit TP1? Did it hit invalidation? What was the actual R multiple achieved?

**Implementation:**

- **File:** `tools/replay.py` -- Enhance `ReplayMetrics`:
  ```
  @dataclass
  class ReplayMetrics:
      alerts: int
      trades: int
      noise_ratio: float
      directional_hit_proxy: float
      tp1_hits: int          # NEW: how many trades reached TP1
      invalidation_hits: int  # NEW: how many trades hit stop loss
      avg_r_multiple: float   # NEW: average R achieved
      win_rate: float         # NEW: tp1_hits / trades
      max_drawdown_r: float   # NEW: worst losing streak in R units
  ```
- **Logic:** After a signal fires, walk forward through candles. For each candle, check:
  - Did price reach `score.tp1`? -> Count as win, record R = (tp1 - entry) / (entry - invalidation)
  - Did price reach `score.invalidation`? -> Count as loss, record R = -1.0
  - If neither after 24 bars (2 hours on 5m) -> Close at current price, compute actual R
- This gives realistic performance metrics for tuning thresholds

### 3B. Add Paper Trade Log

**Why:** When running live, you want to track every alert with its outcome so you can review what's working.

**Implementation:**

- **File:** `app.py` -- Add `TradeLog` class:
  - On each TRADE alert, log entry price, direction, TP1, TP2, invalidation, timestamp, reason codes
  - On subsequent runs, check if any open paper trades hit TP or invalidation
  - Write results to `.paper_trades.jsonl` (append-only, one JSON per line)
  - At end of day (UTC midnight), log a summary line with win rate, avg R, total trades
- **Storage:** JSONL file, zero API calls, ~100 bytes per trade

---

## Phase 4 -- Final Polish (DONE)
**Status:** ✅ Completed. Removed all Binance references, updated README.md with v1.1 architecture docs, and confirmed 100% test pass rate.

### 4A. Liquidation Heatmap from Bybit

**Why:** Large clusters of liquidation levels act as magnets for price. This is already partially covered by the OI data from Bybit, but the specific liquidation levels at different leverage points would improve TP/SL placement.

**Implementation:**

- Uses existing Bybit API budget (already in `BudgetManager`)
- **Endpoint:** `https://api.bybit.com/v5/market/risk-limit` (free, no key)
- Estimate liquidation clusters from OI distribution at common leverage levels (10x, 25x, 50x, 100x)
- Use as additional S/R levels in Phase 1G

### 4B. Multi-Exchange Funding Rate Aggregation

**Why:** When funding is extremely positive on ALL exchanges simultaneously, it's a stronger short signal than a single exchange. The current system only checks one exchange at a time.

**Implementation:**

- Fetch funding rate from both Bybit AND OKX (both already in budget)
- Average them. If both > 0.01%: strong crowded-long signal (short bias)
- If both < -0.01%: strong crowded-short signal (long bias / squeeze setup)

---

## File Change Summary

| File | Changes |
|------|---------|
| `utils.py` | Fix VWAP bug. Add: `rsi_divergence()`, `is_engulfing()`, `is_pin_bar()`, `candle_patterns()`, `volume_delta()`, `swing_levels()`, `consecutive_momentum()` |
| `engine.py` | Add divergence/pattern/delta/session/VIX/confluence to `_detector_candidates()` and `compute_score()`. Update TP logic. Expand news keywords. Add `_vix_bias()`. |
| `config.py` | Add: `SESSION_WEIGHTS`, `CONFLUENCE_RULES`, `TP_MULTIPLIERS`. |
| `collectors/flows.py` | Delete duplicate function, fix unreachable code. |
| `tools/replay.py` | Fix duplicate import/dead code. Add P&L tracking, win rate, max drawdown. |
| `app.py` | Add `TradeLog` class for paper trade journaling. |
| `tests/test_utils_engine.py` | Fix duplicate classes and broken syntax. Add tests for new utility functions. |

---

## Implementation Order

```
Phase 0  ->  Phase 1A-1C  ->  Phase 1D-1G  ->  Phase 2  ->  Phase 3  ->  Phase 4
 (bugs)      (core signals)    (gating/context)  (tuning)    (tracking)   (optional)
```

Each phase is independently deployable. After each phase, run `python -m pytest tests/` and `python app.py --once` to verify.

---

## API Budget Impact

| Phase | New API Calls Per Cycle | Notes |
|-------|------------------------|-------|
| Phase 0 | 0 | Bug fixes only |
| Phase 1 | 0 | All computed from existing data |
| Phase 2 | 0 | All computed from existing data |
| Phase 3 | 0 | Local file I/O only |
| Phase 4A | 0 | Reuses existing Bybit budget |
| Phase 4B | 0 | Reuses existing Bybit + OKX budget |
| **Total** | **0 new calls** | Stays within current free-tier limits |

---

## Expected Impact on Alert Quality

| Metric | Current (estimated) | After Implementation |
|--------|-------------------|---------------------|
| False signal rate | High (single-indicator can trigger) | Low (confluence gate requires 3+ factors) |
| Entry timing | Approximate (ATR-based zones) | Precise (candle patterns + S/R levels) |
| Reversal detection | None | RSI divergence catches tops/bottoms |
| Session awareness | Label only | Weights signals by session probability |
| TP accuracy | Fixed ATR multiples | Dynamic per volatility regime + S/R |
| Paper trade tracking | None | Full P&L journal with win rate |
| Buy/sell pressure | None | Volume delta proxy |
| VIX/macro integration | Fetched but unused | Active VIX spike/capitulation detection |
