# ACTION PLAN v2.1 — The Intelligence Upgrade

> **Codename: EMBER INTELLIGENCE**
> **Previous Version:** v2.0 (Self-Validating Trading Loop — COMPLETE ✅)
> **Target:** v2.1 — Advanced Decision Intelligence Layer
> **Author:** EMBER System / PID-129
> **Created:** 2026-02-17
> **Estimated Total Time:** 18–25 hours across 8 phases.
> **Recommended Pace:** 1 phase per session (2–3 hour sessions).

---

## Executive Summary

v2.0 gave us a **self-validating loop**: alerts fire, outcomes are tracked, a virtual portfolio runs, and results are displayed on a dashboard.

v2.1 is the **intelligence upgrade**. The goal is to give the trader (or the team) every possible edge *before* they act on a signal. We are adding **six new intelligence layers** and two infrastructure improvements — all using **free APIs** and **local computation**. Zero new paid services.

### What v2.1 Delivers

| Layer | What It Does | API Cost |
|:------|:-------------|:---------|
| Squeeze Detector | Identifies volatility compression → imminent explosive moves | **$0** (local math) |
| Volume Profile / POC | Shows where "fair value" is, so you know if entry is cheap or expensive | **$0** (local math) |
| Liquidity Walls | Reveals hidden buy/sell walls that can trap your position | **$0** (Kraken/Bybit free REST) |
| Macro Correlation Pulse | Warns when DXY/Gold are fighting your BTC trade | **$0** (Yahoo Finance) |
| AI Sentiment Engine | Turns 50 news headlines into one actionable sentiment score | **$0** (VADER, local CPU) |
| Multi-Timeframe Confluence Heatmap | Visual grid showing alignment across all timeframes | **$0** (local math) |
| Team Voting Gate | Lets your global team vote on signals before execution | **$0** (Telegram API) |
| Smart Alert Enrichment | Adds all intelligence to every alert message | **$0** |

---

## Current Architecture (v2.0 Baseline)

```
┌──────────────────────────────────────────────────┐
│                  DATA LAYER                       │
│  Kraken ─┐                                       │
│  Bybit  ─┼─→ collectors/price.py ──→ Candles     │
│  Yahoo  ─┘   collectors/derivatives.py            │
│              collectors/flows.py                  │
│              collectors/news.py                   │
│              collectors/fear_greed.py              │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│                ENGINE LAYER                       │
│  engine.py                                        │
│  ├── _regime()         → TREND / RANGE / CHOP    │
│  ├── _detector_candidates() → Pattern detection   │
│  ├── _arbitrate_candidates() → Filter + score     │
│  ├── _session_label()  → Asia/Europe/US           │
│  ├── _trend_bias()     → HTF alignment            │
│  └── compute_score()   → Final AlertScore         │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│               ACTION LAYER                        │
│  app.py                                           │
│  ├── PersistentLogger  → logs/pid-129-alerts.jsonl│
│  ├── Notifier          → Telegram alerts          │
│  ├── Portfolio         → Paper trading            │
│  ├── resolve_outcomes  → Win/Loss/Timeout         │
│  └── generate_dashboard → dashboard.html          │
└──────────────────────────────────────────────────┘
```

### v2.1 Target Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     DATA LAYER (EXPANDED)                     │
│  Kraken  ─┐                                                   │
│  Bybit   ─┼─→ collectors/price.py ──→ Candles                │
│  Yahoo   ─┘                                                   │
│  [NEW] collectors/orderbook.py  ──→ Liquidity Walls           │
│  [NEW] collectors/macro.py      ──→ DXY + Gold Correlation    │
│  collectors/news.py + [NEW] tools/sentiment.py → AI Score     │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│                  ENGINE LAYER (EXPANDED)                       │
│  engine.py                                                     │
│  ├── [EXISTING] _regime(), _detector_candidates(), etc.       │
│  ├── [NEW] _squeeze_detector()    → BB/KC compression         │
│  ├── [NEW] _volume_profile_poc()  → Fair value zone           │
│  ├── [NEW] _liquidity_context()   → Wall proximity warning    │
│  ├── [NEW] _macro_correlation()   → DXY/Gold alignment        │
│  ├── [NEW] _sentiment_score()     → Headline AI analysis      │
│  └── [UPDATED] compute_score()    → Enriched AlertScore       │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│               ACTION LAYER (ENHANCED)                         │
│  app.py                                                        │
│  ├── [UPDATED] _format_alert()  → Shows all intelligence      │
│  ├── [NEW] Team voting gate     → Telegram inline buttons     │
│  ├── [UPDATED] Dashboard        → Confluence heatmap          │
│  └── [EXISTING] Portfolio, Outcomes, Logging                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Phase 1: The Squeeze Detector — Volatility Compression

**Priority:** 🔴 HIGH — This is the single highest-value addition. Signals during a "squeeze" have 2–3x higher R:R.
**Estimated Time:** 2–3 hours
**Files:** `engine.py`, `config.py`
**Depends on:** Nothing (uses existing candle data)
**API Cost:** $0 (pure local math)

### Background

The "TTM Squeeze" concept (developed by John Carter) identifies when Bollinger Bands contract *inside* Keltner Channels. This compression signals that a large move is about to happen—like a coiled spring. When the squeeze "fires," price tends to move explosively.

- **Squeeze ON** = Bollinger Bands are inside Keltner Channels (low volatility, coiling).
- **Squeeze FIRE** = Bollinger Bands just expanded outside Keltner Channels (the move starts).
- **No Squeeze** = Normal volatility, no special context.

### Tasks

#### 1.1 — Implement Bollinger Band Calculator
- [ ] In `engine.py`, add helper `_bollinger_bands(closes, period=20, std_mult=2.0)`.
- [ ] Returns `(upper, middle, lower)` for the latest candle.
- [ ] Uses the closes we already have from `candles[:-1]`.

#### 1.2 — Implement Keltner Channel Calculator
- [ ] In `engine.py`, add helper `_keltner_channels(candles, period=20, atr_mult=1.5)`.
- [ ] Requires ATR calculation (already partially available in `_calculate_raw_regime`).
- [ ] Returns `(upper, middle, lower)` for the latest candle.

#### 1.3 — Implement Squeeze Detector
- [ ] In `engine.py`, add `_squeeze_detector(candles)`.
- [ ] Logic:
  ```python
  bb_upper, bb_mid, bb_lower = _bollinger_bands(closes)
  kc_upper, kc_mid, kc_lower = _keltner_channels(candles)
  
  squeeze_on = bb_lower > kc_lower and bb_upper < kc_upper
  # Check previous state for "FIRE" detection
  prev_bb = _bollinger_bands(closes[:-1])
  prev_kc = _keltner_channels(candles[:-2])
  was_squeeze = prev_bb[2] > prev_kc[2] and prev_bb[0] < prev_kc[0]
  squeeze_fire = was_squeeze and not squeeze_on
  ```
- [ ] Returns: `("SQUEEZE_ON", 0)`, `("SQUEEZE_FIRE", +8)`, or `("NONE", 0)`.

#### 1.4 — Integrate into `compute_score()`
- [ ] Call `_squeeze_detector(candles)` inside `compute_score()`.
- [ ] Add result to `breakdown["volatility"]`.
- [ ] Add to `codes`: `"SQUEEZE_ON"` or `"SQUEEZE_FIRE"`.
- [ ] Add to `AlertScore.context`: `"squeeze": "ON"` / `"FIRE"` / `"NONE"`.

#### 1.5 — Add Config Tunables
- [ ] Add to `config.py` under a new `SQUEEZE` dict:
  ```python
  SQUEEZE = {
      "bb_period": 20,
      "bb_std": 2.0,
      "kc_period": 20,
      "kc_atr_mult": 1.5,
      "fire_bonus_pts": 8,  # Points added when squeeze fires
  }
  ```

#### 1.6 — Add Tests
- [ ] In `tests/test_squeeze.py`, create test cases:
  - Test with synthetic candles where BB is inside KC (squeeze ON).
  - Test with synthetic candles where squeeze just released (FIRE).
  - Test with normal volatility (NONE).
  - Test edge case: fewer than 20 candles (should degrade gracefully).

### Success Criteria
- [ ] `SQUEEZE_FIRE` code appears in alerts when volatility compression releases.
- [ ] `SQUEEZE_ON` code appears when market is coiling.
- [ ] No new API calls are made.
- [ ] Test: `PYTHONPATH=. python3 -m pytest tests/test_squeeze.py`

### Verification
```bash
# Unit tests
PYTHONPATH=. python3 -m pytest tests/test_squeeze.py -v

# Manual: Run one cycle and check alert payload for "squeeze" field
PYTHONPATH=. python3 app.py --once 2>&1 | grep -i squeeze
```

### Evidence
_(To be filled after completion)_

---

## Phase 2: Volume Profile & Point of Control (POC)

**Priority:** 🔴 HIGH — Knowing if you're buying at "fair value" or "expensive" is critical.
**Estimated Time:** 2–3 hours
**Files:** `engine.py`, `config.py`
**Depends on:** Nothing (uses existing candle data)
**API Cost:** $0 (pure local math)

### Background

The Volume Profile shows how much volume traded at each price level over a given period. The **Point of Control (POC)** is the price level with the highest traded volume — it acts as a magnet for price. The **Value Area** covers 70% of all volume and represents "fair value."

- **Entry below POC** = Buying cheap (good for longs).
- **Entry above POC** = Buying expensive (risky for longs, good for shorts).
- **Entry inside Value Area** = Neutral, at "fair value."

### Tasks

#### 2.1 — Implement Volume Profile Calculator
- [ ] In `engine.py`, add `_volume_profile(candles, num_bins=50)`.
- [ ] Algorithm:
  ```python
  # 1. Find price range across all candles
  all_highs = [c.high for c in candles]
  all_lows = [c.low for c in candles]
  price_min, price_max = min(all_lows), max(all_highs)
  
  # 2. Create bins
  bin_size = (price_max - price_min) / num_bins
  bins = [0.0] * num_bins
  
  # 3. Distribute volume across bins
  for c in candles:
      low_bin = int((c.low - price_min) / bin_size)
      high_bin = int((c.high - price_min) / bin_size)
      spread = max(high_bin - low_bin, 1)
      for b in range(low_bin, min(high_bin + 1, num_bins)):
          bins[b] += c.volume / spread
  
  # 4. Find POC (bin with max volume)
  poc_bin = bins.index(max(bins))
  poc_price = price_min + (poc_bin + 0.5) * bin_size
  ```
- [ ] Returns: `(poc_price, value_area_high, value_area_low)`.

#### 2.2 — Implement Value Area Calculation
- [ ] The Value Area = the range of prices containing 70% of the total volume.
- [ ] Algorithm: Start at POC bin, expand outward (up and down), adding the bin with more volume until 70% of total volume is captured.
- [ ] Returns `value_area_high` and `value_area_low` prices.

#### 2.3 — Integrate POC Context into `compute_score()`
- [ ] Call `_volume_profile(candles)` inside `compute_score()`.
- [ ] Determine entry position relative to POC:
  ```python
  current_price = price.price
  if current_price < value_area_low:
      poc_context = "BELOW_VALUE"  # Good for LONG
      breakdown["volume"] += 3.0
  elif current_price > value_area_high:
      poc_context = "ABOVE_VALUE"  # Good for SHORT
      breakdown["volume"] -= 3.0
  else:
      poc_context = "AT_VALUE"     # Neutral
  ```
- [ ] Add to `AlertScore.context`: `"poc": 67500.00, "value_area": "BELOW_VALUE"`.
- [ ] Add to `codes`: `"POC_BELOW_VALUE"`, `"POC_ABOVE_VALUE"`, or `"POC_AT_VALUE"`.

#### 2.4 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  VOLUME_PROFILE = {
      "num_bins": 50,
      "value_area_pct": 0.70,  # 70% of volume
      "poc_bonus_pts": 3,      # Points when entry is at favorable side of POC
  }
  ```

#### 2.5 — Add Tests
- [ ] In `tests/test_volume_profile.py`:
  - Test POC calculation with uniform volume (POC should be at midpoint).
  - Test value area with concentrated volume (VA should be tight).
  - Test with real-ish candle data.
  - Test edge case: single candle (should degrade gracefully).

### Success Criteria
- [ ] `POC_BELOW_VALUE` or `POC_ABOVE_VALUE` appears in alerts when entry is at an extreme.
- [ ] POC price is visible in the alert payload `context` field.
- [ ] No new API calls are made.
- [ ] Test: `PYTHONPATH=. python3 -m pytest tests/test_volume_profile.py`

### Verification
```bash
# Unit tests
PYTHONPATH=. python3 -m pytest tests/test_volume_profile.py -v

# Manual: Run one cycle and check for poc field
PYTHONPATH=. python3 app.py --once 2>&1 | grep -i poc
```

### Evidence
_(To be filled after completion)_

---

## Phase 3: Liquidity Walls — Order Book Intelligence

**Priority:** 🟡 MEDIUM — Prevents you from trading into a wall.
**Estimated Time:** 2–3 hours
**Files:** `collectors/orderbook.py` [NEW], `engine.py`, `config.py`
**Depends on:** Nothing
**API Cost:** $0 (Kraken/Bybit free REST API — ~288 calls/day at 5 min intervals, well within limits)

### Background

Large buy/sell orders ("walls") on the order book can block price movement. If you go LONG and there's a $20M sell wall just $100 above your entry, your trade is likely to fail. Conversely, a massive buy wall below your entry acts as a floor.

### Free API Strategy

| Exchange | Endpoint | Rate Limit | Our Usage |
|:---------|:---------|:-----------|:----------|
| Kraken | `/0/public/Depth?pair=XXBTZUSD&count=100` | ~15 req/min | 1 req/5 min |
| Bybit (fallback) | `/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=50` | 120 req/min | 1 req/5 min |

### Tasks

#### 3.1 — Create `collectors/orderbook.py`
- [ ] Create new file `collectors/orderbook.py`.
- [ ] Implement `OrderBookSnapshot` dataclass:
  ```python
  @dataclass
  class OrderBookSnapshot:
      bid_walls: List[Tuple[float, float]]  # [(price, size_usd), ...]
      ask_walls: List[Tuple[float, float]]  # [(price, size_usd), ...]
      bid_total_usd: float
      ask_total_usd: float
      imbalance: float  # (bid_total - ask_total) / (bid_total + ask_total)
      nearest_bid_wall: Optional[Tuple[float, float]]  # Closest large bid to current price
      nearest_ask_wall: Optional[Tuple[float, float]]  # Closest large ask to current price
      source: str
      healthy: bool = True
  ```

#### 3.2 — Implement Kraken Order Book Fetcher
- [ ] Function `fetch_orderbook(budget)`:
  - Fetch top 100 levels from Kraken (`/0/public/Depth`).
  - Identify "walls" = any single level with > 2x the average level size.
  - Fallback to Bybit if Kraken fails.
- [ ] Calculate `imbalance` ratio: positive = more bids (bullish), negative = more asks (bearish).

#### 3.3 — Implement Wall Detection Logic
- [ ] Function `_detect_walls(levels, current_price, threshold_multiplier=2.0)`:
  - Iterate through order levels.
  - Flag any level where `size > avg_size * threshold_multiplier` as a "wall."
  - Return walls sorted by proximity to current price.
  - Calculate `wall_proximity_pct` = how close the nearest wall is as a % of current price.

#### 3.4 — Integrate into Engine
- [ ] In `engine.py`, add `_liquidity_context(orderbook: OrderBookSnapshot, direction: str, price: float)`:
  ```python
  # If going LONG and there's a massive ask wall within 0.5% of entry → BLOCKER
  # If going SHORT and there's a massive bid wall within 0.5% of entry → BLOCKER
  # If imbalance strongly supports direction → +3 pts
  # If imbalance opposes direction → -3 pts
  ```
- [ ] Add to `AlertScore.context`: `"liquidity": {"imbalance": 0.35, "nearest_wall": "$68,500 (sell)", "wall_distance_pct": 0.3}`.
- [ ] Add to `codes`: `"LIQ_WALL_BLOCKER"`, `"LIQ_IMBALANCE_BULL"`, `"LIQ_IMBALANCE_BEAR"`.

#### 3.5 — Update `app.py` Data Collection
- [ ] In the `run()` function, call `fetch_orderbook(bm)` alongside existing data fetches.
- [ ] Pass the `OrderBookSnapshot` to `compute_score()`.

#### 3.6 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  LIQUIDITY = {
      "wall_threshold_mult": 2.0,   # Level must be 2x avg to be a "wall"
      "wall_danger_pct": 0.005,     # Wall within 0.5% of entry is dangerous
      "imbalance_threshold": 0.3,   # Imbalance > 30% is significant
      "imbalance_pts": 3,           # Points for order book alignment
  }
  ```

#### 3.7 — Add Tests
- [ ] In `tests/test_orderbook.py`:
  - Test wall detection with synthetic order book data.
  - Test imbalance calculation (balanced, bullish, bearish).
  - Test blocker logic when wall is within danger zone.
  - Test graceful degradation when order book is unavailable.

### Success Criteria
- [ ] `LIQ_WALL_BLOCKER` appears when a massive wall is in the path of the trade.
- [ ] `LIQ_IMBALANCE_BULL` / `BEAR` appears in alerts based on order book bias.
- [ ] API calls stay within free limits (verified via BudgetManager logs).
- [ ] Test: `PYTHONPATH=. python3 -m pytest tests/test_orderbook.py`

### Verification
```bash
# Unit tests
PYTHONPATH=. python3 -m pytest tests/test_orderbook.py -v

# Integration: Verify API call count stays low
PYTHONPATH=. python3 app.py --once 2>&1 | grep -i orderbook

# Check BudgetManager to confirm API usage
grep "kraken" logs/*.jsonl | wc -l  # Should be minimal
```

### Evidence
_(To be filled after completion)_

---

## Phase 4: Macro Correlation Pulse — DXY & Gold

**Priority:** 🟡 MEDIUM — BTC doesn't move in isolation.
**Estimated Time:** 2 hours
**Files:** `collectors/price.py` (expand), `engine.py`, `config.py`
**Depends on:** Nothing
**API Cost:** $0 (Yahoo Finance, already used for SPX)

### Background

BTC has strong inverse correlation with the US Dollar Index (DXY) and moderate positive correlation with Gold. When DXY surges, BTC often drops. When Gold rallies alongside BTC, the move has "real" macro support.

- **DXY UP + BTC LONG signal → WARNING** (headwind)
- **DXY DOWN + BTC LONG signal → CONFIRMATION** (tailwind)
- **Gold UP + BTC LONG signal → CONFIRMATION** (risk-on environment)

### Free API Strategy

| Asset | Yahoo Symbol | Interval | Usage |
|:------|:------------|:---------|:------|
| DXY (Dollar Index) | `DX-Y.NYB` | `5m` | 1 call/5 min |
| Gold Futures | `GC=F` | `5m` | 1 call/5 min |

### Tasks

#### 4.1 — Expand `collectors/price.py` with DXY & Gold Fetchers
- [ ] Add function `fetch_dxy_candles(budget, limit=30)`:
  - Uses existing `_fetch_yahoo_symbol_candles(budget, "DX-Y.NYB", "5m", "1d", limit)`.
- [ ] Add function `fetch_gold_candles(budget, limit=30)`:
  - Uses existing `_fetch_yahoo_symbol_candles(budget, "GC=F", "5m", "1d", limit)`.
- [ ] Add a combined function `fetch_macro_correlation_data(budget)` that fetches both in one call.

#### 4.2 — Implement Correlation Calculator in `engine.py`
- [ ] Add `_macro_correlation(dxy_candles, gold_candles, btc_candles)`:
  ```python
  # Calculate 20-period rate of change for each asset
  def _roc(candles, period=20):
      if len(candles) < period + 1: return 0.0
      return (candles[-1].close - candles[-period].close) / candles[-period].close
  
  dxy_roc = _roc(dxy_candles)
  gold_roc = _roc(gold_candles)
  btc_roc = _roc(btc_candles)
  
  # DXY rising + BTC long signal → headwind
  # DXY falling + BTC long signal → tailwind
  # Gold rising + BTC rising → macro confirmation
  ```
- [ ] Returns: `{"dxy_bias": "HEADWIND"/"TAILWIND"/"NEUTRAL", "gold_confirm": True/False, "pts": +/-3}`.

#### 4.3 — Integrate into `compute_score()`
- [ ] Call `_macro_correlation()` inside `compute_score()`.
- [ ] Add points to `breakdown["htf"]` based on macro alignment.
- [ ] Add to `codes`: `"MACRO_HEADWIND"`, `"MACRO_TAILWIND"`, `"GOLD_CONFIRM"`.
- [ ] Add to `AlertScore.context`: `"macro": {"dxy": "HEADWIND", "gold": "CONFIRM"}`.

#### 4.4 — Update `app.py` Data Collection
- [ ] In `run()`, call `fetch_macro_correlation_data(bm)`.
- [ ] Pass DXY and Gold candles to `compute_score()`.

#### 4.5 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  MACRO_CORRELATION = {
      "roc_period": 20,           # Rate of change lookback
      "dxy_threshold": 0.002,     # 0.2% move is significant
      "gold_threshold": 0.003,    # 0.3% move is significant
      "headwind_penalty": -3,     # Points when DXY opposes trade
      "tailwind_bonus": 3,        # Points when DXY supports trade
      "gold_confirm_bonus": 2,    # Points when Gold confirms
  }
  ```

#### 4.6 — Add Tests
- [ ] In `tests/test_macro_correlation.py`:
  - Test DXY headwind scenario (DXY up, BTC long → negative signal).
  - Test DXY tailwind scenario (DXY down, BTC long → positive signal).
  - Test Gold confirmation (Gold up + BTC up → bonus).
  - Test graceful degradation when DXY/Gold data is unavailable.

### Success Criteria
- [ ] `MACRO_HEADWIND` or `MACRO_TAILWIND` appears in alerts.
- [ ] DXY/Gold context is visible in the alert payload.
- [ ] Yahoo Finance usage stays within free limits (verified via BudgetManager).
- [ ] Test: `PYTHONPATH=. python3 -m pytest tests/test_macro_correlation.py`

### Verification
```bash
# Unit tests
PYTHONPATH=. python3 -m pytest tests/test_macro_correlation.py -v

# Manual: Check alert payload for macro field
PYTHONPATH=. python3 app.py --once 2>&1 | grep -i macro
```

### Evidence
_(To be filled after completion)_

---

## Phase 5: AI Sentiment Engine — Local NLP

**Priority:** 🟡 MEDIUM — Turns noisy headlines into one actionable number.
**Estimated Time:** 2–3 hours
**Files:** `tools/sentiment.py` [NEW], `engine.py`, `requirements.txt`
**Depends on:** Nothing
**API Cost:** $0 (VADER runs on local CPU, no network calls)

### Background

We already collect news headlines via `collectors/news.py`. Currently, they're keyword-matched (basic). With VADER (Valence Aware Dictionary and sEntiment Reasoner), we can score each headline from -1 (extremely bearish) to +1 (extremely bullish), then aggregate into a single composite score.

### Why VADER over LLMs?

| Feature | VADER | OpenAI API | Local LLM |
|:--------|:------|:-----------|:----------|
| Cost | Free | $0.01/call | Free but slow |
| Speed | <1ms per headline | 500ms per call | 2-5s per call |
| Privacy | 100% local | Headlines sent to cloud | 100% local |
| Accuracy | Good for financial text | Excellent | Good |
| Dependencies | 1 pip package | API key | 4GB+ model |

### Tasks

#### 5.1 — Install VADER
- [ ] Add `vaderSentiment` to `requirements.txt`.
- [ ] Install: `python3 -m pip install vaderSentiment`.

#### 5.2 — Create `tools/sentiment.py`
- [ ] Implement `SentimentEngine` class:
  ```python
  from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
  
  class SentimentEngine:
      def __init__(self):
          self.analyzer = SentimentIntensityAnalyzer()
          # Extend VADER's lexicon with crypto-specific terms
          self.analyzer.lexicon.update({
              "bullish": 2.0, "bearish": -2.0,
              "dump": -2.5, "pump": 2.0,
              "crash": -3.0, "moon": 2.5,
              "hack": -3.0, "exploit": -2.5,
              "whale": 0.5, "liquidation": -1.5,
              "etf": 1.5, "approval": 2.0,
              "ban": -2.5, "regulation": -1.0,
              "adoption": 2.0, "institutional": 1.5,
              "accumulation": 1.5, "distribution": -1.5,
              "breakout": 1.5, "breakdown": -1.5,
              "support": 0.8, "resistance": -0.3,
              "fud": -1.5, "fomo": 1.0,
          })
      
      def score_headline(self, text: str) -> float:
          """Returns compound score from -1.0 to +1.0."""
          return self.analyzer.polarity_scores(text)["compound"]
      
      def score_batch(self, headlines: List[str]) -> dict:
          """Score multiple headlines and return aggregate stats."""
          scores = [self.score_headline(h) for h in headlines]
          if not scores:
              return {"composite": 0.0, "bullish_pct": 0, "bearish_pct": 0, "count": 0}
          
          bullish = sum(1 for s in scores if s > 0.05)
          bearish = sum(1 for s in scores if s < -0.05)
          
          return {
              "composite": sum(scores) / len(scores),
              "bullish_pct": round(bullish / len(scores) * 100),
              "bearish_pct": round(bearish / len(scores) * 100),
              "strongest_bull": max(scores),
              "strongest_bear": min(scores),
              "count": len(scores),
          }
  ```

#### 5.3 — Integrate into `engine.py`
- [ ] Import `SentimentEngine` in `engine.py`.
- [ ] In `compute_score()`, call `SentimentEngine.score_batch()` on the news headlines.
- [ ] Add points to `breakdown["momentum"]`:
  ```python
  if sentiment["composite"] > 0.3:       # Strongly bullish
      breakdown["momentum"] += 4.0
      codes.append("SENTIMENT_BULL")
  elif sentiment["composite"] < -0.3:    # Strongly bearish
      breakdown["momentum"] -= 4.0
      codes.append("SENTIMENT_BEAR")
  elif abs(sentiment["composite"]) < 0.05:
      codes.append("SENTIMENT_NEUTRAL")
  ```
- [ ] Add to `AlertScore.context`: `"sentiment": {"score": 0.42, "bull_pct": 70, "bear_pct": 15}`.

#### 5.4 — Replace Existing Keyword Sentiment
- [ ] The current `NEWS_DICT` in `engine.py` uses hardcoded keyword weights.
- [ ] Keep `NEWS_DICT` as a fallback but prefer VADER scores when available.
- [ ] If VADER import fails (missing package), gracefully fall back to keyword matching.

#### 5.5 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  SENTIMENT = {
      "strong_threshold": 0.3,    # Composite > 0.3 is "strongly bullish"
      "weak_threshold": 0.05,     # Below 0.05 is "neutral"
      "bull_pts": 4,              # Points for strong bullish sentiment
      "bear_pts": -4,             # Points for strong bearish sentiment
      "max_headlines": 50,        # Max headlines to score per cycle
  }
  ```

#### 5.6 — Add Tests
- [ ] In `tests/test_sentiment.py`:
  - Test known bullish headline → positive score.
  - Test known bearish headline → negative score.
  - Test crypto-specific terms ("BTC ETF approved" → strongly positive).
  - Test aggregate: mixed headlines → near-neutral composite.
  - Test empty headline list → graceful default.

### Success Criteria
- [ ] `SENTIMENT_BULL` / `SENTIMENT_BEAR` appears in alerts based on news tone.
- [ ] Composite sentiment score is visible in alert payload.
- [ ] No external API calls are made for sentiment.
- [ ] Falls back to `NEWS_DICT` if VADER is not installed.
- [ ] Test: `PYTHONPATH=. python3 -m pytest tests/test_sentiment.py`

### Verification
```bash
# Install dependency
python3 -m pip install vaderSentiment

# Unit tests
PYTHONPATH=. python3 -m pytest tests/test_sentiment.py -v

# Quick smoke test
python3 -c "from tools.sentiment import SentimentEngine; e = SentimentEngine(); print(e.score_headline('Bitcoin ETF approved, massive institutional inflow expected'))"
# Expected: > 0.5
```

### Evidence
_(To be filled after completion)_

---

## Phase 6: Multi-Timeframe Confluence Heatmap

**Priority:** 🟡 MEDIUM — The "at a glance" decision tool.
**Estimated Time:** 2–3 hours
**Files:** `engine.py`, `scripts/pid-129/generate_dashboard.py`, `app.py`
**Depends on:** Phases 1–5 (uses all intelligence signals)
**API Cost:** $0 (visualization only)

### Background

Instead of reading through a wall of reason codes, the team should see a **visual grid** that shows alignment across all timeframes and all intelligence layers at a glance. Green = aligned, Red = conflicting, Yellow = neutral.

```
           │  5m   │  15m  │  1h   │
───────────┼───────┼───────┼───────┤
 Trend     │  🟢   │  🟢   │  🟡   │
 Momentum  │  🟢   │  🟡   │  🔴   │
 Squeeze   │  🔥   │  ⚪   │  ⚪   │
 Volume    │  🟢   │  🟢   │  🟢   │
 Sentiment │  🟢   │  🟢   │  🟢   │
 Liquidity │  🟡   │  🟡   │  🟡   │
 Macro     │  🔴   │  🔴   │  🔴   │
```

### Tasks

#### 6.1 — Create Heatmap Data Structure
- [ ] In `engine.py`, create a `ConfluenceGrid` dataclass:
  ```python
  @dataclass
  class ConfluenceCell:
      signal: str      # "BULL", "BEAR", "NEUTRAL", "SQUEEZE_FIRE"
      strength: float  # -1.0 to +1.0
  
  @dataclass
  class ConfluenceGrid:
      rows: Dict[str, Dict[str, ConfluenceCell]]  # {layer: {timeframe: cell}}
  ```

#### 6.2 — Populate Heatmap from AlertScore
- [ ] After `compute_score()` runs for each timeframe, collect the `breakdown` values.
- [ ] Normalize each breakdown dimension to -1.0 → +1.0 range.
- [ ] Store in a `ConfluenceGrid` that accumulates across timeframes.

#### 6.3 — Add Consensus Score
- [ ] A simple "consensus" metric: count the number of green cells divided by total cells.
- [ ] `consensus_pct = green_cells / total_cells * 100`.
- [ ] Include in alert: `"confluence_consensus": 78` (78% of signals agree).

#### 6.4 — Render Heatmap in Dashboard
- [ ] In `generate_dashboard.py`, add an HTML table rendering the heatmap grid.
- [ ] Use color-coded cells (CSS backgrounds):
  - Green (`#00ffcc`) for bullish alignment.
  - Red (`#ff4d4d`) for bearish/conflicting.
  - Yellow (`#ffd700`) for neutral.
  - Fire emoji (`🔥`) for squeeze fire events.

#### 6.5 — Include Heatmap Summary in Telegram Alerts
- [ ] In `_format_alert()`, add a text-based heatmap summary below the payload:
  ```
  📊 Confluence: 78% aligned
  Trend: 🟢🟢🟡 | Mom: 🟢🟡🔴 | Vol: 🟢🟢🟢
  ```
- [ ] Keep it compact (one line) to avoid Telegram clutter.

#### 6.6 — Add Tests
- [ ] In `tests/test_confluence.py`:
  - Test grid population with 3 timeframes.
  - Test consensus calculation (all green = 100%, all red = 0%).
  - Test HTML rendering produces valid output.

### Success Criteria
- [ ] Dashboard shows a visual confluence heatmap grid.
- [ ] Telegram alerts include a one-line confluence summary.
- [ ] Consensus percentage is accurate.
- [ ] Test: `PYTHONPATH=. python3 -m pytest tests/test_confluence.py`

### Verification
```bash
# Unit tests
PYTHONPATH=. python3 -m pytest tests/test_confluence.py -v

# Generate dashboard and open in browser
python3 scripts/pid-129/generate_dashboard.py
open dashboard.html
# Visual check: heatmap grid should be visible
```

### Evidence
_(To be filled after completion)_

---

## Phase 7: Team Voting Gate — Telegram Interaction

**Priority:** 🟢 LOW — Social layer for distributed team decision-making.
**Estimated Time:** 2–3 hours
**Files:** `tools/notifier.py` (or `collectors/notifier.py`), `app.py`, `config.py`
**Depends on:** Phases 1–6 (sends enriched alerts that people vote on)
**API Cost:** $0 (Telegram Bot API, unlimited for small teams)

### Background

When the system fires a `TRADE` alert, instead of just notifying, it posts a **"PROPOSAL"** with inline vote buttons. Team members can vote ✅ (agree) or ❌ (disagree). If enough votes are received within a window, the paper trader can automatically act on it — or the alert is flagged as "team-rejected."

### Tasks

#### 7.1 — Add Telegram Inline Keyboard Support
- [ ] Modify the Notifier's `send()` method to support Telegram Inline Keyboards.
- [ ] For `TRADE`-tier alerts, send with `reply_markup`:
  ```python
  reply_markup = {
      "inline_keyboard": [[
          {"text": "✅ Take Trade", "callback_data": f"vote_yes_{alert_id}"},
          {"text": "❌ Skip", "callback_data": f"vote_no_{alert_id}"},
          {"text": "🔍 More Info", "callback_data": f"info_{alert_id}"},
      ]]
  }
  ```

#### 7.2 — Create Webhook Handler (Lightweight)
- [ ] Create `tools/vote_handler.py`:
  - Listens for Telegram callback queries via polling (not a webhook server).
  - Tracks votes per `alert_id` in a local JSON file (`data/votes.json`).
  - When vote threshold is met, updates the paper portfolio accordingly.
- [ ] Alternatively, use a simple polling approach:
  ```python
  # In the main loop, check for recent callback updates
  updates = requests.get(f"{TELEGRAM_API}/getUpdates?offset={last_update_id}")
  for update in updates["result"]:
      if "callback_query" in update:
          process_vote(update["callback_query"])
  ```

#### 7.3 — Implement Vote Counting Logic
- [ ] Track votes per `alert_id`:
  ```python
  votes = {
      "alert_id_123": {
          "yes": ["user_1", "user_3"],
          "no": ["user_2"],
          "result": "APPROVED",  # or "REJECTED" or "PENDING"
          "expires_at": "2026-02-17T10:00:00Z"
      }
  }
  ```
- [ ] Configurable thresholds:
  - `min_votes`: Minimum votes needed (default: 2).
  - `approval_pct`: Percentage of "yes" votes needed (default: 60%).
  - `vote_window_minutes`: How long voting is open (default: 15 min).

#### 7.4 — Integrate Vote Results into Paper Trader
- [ ] If a signal is `APPROVED` by the team, the paper trader opens the position.
- [ ] If `REJECTED`, the position is not opened but the alert is still logged for performance comparison ("what if we had taken it").
- [ ] This creates a natural A/B test: bot-only trades vs. team-approved trades.

#### 7.5 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  TEAM_VOTING = {
      "enabled": False,           # Set to True to activate voting gate
      "min_votes": 2,             # Minimum votes required
      "approval_pct": 0.6,        # 60% must vote yes
      "vote_window_minutes": 15,  # Voting window
      "auto_approve_a_plus": True, # A+ signals skip voting (optional)
  }
  ```

#### 7.6 — Add Tests
- [ ] In `tests/test_voting.py`:
  - Test vote counting logic (approved, rejected, expired).
  - Test inline keyboard message formatting.
  - Test graceful behavior when voting is disabled.
  - Test auto-approve for A+ tier signals.

### Success Criteria
- [ ] `TRADE` alerts include vote buttons in Telegram.
- [ ] Votes are tracked and counted.
- [ ] Paper trader respects team vote outcomes.
- [ ] Voting can be completely disabled via config.
- [ ] Test: `PYTHONPATH=. python3 -m pytest tests/test_voting.py`

### Verification
```bash
# Unit tests
PYTHONPATH=. python3 -m pytest tests/test_voting.py -v

# Manual: Send a test alert and verify buttons appear in Telegram
# Then click buttons and verify vote counting

# Check that voting is default OFF
python3 -c "from config import TEAM_VOTING; print(TEAM_VOTING['enabled'])"
# Expected: False
```

### Evidence
_(To be filled after completion)_

---

## Phase 8: Smart Alert Enrichment & Dashboard Upgrade

**Priority:** 🟢 LOW — The finishing touch that brings everything together.
**Estimated Time:** 2–3 hours
**Files:** `app.py`, `scripts/pid-129/generate_dashboard.py`, `scripts/pid-129/generate_scorecard.py`
**Depends on:** Phases 1–7 (uses all new intelligence fields)
**API Cost:** $0

### Background

All the intelligence layers from Phases 1–7 need to be surfaced cleanly in both the Telegram alerts and the dashboard. This phase is about **presentation and polish**.

### Tasks

#### 8.1 — Enrich Telegram Alert Format
- [ ] Update `_format_alert()` in `app.py` to include new intelligence fields:
  ```
  --- ALERT ---
  *BTC 1h TRADE (A+)*
  🎯 Direction: SHORT
  💰 Entry: 68,099-68,180
  🛑 Stop: 68,334
  ✅ TP1: 67,880 | TP2: 67,007
  📐 R:R = 1.33
  
  🧠 Intelligence:
  ├ Squeeze: 🔥 FIRE (volatility breakout)
  ├ POC: $67,500 (entry ABOVE value — caution)
  ├ Liquidity: Sell wall @ $68,500 (0.3% away)
  ├ Macro: DXY ↑ HEADWIND | Gold ↓
  ├ Sentiment: -0.35 (Bearish, 70% negative headlines)
  └ Confluence: 78% aligned (5m🟢 15m🟢 1h🟡)
  
  📊 Score: -45 | Confidence: 5
  
  ```json
  { ... full payload ... }
  ```
  ```

#### 8.2 — Add Intelligence Summary Cards to Dashboard
- [ ] In `generate_dashboard.py`, add a new section after "Performance Metrics":
  - **Squeeze Status**: Current squeeze state for each timeframe.
  - **POC Level**: Where "fair value" is right now.
  - **Macro Pulse**: DXY/Gold direction with color indicators.
  - **Sentiment Gauge**: Visual sentiment meter (-1 to +1).

#### 8.3 — Add Historical Intelligence Tracking
- [ ] In `PersistentLogger.log_alert()`, save all new intelligence fields:
  ```python
  record["intelligence"] = {
      "squeeze": alert.context.get("squeeze"),
      "poc": alert.context.get("poc"),
      "liquidity_imbalance": alert.context.get("liquidity", {}).get("imbalance"),
      "macro_dxy": alert.context.get("macro", {}).get("dxy"),
      "sentiment": alert.context.get("sentiment", {}).get("score"),
      "confluence_pct": alert.context.get("confluence_consensus"),
  }
  ```
- [ ] This enables future analysis: "Do alerts with SQUEEZE_FIRE have better outcomes?"

#### 8.4 — Update Scorecard with Intelligence Metrics
- [ ] In `generate_scorecard.py`, add a new section:
  ```
  ## Intelligence Layer Performance (Last 7 Days)
  - Squeeze FIRE signals: 12 alerts, 75% win rate, +2.1R avg
  - POC-aligned entries: 20 alerts, 62% win rate, +1.4R avg
  - Macro headwind signals: 8 alerts, 38% win rate, -0.3R avg
  - Team-approved trades: 5 alerts, 80% win rate, +2.5R avg
  ```
- [ ] This shows which intelligence layers are actually *improving* outcomes.

#### 8.5 — Final Dashboard Polish
- [ ] Add CSS animations for new sections.
- [ ] Add collapsible sections for intelligence details (click to expand).
- [ ] Ensure mobile responsiveness for all new elements.
- [ ] Update the meta-refresh to 30 seconds (from 60) for faster feedback.

#### 8.6 — Update README.md
- [ ] Document all new intelligence layers in the project README.
- [ ] Add a "Quick Start" guide for new developers.
- [ ] Add screenshots of the enriched alert format and dashboard.

### Success Criteria
- [ ] Telegram alerts include all intelligence fields in a clean, readable format.
- [ ] Dashboard displays intelligence summary cards.
- [ ] Historical intelligence data is persisted for analysis.
- [ ] Scorecard reports on intelligence layer performance.
- [ ] README is updated and comprehensive.

### Verification
```bash
# Run full system once
PYTHONPATH=. python3 app.py --once

# Check alert log for intelligence fields
tail -1 logs/pid-129-alerts.jsonl | python3 -m json.tool | grep -A 10 intelligence

# Generate and view dashboard
python3 scripts/pid-129/generate_dashboard.py
open dashboard.html

# Generate scorecard
python3 scripts/pid-129/generate_scorecard.py
cat reports/pid-129-daily-scorecard.md
```

### Evidence
_(To be filled after completion)_

---

## Execution Order & Dependencies

```
Phase 1: Squeeze Detector ──────────────────┐  (standalone)
                                             │
Phase 2: Volume Profile / POC ──────────────┤  (standalone)
                                             │
Phase 3: Liquidity Walls ───────────────────┤  (standalone)
                                             │
Phase 4: Macro Correlation Pulse ───────────┤  (standalone)
                                             │
Phase 5: AI Sentiment Engine ───────────────┤  (standalone)
                                             │
All 1-5 can be done in ANY ORDER or in PARALLEL.
                                             │
                                             ▼
Phase 6: Confluence Heatmap ────────────────┤  (needs 1-5 data)
                                             │
Phase 7: Team Voting Gate ──────────────────┤  (needs enriched alerts)
                                             │
                                             ▼
Phase 8: Smart Alert Enrichment ────────────┘  (needs ALL above)
```

**Total Estimated Time:** 18–25 hours across all phases.
**Recommended Pace:** 1 phase per session (2–3 hour sessions).
**Target Completion:** ~2 weeks of focused sessions.

> **💡 PRO TIP FOR DEVELOPERS:** Phases 1–5 are completely independent. If you have multiple developers, assign each person a different phase and work in parallel. Just coordinate on the `compute_score()` function signature changes.

---

## Quick Reference Commands

```bash
# Run corrected backtest
PYTHONPATH=. python3 tools/run_backtest.py

# Run tests
PYTHONPATH=. python3 -m pytest tests/ -v

# Run live alerts (single cycle)
PYTHONPATH=. python3 app.py --once

# Run continuous monitoring
./run.sh

# Generate scorecard
python3 scripts/pid-129/generate_scorecard.py

# Generate dashboard
python3 scripts/pid-129/generate_dashboard.py

# Paper trader status
python3 tools/paper_trader.py status

# Paper trader report
python3 tools/paper_trader.py report

# Quick sentiment test
python3 -c "from tools.sentiment import SentimentEngine; e = SentimentEngine(); print(e.score_headline('Bitcoin crashes to new low'))"

# Check order book snapshot
python3 -c "from collectors.orderbook import fetch_orderbook; from collectors.base import BudgetManager; print(fetch_orderbook(BudgetManager()))"
```

---

## New Dependencies (v2.1)

| Package | Version | Purpose | Phase |
|:--------|:--------|:--------|:------|
| `vaderSentiment` | >=3.3 | Local NLP sentiment analysis | Phase 5 |

**No other new packages required.** Everything else uses existing libraries (requests, json, math) and free public APIs.

---

## Risk Register

| Risk | Impact | Mitigation |
|:-----|:-------|:-----------|
| Yahoo Finance rate-limits DXY/Gold calls | MEDIUM | Use 5-min polling, cache results, share with existing SPX fetcher |
| VADER sentiment misreads crypto slang | LOW | Extended crypto lexicon + fallback to keyword matching |
| Order book data is stale (5-min snapshots) | LOW | Use for context only, not as primary decision driver |
| Squeeze detector false positives | MEDIUM | Require confirmation from at least 1 other layer |
| Team voting slows down trade execution | LOW | A+ tier auto-approved, configurable timeouts |
| Too many intelligence fields clutter alerts | MEDIUM | Phased rollout, collapsible sections in dashboard |
| Volume Profile POC irrelevant in trending markets | LOW | Weight POC lower when regime = TREND |
| Multiple devs editing `compute_score()` simultaneously | HIGH | Each phase adds a clearly isolated function, merge conflicts are minimal |

---

## Definition of Done (v2.1)

The project reaches v2.1 when ALL of the following are true:

- [ ] Squeeze detector fires correctly during volatility compression releases.
- [ ] Volume Profile POC is calculated and displayed in alerts.
- [ ] Liquidity walls are fetched and flag dangerous positions.
- [ ] DXY and Gold correlation context appears in alerts.
- [ ] AI sentiment replaces (or augments) keyword matching.
- [ ] Confluence heatmap is visible on the dashboard.
- [ ] Team voting gate is implemented and functional (can be disabled).
- [ ] All intelligence layers are persisted for historical analysis.
- [ ] Intelligence performance is tracked in the scorecard.
- [ ] All tests pass: `PYTHONPATH=. python3 -m pytest tests/ -v`.
- [ ] README is updated with v2.1 documentation.

---

_This document is the single source of truth for v2.1 development._
_Update the checkboxes as tasks are completed._
_Last updated: 2026-02-17T09:02:00-05:00_
