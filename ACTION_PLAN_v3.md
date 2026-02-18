# ACTION PLAN v3.0 — The Perfect BTC Alerts System

> **Codename: EMBER APEX**
> **Previous Version:** v2.1 (Intelligence Upgrade — DRAFT)
> **Target:** v3.0 — Production-Grade Intelligence + Infrastructure
> **Created:** 2026-02-18
> **Estimated Total Time:** 30–40 hours across 12 phases.
> **Recommended Pace:** 1 phase per session (2–3 hour sessions).

---

## Executive Summary

v2.0 delivered a **self-validating loop**: alerts fire, outcomes are tracked, a virtual portfolio runs, and results are displayed on a dashboard.

v3.0 is the **complete system**. It adds **seven intelligence layers**, **three infrastructure hardening phases**, a **presentation overhaul**, and a **backtesting framework** to prove every layer works — all using **free APIs** and **local computation**. Zero paid services.

Every phase is written so a **weaker AI or junior developer** can pick it up, execute it, and mark progress. Each task has exact file paths, exact function signatures, exact test commands, and explicit success criteria.

### What v3.0 Delivers

| # | Layer | What It Does | API Cost |
|:--|:------|:-------------|:---------|
| 0 | Infrastructure Preconditions | Fix `AlertScore.context`, `compute_score()` signature, `BudgetManager` limits, feature flags | **$0** |
| 1 | Squeeze Detector | Identifies volatility compression → imminent explosive moves | **$0** (local math) |
| 2 | Volume Profile / POC | Shows where "fair value" is, so you know if entry is cheap or expensive | **$0** (local math) |
| 3 | Liquidity Walls | Reveals hidden buy/sell walls that can trap your position | **$0** (Kraken/Bybit free REST) |
| 4 | Macro Correlation Pulse | Warns when DXY/Gold are fighting your BTC trade | **$0** (Yahoo Finance) |
| 5 | AI Sentiment Engine | Turns 50 news headlines into one actionable sentiment score | **$0** (VADER, local CPU) |
| 6 | Multi-Timeframe Confluence Heatmap | Visual grid showing alignment across all timeframes | **$0** (local math) |
| 7 | Smart Alert Enrichment & Dashboard | Rich Telegram alerts + intelligence dashboard cards | **$0** |
| 8 | Score Recalibration & Threshold Tuning | Normalize scores after adding 6 new point sources | **$0** |
| 9 | Historical Intelligence Backtest | Prove each layer improves outcomes with historical data | **$0** |
| 10 | Error Handling & Circuit Breakers | Graceful degradation when any layer fails | **$0** |
| 11 | Observability & Logging | Structured debug logging for every intelligence layer | **$0** |

### Free API Budget Summary

| Source | Rate Limit | Current Usage/Cycle | v3.0 Usage/Cycle | Headroom |
|:-------|:-----------|:--------------------|:-----------------|:---------|
| Kraken | 15 req/min | ~4 calls | +1 (orderbook) = ~5 | ✅ Safe |
| Bybit | 120 req/min | ~5 calls | +1 (orderbook fallback) = ~6 | ✅ Safe |
| Yahoo Finance | ~2000/day | ~2 calls | +2 (DXY, Gold) = ~4 | ✅ Safe |
| CoinGecko | 10-30/min | 1 call (fallback) | 1 (unchanged) | ✅ Safe |
| Alternative.me | ~500/day | 1 call | 1 (unchanged) | ✅ Safe |
| RSS Feeds | Unlimited | 2 feeds | 2 (unchanged) | ✅ Safe |
| OKX | 20 req/2s | ~3 calls (fallback) | ~3 (unchanged) | ✅ Safe |

---

## Current Architecture (v2.0 Baseline)

```
┌──────────────────────────────────────────────────┐
│                  DATA LAYER                       │
│  Kraken ─┐                                       │
│  Bybit  ─┼─→ collectors/price.py ──→ Candles     │
│  Yahoo  ─┘   collectors/derivatives.py            │
│              collectors/flows.py                  │
│              collectors/social.py (news + F&G)    │
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
│                                                   │
│  utils.py                                         │
│  ├── ema(), rsi(), bollinger_bands(), atr(), adx()│
│  ├── vwap(), zscore(), donchian_break()           │
│  ├── rsi_divergence(), candle_patterns()          │
│  ├── volume_delta(), swing_levels()               │
│  └── percentile_rank()                            │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│               ACTION LAYER                        │
│  app.py                                           │
│  ├── PersistentLogger  → logs/pid-129-alerts.jsonl│
│  ├── Notifier          → Telegram alerts          │
│  ├── AlertStateStore   → Dedup / cooldown         │
│  ├── Portfolio         → Paper trading            │
│  └── _format_alert     → Message formatting       │
│                                                   │
│  tools/                                           │
│  ├── paper_trader.py   → Position management      │
│  ├── outcome_tracker.py→ Win/Loss tracking        │
│  ├── run_backtest.py   → Historical backtest      │
│  └── replay.py         → Alert replay             │
│                                                   │
│  scripts/pid-129/                                 │
│  ├── generate_dashboard.py → dashboard.html       │
│  ├── generate_scorecard.py → Daily scorecard      │
│  └── healthcheck.sh       → System health         │
└──────────────────────────────────────────────────┘
```

### v3.0 Target Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     DATA LAYER (EXPANDED)                     │
│  Kraken  ─┐                                                   │
│  Bybit   ─┼─→ collectors/price.py ──→ Candles                │
│  Yahoo   ─┘                                                   │
│  [NEW] collectors/orderbook.py  ──→ Liquidity Walls           │
│  [UPD] collectors/price.py      ──→ DXY + Gold Candles        │
│  collectors/social.py + [NEW] tools/sentiment.py → AI Score   │
│  collectors/derivatives.py  ──→ Funding + OI + Basis          │
│  collectors/flows.py        ──→ Taker/Long-Short ratios       │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│               INTELLIGENCE LAYER (NEW)                        │
│  intelligence/                                                │
│  ├── __init__.py       → IntelligenceBundle dataclass         │
│  ├── squeeze.py        → BB/KC compression detection          │
│  ├── volume_profile.py → POC + Value Area calculation         │
│  ├── liquidity.py      → Wall detection + imbalance           │
│  ├── macro.py          → DXY/Gold correlation analysis        │
│  ├── sentiment.py      → VADER NLP + crypto lexicon           │
│  └── confluence.py     → Multi-TF heatmap grid                │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│                  ENGINE LAYER (UPDATED)                        │
│  engine.py                                                     │
│  ├── [EXISTING] _regime(), _detector_candidates(), etc.       │
│  ├── [UPDATED] compute_score() → accepts IntelligenceBundle   │
│  └── [UPDATED] AlertScore     → has `context` + `intel` dict  │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│               ACTION LAYER (ENHANCED)                         │
│  app.py                                                        │
│  ├── [UPDATED] _format_alert()  → Shows all intelligence      │
│  ├── [UPDATED] PersistentLogger → Saves intelligence fields   │
│  ├── [NEW] _collect_intelligence() → Orchestrates all layers  │
│  ├── [UPDATED] Dashboard        → Confluence heatmap          │
│  └── [EXISTING] Portfolio, Outcomes, Logging                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Infrastructure Preconditions

**Priority:** 🔴 CRITICAL — Every subsequent phase depends on this.
**Estimated Time:** 1–2 hours
**Files:** `engine.py`, `config.py`, `collectors/base.py`, `intelligence/__init__.py` [NEW]
**Depends on:** Nothing
**API Cost:** $0

### Background

The v2.0 codebase has structural gaps that will block every intelligence phase. These must be fixed first:
1. `AlertScore` has no `context` dict field — Phases 1–6 all write to it.
2. `compute_score()` has a fixed positional signature — adding new data types requires refactoring.
3. `BudgetManager.LIMITS["yahoo"]` is set to `(0, 300.0)` — zero calls allowed. Phase 4 needs Yahoo.
4. No feature flags exist to enable/disable individual intelligence layers.
5. No `intelligence/` package exists for the new modules.

### Tasks

#### 0.1 — Add `context` Field to `AlertScore`
- [ ] In `engine.py`, add `context: Dict[str, object] = field(default_factory=dict)` to `AlertScore` dataclass.
- [ ] Position it after `decision_trace`.
- [ ] Verify existing code that reads `AlertScore` does not break (grep for `AlertScore` usage in `app.py`, `tools/paper_trader.py`, `tools/outcome_tracker.py`).

#### 0.2 — Create `IntelligenceBundle` Dataclass
- [ ] Create directory `intelligence/` in project root.
- [ ] Create `intelligence/__init__.py` with:
  ```python
  from dataclasses import dataclass, field
  from typing import Optional, Dict, Any

  @dataclass
  class IntelligenceBundle:
      """Container for all intelligence layer results.
      Each field is Optional so compute_score() works even if a layer fails."""
      squeeze: Optional[Dict[str, Any]] = None        # Phase 1
      volume_profile: Optional[Dict[str, Any]] = None  # Phase 2
      liquidity: Optional[Dict[str, Any]] = None       # Phase 3
      macro: Optional[Dict[str, Any]] = None           # Phase 4
      sentiment: Optional[Dict[str, Any]] = None       # Phase 5
      confluence: Optional[Dict[str, Any]] = None      # Phase 6
  ```

#### 0.3 — Refactor `compute_score()` Signature
- [ ] Add `intel: Optional[IntelligenceBundle] = None` as the last parameter to `compute_score()`.
- [ ] Import `IntelligenceBundle` at top of `engine.py`.
- [ ] Default to `IntelligenceBundle()` if `None` is passed.
- [ ] Update the single call site in `app.py` `run()` function to pass `intel=None` initially.
- [ ] **DO NOT change any existing parameters** — backward compatibility is mandatory.

#### 0.4 — Fix Yahoo Finance BudgetManager Limit
- [ ] In `collectors/base.py`, change `BudgetManager.LIMITS["yahoo"]` from `(0, 300.0)` to `(10, 300.0)`.
- [ ] This allows 10 Yahoo calls per 5-minute window (DXY + Gold + SPX + VIX + NQ = 5 symbols max).

#### 0.5 — Add Feature Flags to `config.py`
- [ ] Add to `config.py`:
  ```python
  INTELLIGENCE_FLAGS = {
      "squeeze_enabled": True,
      "volume_profile_enabled": True,
      "liquidity_enabled": True,
      "macro_correlation_enabled": True,
      "sentiment_enabled": True,
      "confluence_enabled": True,
  }
  ```
- [ ] Update `validate_config()` to check that all keys in `INTELLIGENCE_FLAGS` are booleans.

#### 0.6 — Add Tests for Preconditions
- [ ] In `tests/test_preconditions.py`:
  - Test `AlertScore` has `context` field and it defaults to `{}`.
  - Test `IntelligenceBundle` can be instantiated with no args (all None).
  - Test `compute_score()` still works with `intel=None`.
  - Test `BudgetManager` allows Yahoo calls after fix.
  - Test `INTELLIGENCE_FLAGS` contains all expected keys.

### Success Criteria
- [ ] `AlertScore(context={})` works.
- [ ] `IntelligenceBundle()` works with all fields as `None`.
- [ ] `compute_score(..., intel=None)` produces identical output to before.
- [ ] `BudgetManager().can_call("yahoo")` returns `True`.
- [ ] All feature flags default to `True`.
- [ ] Test: `PYTHONPATH=. python -m pytest tests/test_preconditions.py -v`

### Verification
```bash
PYTHONPATH=. python -m pytest tests/test_preconditions.py -v
# Also run existing tests to confirm no regressions:
PYTHONPATH=. python -m pytest tests/ -v
```

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 1: Squeeze Detector — Volatility Compression

**Priority:** 🔴 HIGH — Signals during a "squeeze" have 2–3x higher R:R.
**Estimated Time:** 2–3 hours
**Files:** `intelligence/squeeze.py` [NEW], `engine.py`, `config.py`
**Depends on:** Phase 0
**API Cost:** $0 (pure local math)

### Background

The "TTM Squeeze" (John Carter) identifies when Bollinger Bands contract *inside* Keltner Channels. This compression signals a large move is about to happen — like a coiled spring.

- **Squeeze ON** = BB inside KC (low volatility, coiling).
- **Squeeze FIRE** = BB just expanded outside KC (the move starts).
- **No Squeeze** = Normal volatility.

### Tasks

#### 1.1 — Create `intelligence/squeeze.py`
- [ ] Create new file `intelligence/squeeze.py`.
- [ ] Import from `utils`: `bollinger_bands`, `atr`, and `Candle`.
- [ ] Implement `keltner_channels(candles, period=20, atr_mult=1.5)`:
  ```python
  def keltner_channels(candles: List[Candle], period: int = 20, atr_mult: float = 1.5):
      """Returns (upper, middle, lower) for latest candle."""
      if len(candles) < period:
          return None
      closes = [c.close for c in candles[-period:]]
      middle = sum(closes) / len(closes)
      atr_val = atr(candles, period)
      if atr_val is None:
          return None
      return (middle + atr_mult * atr_val, middle, middle - atr_mult * atr_val)
  ```

#### 1.2 — Implement Squeeze Detection Function
- [ ] In `intelligence/squeeze.py`, implement `detect_squeeze(candles)`:
  ```python
  def detect_squeeze(candles: List[Candle]) -> Dict[str, Any]:
      """Detect TTM Squeeze state.
      Returns: {"state": "SQUEEZE_ON"|"SQUEEZE_FIRE"|"NONE", "pts": int, "bb_width": float, "kc_width": float}
      """
      if len(candles) < 22:  # Need 20 + 2 for previous comparison
          return {"state": "NONE", "pts": 0, "bb_width": 0.0, "kc_width": 0.0}

      closes = [c.close for c in candles]

      # Current state
      bb = bollinger_bands(closes, period=20, multiplier=2.0)
      kc = keltner_channels(candles, period=20, atr_mult=1.5)
      if bb is None or kc is None:
          return {"state": "NONE", "pts": 0, "bb_width": 0.0, "kc_width": 0.0}

      bb_upper, bb_mid, bb_lower = bb
      kc_upper, kc_mid, kc_lower = kc
      squeeze_on = bb_lower > kc_lower and bb_upper < kc_upper

      # Previous state (for FIRE detection)
      prev_closes = closes[:-1]
      prev_bb = bollinger_bands(prev_closes, period=20, multiplier=2.0)
      prev_kc = keltner_channels(candles[:-1], period=20, atr_mult=1.5)

      was_squeeze = False
      if prev_bb and prev_kc:
          was_squeeze = prev_bb[2] > prev_kc[2] and prev_bb[0] < prev_kc[0]

      squeeze_fire = was_squeeze and not squeeze_on

      bb_width = bb_upper - bb_lower
      kc_width = kc_upper - kc_lower

      if squeeze_fire:
          return {"state": "SQUEEZE_FIRE", "pts": 8, "bb_width": bb_width, "kc_width": kc_width}
      elif squeeze_on:
          return {"state": "SQUEEZE_ON", "pts": 0, "bb_width": bb_width, "kc_width": kc_width}
      else:
          return {"state": "NONE", "pts": 0, "bb_width": bb_width, "kc_width": kc_width}
  ```

#### 1.3 — Integrate into `compute_score()`
- [ ] In `engine.py`, inside `compute_score()`, after the existing logic but before final score calculation:
  ```python
  from config import INTELLIGENCE_FLAGS
  # Squeeze integration
  if intel and intel.squeeze and INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
      sq = intel.squeeze
      if sq["state"] == "SQUEEZE_FIRE":
          breakdown["volatility"] += sq["pts"]
          codes.append("SQUEEZE_FIRE")
      elif sq["state"] == "SQUEEZE_ON":
          codes.append("SQUEEZE_ON")
      score_obj.context["squeeze"] = sq["state"]
  ```
- [ ] Place this block in a clearly commented section: `# --- Intelligence Layer: Squeeze ---`.

#### 1.4 — Wire Up in `app.py`
- [ ] In `app.py` `run()`, after candle collection, compute squeeze for each timeframe:
  ```python
  from intelligence.squeeze import detect_squeeze
  from intelligence import IntelligenceBundle

  intel = IntelligenceBundle()
  if INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
      intel.squeeze = detect_squeeze(candles)
  ```
- [ ] Pass `intel=intel` to `compute_score()`.

#### 1.5 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  SQUEEZE = {
      "bb_period": 20,
      "bb_std": 2.0,
      "kc_period": 20,
      "kc_atr_mult": 1.5,
      "fire_bonus_pts": 8,
  }
  ```

#### 1.6 — Add Tests
- [ ] Create `tests/test_squeeze.py`:
  - Test with synthetic candles where BB is inside KC → `SQUEEZE_ON`.
  - Test with synthetic candles where squeeze just released → `SQUEEZE_FIRE`.
  - Test with normal volatility → `NONE`.
  - Test edge case: fewer than 22 candles → graceful `NONE`.
  - Test that `detect_squeeze` returns correct dict keys.

### Success Criteria
- [ ] `SQUEEZE_FIRE` code appears in alerts when volatility compression releases.
- [ ] `SQUEEZE_ON` code appears when market is coiling.
- [ ] No new API calls are made.
- [ ] Test: `PYTHONPATH=. python -m pytest tests/test_squeeze.py -v`

### Verification
```bash
PYTHONPATH=. python -m pytest tests/test_squeeze.py -v
PYTHONPATH=. python -m pytest tests/ -v  # No regressions
```

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 2: Volume Profile & Point of Control (POC)

**Priority:** 🔴 HIGH — Knowing if you're buying at "fair value" or "expensive" is critical.
**Estimated Time:** 2–3 hours
**Files:** `intelligence/volume_profile.py` [NEW], `engine.py`, `config.py`
**Depends on:** Phase 0
**API Cost:** $0 (pure local math)

### Background

The Volume Profile shows how much volume traded at each price level. The **Point of Control (POC)** is the price with highest traded volume — it acts as a magnet. The **Value Area** covers 70% of all volume and represents "fair value."

- **Entry below POC** = Buying cheap (good for longs).
- **Entry above POC** = Buying expensive (risky for longs, good for shorts).
- **Entry inside Value Area** = At "fair value."

### Tasks

#### 2.1 — Create `intelligence/volume_profile.py`
- [ ] Create new file `intelligence/volume_profile.py`.
- [ ] Implement `compute_volume_profile(candles, current_price, num_bins=50)`:
  ```python
  def compute_volume_profile(candles: List[Candle], current_price: float, num_bins: int = 50) -> Dict[str, Any]:
      """Compute volume profile, POC, and value area.
      Returns: {"poc": float, "va_high": float, "va_low": float, "position": str, "pts": float}
      """
      if len(candles) < 5:
          return {"poc": 0.0, "va_high": 0.0, "va_low": 0.0, "position": "UNKNOWN", "pts": 0.0}

      all_highs = [c.high for c in candles]
      all_lows = [c.low for c in candles]
      price_min, price_max = min(all_lows), max(all_highs)

      if price_max == price_min:
          return {"poc": price_min, "va_high": price_max, "va_low": price_min, "position": "AT_VALUE", "pts": 0.0}

      bin_size = (price_max - price_min) / num_bins
      bins = [0.0] * num_bins

      for c in candles:
          low_bin = int((c.low - price_min) / bin_size)
          high_bin = int((c.high - price_min) / bin_size)
          low_bin = max(0, min(low_bin, num_bins - 1))
          high_bin = max(0, min(high_bin, num_bins - 1))
          spread = max(high_bin - low_bin, 1)
          for b in range(low_bin, min(high_bin + 1, num_bins)):
              bins[b] += c.volume / spread

      # POC
      poc_bin = bins.index(max(bins))
      poc_price = price_min + (poc_bin + 0.5) * bin_size

      # Value Area (70% of total volume)
      total_vol = sum(bins)
      target_vol = total_vol * 0.70
      accumulated = bins[poc_bin]
      low_idx, high_idx = poc_bin, poc_bin
      while accumulated < target_vol and (low_idx > 0 or high_idx < num_bins - 1):
          look_down = bins[low_idx - 1] if low_idx > 0 else 0
          look_up = bins[high_idx + 1] if high_idx < num_bins - 1 else 0
          if look_down >= look_up and low_idx > 0:
              low_idx -= 1
              accumulated += bins[low_idx]
          elif high_idx < num_bins - 1:
              high_idx += 1
              accumulated += bins[high_idx]
          else:
              low_idx -= 1
              accumulated += bins[low_idx]

      va_low = price_min + low_idx * bin_size
      va_high = price_min + (high_idx + 1) * bin_size

      # Position relative to value area
      if current_price < va_low:
          position = "BELOW_VALUE"
          pts = 3.0
      elif current_price > va_high:
          position = "ABOVE_VALUE"
          pts = -3.0
      else:
          position = "AT_VALUE"
          pts = 0.0

      return {"poc": round(poc_price, 2), "va_high": round(va_high, 2), "va_low": round(va_low, 2), "position": position, "pts": pts}
  ```

#### 2.2 — Integrate into `compute_score()`
- [ ] In `engine.py`, add after squeeze block:
  ```python
  # --- Intelligence Layer: Volume Profile ---
  if intel and intel.volume_profile and INTELLIGENCE_FLAGS.get("volume_profile_enabled", True):
      vp = intel.volume_profile
      breakdown["volume"] += vp["pts"]
      codes.append(f"POC_{vp['position']}")
      score_obj.context["poc"] = vp["poc"]
      score_obj.context["value_area"] = vp["position"]
  ```

#### 2.3 — Wire Up in `app.py`
- [ ] After candle collection in `run()`:
  ```python
  from intelligence.volume_profile import compute_volume_profile
  if INTELLIGENCE_FLAGS.get("volume_profile_enabled", True):
      intel.volume_profile = compute_volume_profile(candles, btc_price.price)
  ```

#### 2.4 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  VOLUME_PROFILE = {
      "num_bins": 50,
      "value_area_pct": 0.70,
      "poc_bonus_pts": 3,
  }
  ```

#### 2.5 — Add Tests
- [ ] Create `tests/test_volume_profile.py`:
  - Test POC with uniform volume → midpoint.
  - Test value area with concentrated volume → tight VA.
  - Test position detection (below, above, at value).
  - Test single candle → graceful default.
  - Test zero-volume edge case.

### Success Criteria
- [ ] `POC_BELOW_VALUE` or `POC_ABOVE_VALUE` appears in alerts.
- [ ] POC price visible in alert `context`.
- [ ] No new API calls.
- [ ] Test: `PYTHONPATH=. python -m pytest tests/test_volume_profile.py -v`

### Verification
```bash
PYTHONPATH=. python -m pytest tests/test_volume_profile.py -v
PYTHONPATH=. python -m pytest tests/ -v
```

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 3: Liquidity Walls — Order Book Intelligence

**Priority:** 🟡 MEDIUM — Prevents trading into a wall.
**Estimated Time:** 2–3 hours
**Files:** `collectors/orderbook.py` [NEW], `intelligence/liquidity.py` [NEW], `engine.py`, `config.py`, `collectors/base.py`
**Depends on:** Phase 0
**API Cost:** $0 (Kraken/Bybit free REST — ~1 req/5 min per source)

### Background

Large buy/sell orders ("walls") on the order book can block price movement. If you go LONG and there's a $20M sell wall $100 above entry, your trade will likely fail. A massive buy wall below entry acts as a floor.

### Free API Endpoints

| Exchange | Endpoint | Rate Limit | Our Usage |
|:---------|:---------|:-----------|:----------|
| Kraken | `/0/public/Depth?pair=XXBTZUSD&count=100` | ~15 req/min | 1 req/5 min |
| Bybit | `/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=50` | 120 req/min | 1 req/5 min (fallback) |

### Tasks

#### 3.1 — Create `collectors/orderbook.py`
- [ ] Create new file `collectors/orderbook.py`.
- [ ] Implement `OrderBookSnapshot` dataclass:
  ```python
  @dataclass
  class OrderBookSnapshot:
      bid_walls: List[Tuple[float, float]]    # [(price, size_usd), ...]
      ask_walls: List[Tuple[float, float]]    # [(price, size_usd), ...]
      bid_total_usd: float
      ask_total_usd: float
      imbalance: float  # (bid - ask) / (bid + ask), range -1 to +1
      nearest_bid_wall: Optional[Tuple[float, float]] = None
      nearest_ask_wall: Optional[Tuple[float, float]] = None
      source: str = "none"
      healthy: bool = True
  ```

#### 3.2 — Implement Kraken/Bybit Fetchers
- [ ] Function `fetch_orderbook(budget, current_price)`:
  - Try Kraken first → `/0/public/Depth?pair=XXBTZUSD&count=100`.
  - Fallback to Bybit → `/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=50`.
  - Parse bid/ask levels into `(price, size_btc * price)` tuples.
  - Calculate `imbalance = (bid_total - ask_total) / (bid_total + ask_total)`.
- [ ] Function `_detect_walls(levels, current_price, threshold_mult=2.0)`:
  - Flag any level where `size > avg_size * threshold_mult` as a "wall."
  - Sort walls by proximity to `current_price`.
  - Return walls list and nearest wall.

#### 3.3 — Create `intelligence/liquidity.py`
- [ ] Implement `analyze_liquidity(orderbook, direction, current_price)`:
  ```python
  def analyze_liquidity(ob: OrderBookSnapshot, direction: str, current_price: float) -> Dict[str, Any]:
      """Analyze order book for trade direction.
      Returns: {"imbalance": float, "nearest_wall": str, "wall_distance_pct": float,
                "blocker": bool, "bias": str, "pts": float}
      """
      if not ob.healthy:
          return {"imbalance": 0.0, "nearest_wall": "N/A", "wall_distance_pct": 0.0,
                  "blocker": False, "bias": "NEUTRAL", "pts": 0.0}

      result = {"imbalance": round(ob.imbalance, 3), "blocker": False, "bias": "NEUTRAL", "pts": 0.0}

      # Check for blocking walls
      if direction == "LONG" and ob.nearest_ask_wall:
          wall_price, wall_size = ob.nearest_ask_wall
          dist_pct = (wall_price - current_price) / current_price
          result["nearest_wall"] = f"${wall_price:,.0f} (sell, ${wall_size:,.0f})"
          result["wall_distance_pct"] = round(dist_pct * 100, 2)
          if dist_pct < 0.005:  # Wall within 0.5%
              result["blocker"] = True
      elif direction == "SHORT" and ob.nearest_bid_wall:
          wall_price, wall_size = ob.nearest_bid_wall
          dist_pct = (current_price - wall_price) / current_price
          result["nearest_wall"] = f"${wall_price:,.0f} (buy, ${wall_size:,.0f})"
          result["wall_distance_pct"] = round(dist_pct * 100, 2)
          if dist_pct < 0.005:
              result["blocker"] = True

      # Imbalance scoring
      if ob.imbalance > 0.3:
          result["bias"] = "IMBALANCE_BULL"
          result["pts"] = 3.0
      elif ob.imbalance < -0.3:
          result["bias"] = "IMBALANCE_BEAR"
          result["pts"] = -3.0

      return result
  ```

#### 3.4 — Integrate into `compute_score()`
- [ ] Add after volume profile block:
  ```python
  # --- Intelligence Layer: Liquidity ---
  if intel and intel.liquidity and INTELLIGENCE_FLAGS.get("liquidity_enabled", True):
      liq = intel.liquidity
      breakdown["volume"] += liq["pts"]
      if liq["blocker"]:
          codes.append("LIQ_WALL_BLOCKER")
          blockers.append("Liquidity wall blocking trade path")
      if liq["bias"] != "NEUTRAL":
          codes.append(f"LIQ_{liq['bias']}")
      score_obj.context["liquidity"] = {
          "imbalance": liq["imbalance"],
          "nearest_wall": liq.get("nearest_wall", "N/A"),
          "wall_distance_pct": liq.get("wall_distance_pct", 0.0),
      }
  ```

#### 3.5 — Wire Up in `app.py`
- [ ] In `run()`, after price fetch:
  ```python
  from collectors.orderbook import fetch_orderbook
  from intelligence.liquidity import analyze_liquidity

  orderbook = None
  if INTELLIGENCE_FLAGS.get("liquidity_enabled", True):
      try:
          orderbook = fetch_orderbook(bm, btc_price.price)
      except Exception as e:
          logger.warning(f"Orderbook fetch failed: {e}")
  ```
- [ ] After direction is known (inside the per-timeframe loop):
  ```python
  if orderbook and orderbook.healthy:
      intel.liquidity = analyze_liquidity(orderbook, direction, btc_price.price)
  ```

#### 3.6 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  LIQUIDITY = {
      "wall_threshold_mult": 2.0,
      "wall_danger_pct": 0.005,
      "imbalance_threshold": 0.3,
      "imbalance_pts": 3,
  }
  ```

#### 3.7 — Add Tests
- [ ] Create `tests/test_liquidity.py`:
  - Test wall detection with synthetic order book.
  - Test imbalance calculation (balanced, bullish, bearish).
  - Test blocker when wall is within danger zone.
  - Test graceful degradation when `healthy=False`.
  - Test with empty bid/ask lists.

### Success Criteria
- [ ] `LIQ_WALL_BLOCKER` appears when a wall blocks the trade path.
- [ ] `LIQ_IMBALANCE_BULL` / `BEAR` appears based on order book bias.
- [ ] API calls stay within free limits.
- [ ] Test: `PYTHONPATH=. python -m pytest tests/test_liquidity.py -v`

### Verification
```bash
PYTHONPATH=. python -m pytest tests/test_liquidity.py -v
PYTHONPATH=. python -m pytest tests/ -v
```

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 4: Macro Correlation Pulse — DXY & Gold

**Priority:** 🟡 MEDIUM — BTC doesn't move in isolation.
**Estimated Time:** 2 hours
**Files:** `collectors/price.py` (expand), `intelligence/macro.py` [NEW], `engine.py`, `config.py`
**Depends on:** Phase 0 (specifically the Yahoo budget fix 0.4)
**API Cost:** $0 (Yahoo Finance — 2 additional calls/cycle)

### Background

BTC has strong inverse correlation with DXY and moderate positive correlation with Gold:
- **DXY UP + BTC LONG → WARNING** (headwind)
- **DXY DOWN + BTC LONG → CONFIRMATION** (tailwind)
- **Gold UP + BTC LONG → CONFIRMATION** (risk-on macro)

### Free API Strategy

| Asset | Yahoo Symbol | Interval | Usage |
|:------|:------------|:---------|:------|
| DXY | `DX-Y.NYB` | `5m` | 1 call/5 min |
| Gold | `GC=F` | `5m` | 1 call/5 min |

### Tasks

#### 4.1 — Add DXY & Gold Fetchers to `collectors/price.py`
- [ ] Add function `fetch_dxy_candles(budget, limit=30)`:
  - Uses existing `_fetch_yahoo_symbol_candles(budget, "DX-Y.NYB", "5m", "1d", limit)`.
- [ ] Add function `fetch_gold_candles(budget, limit=30)`:
  - Uses existing `_fetch_yahoo_symbol_candles(budget, "GC=F", "5m", "1d", limit)`.
- [ ] Add combined function `fetch_macro_assets(budget)`:
  ```python
  def fetch_macro_assets(budget: BudgetManager) -> Dict[str, List[Candle]]:
      dxy = fetch_dxy_candles(budget)
      time.sleep(1.0)  # Throttle between calls
      gold = fetch_gold_candles(budget)
      return {"dxy": dxy, "gold": gold}
  ```

#### 4.2 — Create `intelligence/macro.py`
- [ ] Implement `analyze_macro_correlation(dxy_candles, gold_candles, btc_candles, direction)`:
  ```python
  def analyze_macro_correlation(dxy: List[Candle], gold: List[Candle],
                                 btc: List[Candle], direction: str) -> Dict[str, Any]:
      """Analyze DXY and Gold correlation with BTC trade direction.
      Returns: {"dxy_bias": str, "gold_confirm": bool, "dxy_roc": float,
                "gold_roc": float, "pts": float}
      """
      def _roc(candles, period=20):
          if len(candles) < period + 1:
              return 0.0
          return (candles[-1].close - candles[-period].close) / candles[-period].close

      dxy_roc = _roc(dxy)
      gold_roc = _roc(gold)

      result = {"dxy_bias": "NEUTRAL", "gold_confirm": False,
                "dxy_roc": round(dxy_roc, 5), "gold_roc": round(gold_roc, 5), "pts": 0.0}

      # DXY analysis (inverse correlation with BTC)
      dxy_threshold = 0.002  # 0.2% move
      if direction == "LONG":
          if dxy_roc > dxy_threshold:
              result["dxy_bias"] = "HEADWIND"
              result["pts"] -= 3.0
          elif dxy_roc < -dxy_threshold:
              result["dxy_bias"] = "TAILWIND"
              result["pts"] += 3.0
      elif direction == "SHORT":
          if dxy_roc > dxy_threshold:
              result["dxy_bias"] = "TAILWIND"
              result["pts"] += 3.0
          elif dxy_roc < -dxy_threshold:
              result["dxy_bias"] = "HEADWIND"
              result["pts"] -= 3.0

      # Gold confirmation
      gold_threshold = 0.003  # 0.3% move
      btc_roc = _roc(btc)
      if gold_roc > gold_threshold and btc_roc > 0:
          result["gold_confirm"] = True
          result["pts"] += 2.0

      return result
  ```

#### 4.3 — Integrate into `compute_score()`
- [ ] Add after liquidity block:
  ```python
  # --- Intelligence Layer: Macro Correlation ---
  if intel and intel.macro and INTELLIGENCE_FLAGS.get("macro_correlation_enabled", True):
      mc = intel.macro
      breakdown["htf"] += mc["pts"]
      if mc["dxy_bias"] == "HEADWIND":
          codes.append("MACRO_HEADWIND")
      elif mc["dxy_bias"] == "TAILWIND":
          codes.append("MACRO_TAILWIND")
      if mc["gold_confirm"]:
          codes.append("GOLD_CONFIRM")
      score_obj.context["macro"] = {"dxy": mc["dxy_bias"], "gold": "CONFIRM" if mc["gold_confirm"] else "NEUTRAL"}
  ```

#### 4.4 — Wire Up in `app.py`
- [ ] In `run()`, after existing macro fetch:
  ```python
  from collectors.price import fetch_macro_assets
  from intelligence.macro import analyze_macro_correlation

  macro_assets = {"dxy": [], "gold": []}
  if INTELLIGENCE_FLAGS.get("macro_correlation_enabled", True):
      try:
          macro_assets = fetch_macro_assets(bm)
      except Exception as e:
          logger.warning(f"Macro asset fetch failed: {e}")
  ```
- [ ] Inside per-timeframe loop (after direction is known):
  ```python
  if macro_assets["dxy"] or macro_assets["gold"]:
      intel.macro = analyze_macro_correlation(
          macro_assets["dxy"], macro_assets["gold"], candles, direction
      )
  ```

#### 4.5 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  MACRO_CORRELATION = {
      "roc_period": 20,
      "dxy_threshold": 0.002,
      "gold_threshold": 0.003,
      "headwind_penalty": -3,
      "tailwind_bonus": 3,
      "gold_confirm_bonus": 2,
  }
  ```

#### 4.6 — Add Tests
- [ ] Create `tests/test_macro.py`:
  - Test DXY headwind (DXY up, BTC long → negative).
  - Test DXY tailwind (DXY down, BTC long → positive).
  - Test Gold confirmation (Gold up + BTC up → bonus).
  - Test SHORT direction (inverted DXY logic).
  - Test empty candle lists → graceful defaults.

### Success Criteria
- [ ] `MACRO_HEADWIND` / `MACRO_TAILWIND` appears in alerts.
- [ ] `GOLD_CONFIRM` appears when gold confirms.
- [ ] Yahoo usage stays within free limits.
- [ ] Test: `PYTHONPATH=. python -m pytest tests/test_macro.py -v`

### Verification
```bash
PYTHONPATH=. python -m pytest tests/test_macro.py -v
PYTHONPATH=. python -m pytest tests/ -v
```

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 5: AI Sentiment Engine — Local NLP

**Priority:** 🟡 MEDIUM — Turns noisy headlines into one actionable number.
**Estimated Time:** 2–3 hours
**Files:** `intelligence/sentiment.py` [NEW], `engine.py`, `config.py`, `requirements.txt`
**Depends on:** Phase 0
**API Cost:** $0 (VADER runs 100% locally, no network calls)

### Background

Headlines are already collected via `collectors/social.py` `fetch_news()`. Currently they use basic keyword matching (`NEWS_DICT` in `engine.py`). VADER scores each headline from -1 to +1 and aggregates them.

### Why VADER?

| Feature | VADER | OpenAI | Local LLM |
|:--------|:------|:-------|:----------|
| Cost | Free | $$$ | Free but slow |
| Speed | <1ms/headline | 500ms/call | 2-5s/call |
| Privacy | 100% local | Cloud | 100% local |
| Dependencies | 1 pip package | API key | 4GB+ model |

### Tasks

#### 5.1 — Add VADER Dependency
- [ ] Add `vaderSentiment>=3.3` to `requirements.txt`.
- [ ] Install: `python -m pip install vaderSentiment`.

#### 5.2 — Create `intelligence/sentiment.py`
- [ ] Implement `SentimentEngine` class (singleton pattern for efficiency):
  ```python
  _engine_instance = None

  class SentimentEngine:
      def __init__(self):
          from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
          self.analyzer = SentimentIntensityAnalyzer()
          # Extend with crypto-specific terms
          self.analyzer.lexicon.update({
              "bullish": 2.0, "bearish": -2.0, "dump": -2.5, "pump": 2.0,
              "crash": -3.0, "moon": 2.5, "hack": -3.0, "exploit": -2.5,
              "whale": 0.5, "liquidation": -1.5, "etf": 1.5, "approval": 2.0,
              "ban": -2.5, "regulation": -1.0, "adoption": 2.0, "institutional": 1.5,
              "accumulation": 1.5, "distribution": -1.5, "breakout": 1.5, "breakdown": -1.5,
              "support": 0.8, "resistance": -0.3, "fud": -1.5, "fomo": 1.0,
              "halving": 1.5, "halvening": 1.5, "defi": 0.5, "nft": 0.3,
              "staking": 0.5, "yield": 0.3, "airdrop": 0.8, "rug": -3.0,
              "scam": -2.5, "sec": -0.5, "lawsuit": -1.5, "settlement": 0.5,
          })

      def score_headline(self, text: str) -> float:
          return self.analyzer.polarity_scores(text)["compound"]

      def score_batch(self, headlines) -> Dict[str, Any]:
          scores = [self.score_headline(h.title if hasattr(h, 'title') else str(h))
                    for h in headlines[:50]]  # Cap at 50
          if not scores:
              return {"composite": 0.0, "bullish_pct": 0, "bearish_pct": 0, "count": 0}
          bullish = sum(1 for s in scores if s > 0.05)
          bearish = sum(1 for s in scores if s < -0.05)
          return {
              "composite": round(sum(scores) / len(scores), 4),
              "bullish_pct": round(bullish / len(scores) * 100),
              "bearish_pct": round(bearish / len(scores) * 100),
              "strongest_bull": round(max(scores), 4),
              "strongest_bear": round(min(scores), 4),
              "count": len(scores),
          }

  def get_engine() -> Optional[SentimentEngine]:
      global _engine_instance
      if _engine_instance is None:
          try:
              _engine_instance = SentimentEngine()
          except ImportError:
              return None
      return _engine_instance

  def analyze_sentiment(headlines) -> Dict[str, Any]:
      engine = get_engine()
      if engine is None:
          return {"composite": 0.0, "bullish_pct": 0, "bearish_pct": 0,
                  "count": 0, "fallback": True}
      result = engine.score_batch(headlines)
      result["fallback"] = False
      return result
  ```
- [ ] Note the singleton pattern: `get_engine()` creates the analyzer once, reusing it across cycles.

#### 5.3 — Integrate into `compute_score()`
- [ ] Add after macro block:
  ```python
  # --- Intelligence Layer: Sentiment ---
  if intel and intel.sentiment and INTELLIGENCE_FLAGS.get("sentiment_enabled", True):
      sent = intel.sentiment
      if not sent.get("fallback", True):
          if sent["composite"] > 0.3:
              breakdown["momentum"] += 4.0
              codes.append("SENTIMENT_BULL")
          elif sent["composite"] < -0.3:
              breakdown["momentum"] -= 4.0
              codes.append("SENTIMENT_BEAR")
          elif abs(sent["composite"]) < 0.05:
              codes.append("SENTIMENT_NEUTRAL")
          score_obj.context["sentiment"] = {
              "score": sent["composite"],
              "bull_pct": sent["bullish_pct"],
              "bear_pct": sent["bearish_pct"],
          }
  ```
- [ ] **Keep existing `NEWS_DICT` keyword logic** as a fallback — it still runs regardless.

#### 5.4 — Wire Up in `app.py`
- [ ] In `run()`, after news collection:
  ```python
  from intelligence.sentiment import analyze_sentiment
  if INTELLIGENCE_FLAGS.get("sentiment_enabled", True) and news:
      intel.sentiment = analyze_sentiment(news)
  ```

#### 5.5 — Add Config Tunables
- [ ] Add to `config.py`:
  ```python
  SENTIMENT = {
      "strong_threshold": 0.3,
      "weak_threshold": 0.05,
      "bull_pts": 4,
      "bear_pts": -4,
      "max_headlines": 50,
  }
  ```

#### 5.6 — Add Tests
- [ ] Create `tests/test_sentiment.py`:
  - Test bullish headline → positive score.
  - Test bearish headline → negative score.
  - Test crypto terms ("BTC ETF approved" → strongly positive).
  - Test mixed headlines → near-neutral composite.
  - Test empty list → graceful default.
  - Test fallback when VADER not installed (mock ImportError).
  - Test singleton pattern (same instance returned).

### Success Criteria
- [ ] `SENTIMENT_BULL` / `SENTIMENT_BEAR` in alerts based on news.
- [ ] Composite score visible in alert `context`.
- [ ] No external API calls for sentiment itself.
- [ ] Falls back gracefully if VADER not installed.
- [ ] Test: `PYTHONPATH=. python -m pytest tests/test_sentiment.py -v`

### Verification
```bash
python -m pip install vaderSentiment
PYTHONPATH=. python -m pytest tests/test_sentiment.py -v
# Smoke test:
python -c "from intelligence.sentiment import analyze_sentiment; from collectors.social import Headline; print(analyze_sentiment([Headline('Bitcoin ETF approved massive inflow', 'test')]))"
# Expected composite: > 0.5
```

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 6: Multi-Timeframe Confluence Heatmap

**Priority:** 🟡 MEDIUM — The "at a glance" decision tool.
**Estimated Time:** 2–3 hours
**Files:** `intelligence/confluence.py` [NEW], `engine.py`, `scripts/pid-129/generate_dashboard.py`, `app.py`
**Depends on:** Phases 1–5 (uses all intelligence signals)
**API Cost:** $0

### Background

A visual grid showing alignment across timeframes and intelligence layers. Green = aligned, Red = conflicting, Yellow = neutral.

### Tasks

#### 6.1 — Create `intelligence/confluence.py`
- [ ] Create `intelligence/confluence.py`.
- [ ] Implement `build_confluence_grid(scores_by_tf)`:
  - Takes `Dict[str, AlertScore]` (timeframe → AlertScore).
  - Builds grid: `{layer: {tf: {"signal": "BULL"|"BEAR"|"NEUTRAL", "strength": float}}}`.
  - Normalizes each `score_breakdown` dimension to -1.0 → +1.0.
  - Computes `consensus_pct = green_cells / total_cells * 100`.
  - Generates one-line emoji summary for Telegram.
- [ ] Returns: `{"grid": dict, "consensus_pct": int, "summary": str}`.

#### 6.2 — Integrate into `app.py`
- [ ] After computing all `AlertScore`s across timeframes, call `build_confluence_grid()`.
- [ ] Store `consensus_pct` and `summary` in each AlertScore's `context`.

#### 6.3 — Add Heatmap to Dashboard HTML
- [ ] In `generate_dashboard.py`, render grid as color-coded HTML table.
- [ ] Colors: Green `#00ffcc`, Red `#ff4d4d`, Yellow `#ffd700`.

#### 6.4 — Include Summary in Telegram Alerts
- [ ] Append one-line summary to `_format_alert()`.

#### 6.5 — Add Tests
- [ ] Create `tests/test_confluence.py`:
  - Test all-bullish → 100% consensus.
  - Test mixed → partial consensus.
  - Test all-bearish → 0%.
  - Test single timeframe.

### Success Criteria
- [ ] Dashboard shows heatmap. Telegram gets one-line summary.
- [ ] Test: `PYTHONPATH=. python -m pytest tests/test_confluence.py -v`

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 7: Smart Alert Enrichment & Dashboard Upgrade

**Priority:** 🟢 LOW-MED — Presentation polish.
**Estimated Time:** 2–3 hours
**Files:** `app.py`, `scripts/pid-129/generate_dashboard.py`, `scripts/pid-129/generate_scorecard.py`
**Depends on:** Phases 1–6
**API Cost:** $0

### Tasks

#### 7.1 — Enrich Telegram Alert Format
- [ ] Update `_format_alert()` to show intelligence summary conditionally:
  ```
  🧠 Intelligence:
  ├ Squeeze: 🔥 FIRE
  ├ POC: $67,500 (ABOVE_VALUE)
  ├ Liquidity: Sell wall @ $68,500 (0.3%)
  ├ Macro: DXY ↑ HEADWIND | Gold ↓
  ├ Sentiment: -0.35 (70% bearish)
  └ Confluence: 78% aligned
  ```
- [ ] Only show layers that have data (skip None/missing).

#### 7.2 — Add Intelligence Cards to Dashboard
- [ ] Squeeze status, POC level, Macro pulse, Sentiment gauge per timeframe.

#### 7.3 — Persist Intelligence in Alert Logs
- [ ] In `PersistentLogger.log_alert()`, save `record["intelligence"]` from `score.context`.
- [ ] Use `.get()` everywhere for backward compatibility with old records.

#### 7.4 — Update Scorecard with Layer Performance
- [ ] Report win rate per intelligence code (e.g., "SQUEEZE_FIRE: 75% win rate").
- [ ] Handle missing `intelligence` key in old records.

#### 7.5 — Dashboard CSS Polish + Mobile Responsive
- [ ] Smooth transitions, collapsible sections, mobile grid.

#### 7.6 — Update README.md
- [ ] Document all layers, feature flags, quick start guide.

### Success Criteria
- [ ] Enriched Telegram alerts. Dashboard cards. Historical persistence. Updated README.

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 8: Score Recalibration & Threshold Tuning

**Priority:** 🔴 HIGH — Without this, alerts fire at wrong rates.
**Estimated Time:** 1–2 hours
**Files:** `config.py`, `engine.py`
**Depends on:** Phases 1–7
**API Cost:** $0

### Background

v2.0 had ~±50 pts max range. v3.0 adds up to ±24 more (squeeze +8, POC ±3, liquidity ±3, macro ±5, sentiment ±4). Existing `TIMEFRAME_RULES` thresholds need adjustment.

### Tasks

#### 8.1 — Document Score Contribution Budget
- [ ] Create table of ALL point sources with max +/- contributions.
- [ ] v2.0 theoretical: max ~+58, min ~-62.
- [ ] v3.0 adds: max +23, min -15. New total: max ~+81, min ~-77.

#### 8.2 — Recalibrate TIMEFRAME_RULES Thresholds
- [ ] Scale thresholds up ~15% proportionally:
  ```python
  TIMEFRAME_RULES = {
      "5m":  {"min_rr": 1.35, "trade_long": 78, "trade_short": 22, "watch_long": 64, "watch_short": 36},
      "15m": {"min_rr": 1.25, "trade_long": 76, "trade_short": 24, "watch_long": 62, "watch_short": 38},
      "1h":  {"min_rr": 1.15, "trade_long": 72, "trade_short": 28, "watch_long": 60, "watch_short": 40},
  }
  ```
- [ ] Comment old values above for rollback reference.

#### 8.3 — Optional: Score Normalization
- [ ] If threshold tuning is insufficient, normalize raw score to fixed 0–100 range before threshold check.

#### 8.4 — Add Tests
- [ ] `tests/test_score_calibration.py`: max bullish > trade_long, max bearish < trade_short, neutral ≈ 50.

### Success Criteria
- [ ] Alert fire rate roughly matches v2.0 proportions. A+ still rare. NO-TRADE still for weak signals.

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 9: Historical Intelligence Backtest

**Priority:** 🟡 MEDIUM — Proves each layer works.
**Estimated Time:** 3–4 hours
**Files:** `tools/intelligence_backtest.py` [NEW], `tools/collect_historical.py` [NEW]
**Depends on:** Phases 1–8
**API Cost:** $0

### Tasks

#### 9.1 — Create `tools/collect_historical.py`
- [ ] Fetch 7 days of 5m/15m/1h candles from Kraken. Save to `data/historical/` as JSON.
- [ ] Respect rate limits. Run once, not every cycle.

#### 9.2 — Create `tools/intelligence_backtest.py`
- [ ] Replay historical candles through `compute_score()` with and without `IntelligenceBundle`.
- [ ] Track outcomes: win rate, average R:R, alert count.
- [ ] Generate comparison report in `reports/intelligence_impact.md`.

#### 9.3 — Per-Layer Ablation
- [ ] Run backtest with each layer individually disabled via `INTELLIGENCE_FLAGS`.
- [ ] Report per-layer contribution to overall performance.

#### 9.4 — Tests
- [ ] `tests/test_backtest.py`: synthetic history, report generation, ablation logic.

### Success Criteria
- [ ] Report shows v3.0 ≥ v2.0 performance (or identifies non-contributing layers).

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 10: Error Handling & Circuit Breakers

**Priority:** 🔴 HIGH — One layer failure must never crash the system.
**Estimated Time:** 2 hours
**Files:** `intelligence/__init__.py`, `app.py`, `engine.py`
**Depends on:** Phase 0
**API Cost:** $0

### Tasks

#### 10.1 — Create `_collect_intelligence()` Orchestrator
- [ ] In `app.py`, single function with per-layer `try/except`.
- [ ] Returns `IntelligenceBundle` with whatever succeeded.
- [ ] Logs `degraded_layers` list.

#### 10.2 — Implement `CircuitBreaker` Class
- [ ] In `intelligence/__init__.py`:
  - Track per-layer consecutive failure count.
  - Trip after 3 failures → skip layer for 10 cycles.
  - Auto-reset after cooldown.
- [ ] Methods: `should_skip(layer)`, `record_failure(layer)`, `record_success(layer)`, `tick()`.

#### 10.3 — Guard `compute_score()` Intel Blocks
- [ ] Wrap each `# --- Intelligence Layer ---` block in `try/except`.

#### 10.4 — Tests
- [ ] `tests/test_circuit_breaker.py`:
  - One layer fails, others continue.
  - Breaker trips after N failures.
  - Breaker resets after cooldown.
  - `compute_score()` with partial `IntelligenceBundle`.

### Success Criteria
- [ ] System runs complete cycle even when 1+ layers fail. Breaker disables chronic failures.

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Phase 11: Observability & Structured Logging

**Priority:** 🟢 LOW-MED — Enables production debugging.
**Estimated Time:** 1–2 hours
**Files:** `intelligence/*.py`, `app.py`, `config.py`
**Depends on:** Phases 1–5
**API Cost:** $0

### Tasks

#### 11.1 — Add `logger.debug()` to Each Intelligence Module
- [ ] Each module gets a named logger (`intel.squeeze`, `intel.volume_profile`, etc.).
- [ ] Log raw input values and computed result.

#### 11.2 — Add Cycle Summary Log
- [ ] `logger.info("Cycle intel summary", extra={...})` at end of each cycle.

#### 11.3 — Add `DEBUG_INTELLIGENCE` Config Flag
- [ ] In `config.py`: `DEBUG_INTELLIGENCE = False`.
- [ ] Gate verbose logging behind this flag.

### Success Criteria
- [ ] Every layer has at least one debug log with raw values. Cycle summary in one line.

### Evidence
_(Mark items with ✅ and timestamp when complete)_

---

## Execution Order & Dependencies

```
Phase 0: Infrastructure ─────────────────────────┐  (MUST BE FIRST)
                                                   │
Phase 1: Squeeze ──────────────┐                   │
Phase 2: Volume Profile ───────┤  (all need P0)    │
Phase 3: Liquidity Walls ──────┤  CAN PARALLELIZE  │
Phase 4: Macro Correlation ────┤                    │
Phase 5: AI Sentiment ─────────┘                    │
                                                    │
Phase 10: Error Handling ──────── (can start after P0, recommended before P6)
Phase 11: Observability ───────── (can start after P0)
                                                    │
Phase 6: Confluence Heatmap ────── (needs P1–P5)    │
Phase 7: Alert Enrichment ─────── (needs P1–P6)     │
Phase 8: Score Recalibration ───── (needs P1–P7)    │
Phase 9: Historical Backtest ───── (needs ALL)      │
```

**Total:** 30–40 hours. **Pace:** 1 phase/session. **Target:** ~3 weeks.

---

## New Dependencies (v3.0)

| Package | Version | Purpose | Phase |
|:--------|:--------|:--------|:------|
| `vaderSentiment` | >=3.3 | Local NLP sentiment | Phase 5 |

All other features use existing `httpx`, `json`, `math`, `dataclasses` and free APIs.

---

## Risk Register

| # | Risk | Impact | Mitigation |
|:--|:-----|:-------|:-----------|
| 1 | Yahoo rate-limits DXY/Gold | MED | 5-min polling, cache, share fetcher |
| 2 | VADER misreads crypto slang | LOW | 30+ term extended lexicon + keyword fallback |
| 3 | Order book staleness (5-min) | LOW | Context only, never primary driver |
| 4 | Squeeze false positives | MED | Require ≥1 other layer via confluence |
| 5 | Score inflation | HIGH | Phase 8 recalibration + point budget doc |
| 6 | Old logs lack `intelligence` | MED | All reads use `.get()` with defaults |
| 7 | `compute_score()` merge conflicts | HIGH | Isolated `# --- Intel Layer ---` blocks |
| 8 | Single layer crash | HIGH | Phase 10 circuit breakers |
| 9 | `BudgetManager` yahoo=0 | HIGH | Fixed in Phase 0 → yahoo=(10, 300) |
| 10 | `AlertScore` missing `context` | HIGH | Fixed in Phase 0 |
| 11 | VADER init latency | LOW | Lazy singleton `get_engine()` |
| 12 | VP POC irrelevant in trends | LOW | Lower weight when regime=TREND |
| 13 | Alert clutter | MED | Conditional display, collapsible sections |

---

## Quick Reference Commands

```bash
# Full system (single cycle)
PYTHONPATH=. python app.py --once

# Continuous
./run.sh

# All tests
PYTHONPATH=. python -m pytest tests/ -v

# Per-phase tests
PYTHONPATH=. python -m pytest tests/test_preconditions.py -v    # P0
PYTHONPATH=. python -m pytest tests/test_squeeze.py -v          # P1
PYTHONPATH=. python -m pytest tests/test_volume_profile.py -v   # P2
PYTHONPATH=. python -m pytest tests/test_liquidity.py -v        # P3
PYTHONPATH=. python -m pytest tests/test_macro.py -v            # P4
PYTHONPATH=. python -m pytest tests/test_sentiment.py -v        # P5
PYTHONPATH=. python -m pytest tests/test_confluence.py -v       # P6
PYTHONPATH=. python -m pytest tests/test_score_calibration.py   # P8
PYTHONPATH=. python -m pytest tests/test_backtest.py -v         # P9
PYTHONPATH=. python -m pytest tests/test_circuit_breaker.py -v  # P10

# Dashboard + scorecard
python scripts/pid-129/generate_dashboard.py
python scripts/pid-129/generate_scorecard.py

# Smoke tests
python tools/paper_trader.py status
python -c "from intelligence.sentiment import analyze_sentiment; from collectors.social import Headline; print(analyze_sentiment([Headline('Bitcoin ETF approved', 'test')]))"
python -c "from collectors.orderbook import fetch_orderbook; from collectors.base import BudgetManager; print(fetch_orderbook(BudgetManager(), 68000))"
python tools/intelligence_backtest.py
```

---

## Definition of Done (v3.0)

- [ ] `AlertScore` has `context` field populated by all intelligence layers.
- [ ] `IntelligenceBundle` carries data between collectors and engine.
- [ ] Squeeze detector fires during volatility compression releases.
- [ ] Volume Profile POC calculated and displayed.
- [ ] Liquidity walls fetched and flag dangerous positions.
- [ ] DXY/Gold correlation context in alerts.
- [ ] AI sentiment replaces keyword matching (with fallback).
- [ ] Confluence heatmap on dashboard.
- [ ] Telegram alerts show formatted intelligence summary.
- [ ] Intelligence data persisted for historical analysis.
- [ ] Scorecard reports intelligence layer performance.
- [ ] Score thresholds recalibrated for new point range.
- [ ] Backtest proves v3.0 ≥ v2.0 performance.
- [ ] Every layer has error handling (no single-point-of-failure).
- [ ] Every layer has structured debug logging.
- [ ] Feature flags enable/disable each layer independently.
- [ ] All tests pass: `PYTHONPATH=. python -m pytest tests/ -v`
- [ ] README updated with v3.0 docs.
- [ ] BudgetManager Yahoo limit fixed (10, not 0).
- [ ] Zero paid APIs — all free tier.

---

_Single source of truth for v3.0 development._
_Update checkboxes as tasks complete._
_Last updated: 2026-02-18T08:48:00-05:00_
