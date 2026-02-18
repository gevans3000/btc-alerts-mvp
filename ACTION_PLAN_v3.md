# ACTION PLAN v3.0 — EMBER APEX

> **Goal:** Production-grade BTC alert system with 7 intelligence layers, error handling, observability, and backtesting.
> **Constraint:** Zero paid APIs. All free-tier or local computation.
> **Created:** 2026-02-18 | **Pace:** 1 phase per session.

---

## Progress Tracker

| Phase | Name | Status | Depends On |
|:------|:-----|:-------|:-----------|
| 0 | Infrastructure Preconditions | ✅ DONE | — |
| 1 | Squeeze Detector | 🟡 PARTIAL (core done, wiring/tests remain) | P0 |
| 2 | Volume Profile / POC | 🟡 PARTIAL (needs alignment) | P0 |
| 3 | Liquidity Walls | 🟡 PARTIAL (collector/intel done, integration missing) | P0 |
| 4 | Macro Correlation Pulse | 🔴 TODO | P0 |
| 5 | AI Sentiment Engine | 🔴 TODO | P0 |
| 6 | Confluence Heatmap | 🔴 TODO | P1–P5 |
| 7 | Alert Enrichment & Dashboard | 🔴 TODO | P1–P6 |
| 8 | Score Recalibration | 🔴 TODO | P1–P7 |
| 9 | Historical Backtest | 🔴 TODO | ALL |
| 10 | Error Handling & Circuit Breakers | 🔴 TODO | P0 |
| 11 | Observability & Logging | 🔴 TODO | P0 |

### Known Issues
- `PermissionError: [WinError 5]` in `tests/test_performance_loop.py` — Windows `tmp_path` issue, unrelated to v3.0 changes.

---

## What v3.0 Adds

| # | Layer | Purpose | Cost |
|:--|:------|:--------|:-----|
| 1 | Squeeze Detector | Identifies volatility compression → explosive moves imminent | $0 (local) |
| 2 | Volume Profile / POC | Shows fair value — is entry cheap or expensive? | $0 (local) |
| 3 | Liquidity Walls | Reveals hidden buy/sell walls that can trap positions | $0 (Kraken/Bybit free REST) |
| 4 | Macro Correlation | Warns when DXY/Gold fight your BTC trade | $0 (Yahoo Finance) |
| 5 | AI Sentiment | 50 headlines → one actionable sentiment score | $0 (VADER, local) |
| 6 | Confluence Heatmap | Visual grid: alignment across all timeframes | $0 (local) |
| 7–11 | Infrastructure | Rich alerts, score tuning, backtest, error handling, logging | $0 |

### Free API Budget

| Source | Rate Limit | v2 Usage | v3 Usage | OK? |
|:-------|:-----------|:---------|:---------|:----|
| Kraken | 15/min | ~4 | ~5 (+orderbook) | ✅ |
| Bybit | 120/min | ~5 | ~6 (+orderbook fallback) | ✅ |
| Yahoo Finance | ~2000/day | ~2 | ~4 (+DXY, Gold) | ✅ |
| CoinGecko | 10-30/min | 1 | 1 | ✅ |
| Alternative.me | ~500/day | 1 | 1 | ✅ |
| RSS Feeds | Unlimited | 2 | 2 | ✅ |
| OKX | 20/2s | ~3 | ~3 | ✅ |

---

## Architecture

### v2.0 (Current)

```
DATA LAYER                    ENGINE LAYER                   ACTION LAYER
─────────────                 ────────────                   ────────────
Kraken  ─┐                    engine.py                      app.py
Bybit   ─┼→ price.py → OHLCV ├ _regime()                    ├ PersistentLogger
Yahoo   ─┘   derivatives.py   ├ _detector_candidates()       ├ Notifier (Telegram)
             flows.py         ├ _arbitrate_candidates()      ├ AlertStateStore
             social.py        ├ _session_label()              ├ Portfolio (paper)
                              ├ _trend_bias()                 └ _format_alert()
                              └ compute_score() → AlertScore
                                                             tools/
                                                             ├ paper_trader.py
                                                             ├ outcome_tracker.py
                                                             ├ run_backtest.py
                                                             └ replay.py
```

### v3.0 (Target) — adds `intelligence/` layer between data and engine

```
DATA LAYER (expanded)         INTELLIGENCE LAYER (NEW)       ENGINE (updated)
─────────────────────         ──────────────────────────     ────────────────
[NEW] orderbook.py            intelligence/                  compute_score(
[UPD] price.py (+DXY,Gold)    ├ __init__.py (Bundle)           ..., intel=Bundle)
      social.py + sentiment   ├ squeeze.py                  AlertScore.context={}
                              ├ volume_profile.py
                              ├ liquidity.py                 ACTION (enhanced)
                              ├ macro.py                     ────────────────────
                              ├ sentiment.py                 _collect_intelligence()
                              └ confluence.py                _format_alert() (rich)
                                                             Dashboard (heatmap)
```

---

## Phase 0: Infrastructure Preconditions ✅ DONE

> Fixed all structural gaps blocking intelligence phases.

**Files:** `engine.py`, `config.py`, `collectors/base.py`, `intelligence/__init__.py`

### What was done
- [x] **0.1** — Added `context: Dict[str, object]` to `AlertScore` dataclass
- [x] **0.2** — Created `intelligence/__init__.py` with `IntelligenceBundle` dataclass (all Optional fields)
- [x] **0.3** — Added `intel: Optional[IntelligenceBundle] = None` param to `compute_score()`
- [x] **0.4** — Fixed `BudgetManager.LIMITS["yahoo"]` from `(0, 300)` → `(10, 300)`
- [x] **0.5** — Added `INTELLIGENCE_FLAGS` dict to `config.py` (all default `True`)
- [x] **0.6** — Tests in `tests/test_preconditions.py` — all passing

```bash
# Verified
PYTHONPATH=. python -m pytest tests/test_preconditions.py -v  # PASSED
PYTHONPATH=. python -m pytest tests/test_volume.py -v          # PASSED
```

---

## Phase 1: Squeeze Detector — Volatility Compression

> **Concept:** TTM Squeeze (John Carter). BB contracts inside KC = coiled spring. Release = explosive move.
> - `SQUEEZE_ON` = BB inside KC (coiling)
> - `SQUEEZE_FIRE` = BB just expanded outside KC (move starts, +8 pts)
> - `NONE` = normal volatility

**Files:** `intelligence/squeeze.py`, `engine.py`, `config.py`, `app.py`
**Depends on:** P0 | **Cost:** $0

### Tasks

#### 1.1 — Create `intelligence/squeeze.py`
- [x] `keltner_channels(candles, period=20, atr_mult=1.5)` → `(upper, middle, lower)`
- [x] `detect_squeeze(candles)` → `{"state": "SQUEEZE_ON"|"SQUEEZE_FIRE"|"NONE", "pts": int, "bb_width": float, "kc_width": float}`

```python
def keltner_channels(candles, period=20, atr_mult=1.5):
    if len(candles) < period:
        return None
    closes = [c.close for c in candles[-period:]]
    middle = sum(closes) / len(closes)
    atr_val = atr(candles, period)
    if atr_val is None:
        return None
    return (middle + atr_mult * atr_val, middle, middle - atr_mult * atr_val)

def detect_squeeze(candles):
    if len(candles) < 22:
        return {"state": "NONE", "pts": 0, "bb_width": 0.0, "kc_width": 0.0}

    closes = [c.close for c in candles]
    bb = bollinger_bands(closes, period=20, multiplier=2.0)
    kc = keltner_channels(candles, period=20, atr_mult=1.5)
    if bb is None or kc is None:
        return {"state": "NONE", "pts": 0, "bb_width": 0.0, "kc_width": 0.0}

    squeeze_on = bb[2] > kc[2] and bb[0] < kc[0]  # BB inside KC

    # Check previous bar for FIRE detection
    prev_bb = bollinger_bands(closes[:-1], period=20, multiplier=2.0)
    prev_kc = keltner_channels(candles[:-1], period=20, atr_mult=1.5)
    was_squeeze = prev_bb and prev_kc and prev_bb[2] > prev_kc[2] and prev_bb[0] < prev_kc[0]
    squeeze_fire = was_squeeze and not squeeze_on

    bb_width = bb[0] - bb[2]
    kc_width = kc[0] - kc[2]

    if squeeze_fire:
        return {"state": "SQUEEZE_FIRE", "pts": 8, "bb_width": bb_width, "kc_width": kc_width}
    elif squeeze_on:
        return {"state": "SQUEEZE_ON", "pts": 0, "bb_width": bb_width, "kc_width": kc_width}
    else:
        return {"state": "NONE", "pts": 0, "bb_width": bb_width, "kc_width": kc_width}
```

#### 1.2 — Integrate into `compute_score()` in `engine.py`
- [x] Added `# --- Intelligence Layer: Squeeze ---` block

```python
if intel and intel.squeeze and INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
    sq = intel.squeeze
    if sq["state"] == "SQUEEZE_FIRE":
        breakdown["volatility"] += sq["pts"]
        codes.append("SQUEEZE_FIRE")
    elif sq["state"] == "SQUEEZE_ON":
        codes.append("SQUEEZE_ON")
    score_obj.context["squeeze"] = sq["state"]
```

#### 1.3 — Wire up in `app.py` (TODO)
- [x] P1.3: Wire up Squeeze Detector in app.py I AM HERE
```python
from intelligence.squeeze import detect_squeeze
from intelligence import IntelligenceBundle

intel = IntelligenceBundle()
if INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
    intel.squeeze = detect_squeeze(candles)
# pass intel=intel to compute_score()
```

#### 1.4 — Config tunables (TODO)
- [x] Add `SQUEEZE` dict to `config.py`: I AM HERE
```python
SQUEEZE = {"bb_period": 20, "bb_std": 2.0, "kc_period": 20, "kc_atr_mult": 1.5, "fire_bonus_pts": 8}
```

#### 1.5 — Tests (TODO)
- [x] P1.5: Create tests for Squeeze Detector (tests/test_squeeze.py) I AM HERE
  - BB inside KC → `SQUEEZE_ON`
  - Squeeze just released → `SQUEEZE_FIRE`
  - Normal volatility → `NONE`
  - < 22 candles → graceful `NONE`
  - Correct dict keys

```bash
PYTHONPATH=. python -m pytest tests/test_squeeze.py -v
```

---

## Phase 2: Volume Profile & Point of Control (POC)

> **Concept:** Volume traded at each price level. POC = price with highest volume (magnet).
> - Entry below POC = buying cheap (good for longs, +3 pts)
> - Entry above POC = buying expensive (risky for longs, -3 pts)
> - Value Area = 70% of volume = "fair value"

**Files:** `intelligence/volume_profile.py`, `engine.py`, `config.py`, `app.py`
**Depends on:** P0 | **Cost:** $0

### Tasks

#### 2.1 — Create `intelligence/volume_profile.py`
- [x] `compute_volume_profile(candles, current_price, num_bins=50)` → I AM HERE
  `{"poc": float, "va_high": float, "va_low": float, "position": str, "pts": float}`

```python
def compute_volume_profile(candles, current_price, num_bins=50):
    if len(candles) < 5:
        return {"poc": 0.0, "va_high": 0.0, "va_low": 0.0, "position": "UNKNOWN", "pts": 0.0}

    price_min = min(c.low for c in candles)
    price_max = max(c.high for c in candles)
    if price_max == price_min:
        return {"poc": price_min, "va_high": price_max, "va_low": price_min, "position": "AT_VALUE", "pts": 0.0}

    bin_size = (price_max - price_min) / num_bins
    bins = [0.0] * num_bins

    for c in candles:
        lo = max(0, min(int((c.low - price_min) / bin_size), num_bins - 1))
        hi = max(0, min(int((c.high - price_min) / bin_size), num_bins - 1))
        spread = max(hi - lo, 1)
        for b in range(lo, min(hi + 1, num_bins)):
            bins[b] += c.volume / spread

    # POC = bin with max volume
    poc_bin = bins.index(max(bins))
    poc_price = price_min + (poc_bin + 0.5) * bin_size

    # Value Area = 70% of total volume, expanding outward from POC
    total_vol = sum(bins)
    target_vol = total_vol * 0.70
    acc = bins[poc_bin]
    lo_idx, hi_idx = poc_bin, poc_bin
    while acc < target_vol and (lo_idx > 0 or hi_idx < num_bins - 1):
        down = bins[lo_idx - 1] if lo_idx > 0 else 0
        up = bins[hi_idx + 1] if hi_idx < num_bins - 1 else 0
        if down >= up and lo_idx > 0:
            lo_idx -= 1; acc += bins[lo_idx]
        elif hi_idx < num_bins - 1:
            hi_idx += 1; acc += bins[hi_idx]
        else:
            lo_idx -= 1; acc += bins[lo_idx]

    va_low = price_min + lo_idx * bin_size
    va_high = price_min + (hi_idx + 1) * bin_size

    if current_price < va_low:
        position, pts = "BELOW_VALUE", 3.0
    elif current_price > va_high:
        position, pts = "ABOVE_VALUE", -3.0
    else:
        position, pts = "AT_VALUE", 0.0

    return {"poc": round(poc_price, 2), "va_high": round(va_high, 2),
            "va_low": round(va_low, 2), "position": position, "pts": pts}
```

#### 2.2 — Integrate into `compute_score()`
- [x] P2.2: Integrate Volume Profile into compute_score() in engine.py I AM HERE
- [ ] After squeeze block:
```python
# --- Intelligence Layer: Volume Profile ---
if intel and intel.volume_profile and INTELLIGENCE_FLAGS.get("volume_profile_enabled", True):
    vp = intel.volume_profile
    breakdown["volume"] += vp["pts"]
    codes.append(f"POC_{vp['position']}")
    score_obj.context["poc"] = vp["poc"]
    score_obj.context["value_area"] = vp["position"]
```

#### 2.3 — Wire up in `app.py`
- [x] After candle collection: I AM HERE
```python
from intelligence.volume_profile import compute_volume_profile
if INTELLIGENCE_FLAGS.get("volume_profile_enabled", True):
    intel.volume_profile = compute_volume_profile(candles, btc_price.price)
```

#### 2.4 — Config & Tests
- [x] P2.4: Add Volume Profile config and tests (tests/test_volume_profile.py) I AM HERE
- [ ] Create `tests/test_volume_profile.py`:
  - Uniform volume → POC at midpoint
  - Concentrated volume → tight VA
  - Position detection (below/above/at)
  - Single candle → graceful default

```bash
PYTHONPATH=. python -m pytest tests/test_volume_profile.py -v
```

---

## Phase 3: Liquidity Walls — Order Book Intelligence

> **Concept:** Large orders ("walls") block price movement. A sell wall above your long entry = trade will fail.
> - Imbalance > 0.3 → `IMBALANCE_BULL` (+3 pts)
> - Imbalance < -0.3 → `IMBALANCE_BEAR` (-3 pts)
> - Wall within 0.5% of entry → `LIQ_WALL_BLOCKER`

**Files:** `collectors/orderbook.py`, `intelligence/liquidity.py`, `engine.py`, `config.py`, `app.py`
**Depends on:** P0 | **Cost:** $0 (Kraken/Bybit free REST, ~1 req/5 min each)

### API Endpoints

| Exchange | Endpoint | Our Usage |
|:---------|:---------|:----------|
| Kraken | `/0/public/Depth?pair=XXBTZUSD&count=100` | 1 req/5 min |
| Bybit (fallback) | `/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=50` | 1 req/5 min |

### Tasks

#### 3.1 — Create `collectors/orderbook.py`
- [x] P3.1: Create collectors/orderbook.py with OrderBookSnapshot dataclass and fetch_orderbook, _detect_walls functions I AM HERE
- [ ] `OrderBookSnapshot` dataclass:
```python
@dataclass
class OrderBookSnapshot:
    bid_walls: List[Tuple[float, float]]     # [(price, size_usd), ...]
    ask_walls: List[Tuple[float, float]]
    bid_total_usd: float
    ask_total_usd: float
    imbalance: float                          # (bid - ask) / (bid + ask), range -1 to +1
    nearest_bid_wall: Optional[Tuple[float, float]] = None
    nearest_ask_wall: Optional[Tuple[float, float]] = None
    source: str = "none"
    healthy: bool = True
```
- [ ] `fetch_orderbook(budget, current_price)` — try Kraken, fallback Bybit
- [ ] `_detect_walls(levels, current_price, threshold_mult=2.0)` — flag levels > avg × mult

#### 3.2 — Create `intelligence/liquidity.py`
- [x] P3.2: Create intelligence/liquidity.py with analyze_liquidity function I AM HERE
- [ ] `analyze_liquidity(ob, direction, current_price)` →
  `{"imbalance": float, "nearest_wall": str, "wall_distance_pct": float, "blocker": bool, "bias": str, "pts": float}`

```python
def analyze_liquidity(ob, direction, current_price):
    if not ob.healthy:
        return {"imbalance": 0.0, "nearest_wall": "N/A", "wall_distance_pct": 0.0,
                "blocker": False, "bias": "NEUTRAL", "pts": 0.0}

    result = {"imbalance": round(ob.imbalance, 3), "blocker": False, "bias": "NEUTRAL", "pts": 0.0}

    # Check for blocking walls in trade direction
    if direction == "LONG" and ob.nearest_ask_wall:
        wall_price, wall_size = ob.nearest_ask_wall
        dist_pct = (wall_price - current_price) / current_price
        result["nearest_wall"] = f"${wall_price:,.0f} (sell, ${wall_size:,.0f})"
        result["wall_distance_pct"] = round(dist_pct * 100, 2)
        if dist_pct < 0.005:
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
        result["bias"], result["pts"] = "IMBALANCE_BULL", 3.0
    elif ob.imbalance < -0.3:
        result["bias"], result["pts"] = "IMBALANCE_BEAR", -3.0

    return result
```

#### 3.3 — Integrate into `compute_score()`
- [x] P3.3: Integrate Liquidity Walls into compute_score() in engine.py I AM HERE
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

#### 3.4 — Wire up in `app.py` ✅ DONE
- [ ] After price fetch:
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
- [ ] After direction is known (per-timeframe loop):
```python
if orderbook and orderbook.healthy:
    intel.liquidity = analyze_liquidity(orderbook, direction, btc_price.price)
```

#### 3.5 — Config & Tests
- [x] P3.5: Add Liquidity Walls config and tests (tests/test_liquidity.py) I AM HERE
- [ ] Add `LIQUIDITY = {"wall_threshold_mult": 2.0, "wall_danger_pct": 0.005, "imbalance_threshold": 0.3, "imbalance_pts": 3}` to `config.py`
- [ ] Create `tests/test_liquidity.py`:
  - Wall detection with synthetic orderbook
  - Imbalance: balanced, bullish, bearish
  - Blocker within danger zone
  - `healthy=False` → graceful default
  - Empty bid/ask lists

```bash
PYTHONPATH=. python -m pytest tests/test_liquidity.py -v
```

---

## Phase 4: Macro Correlation Pulse — DXY & Gold

> **Concept:** BTC doesn't move in isolation.
> - DXY UP + BTC LONG → HEADWIND (-3 pts)
> - DXY DOWN + BTC LONG → TAILWIND (+3 pts)
> - Gold UP + BTC UP → GOLD_CONFIRM (+2 pts)

**Files:** `collectors/price.py`, `intelligence/macro.py`, `engine.py`, `config.py`, `app.py`
**Depends on:** P0 (specifically 0.4 Yahoo budget fix) | **Cost:** $0 (Yahoo Finance, 2 calls/cycle)

### Yahoo Symbols

| Asset | Symbol | Interval |
|:------|:-------|:---------|
| DXY | `DX-Y.NYB` | 5m |
| Gold | `GC=F` | 5m |

### Tasks

#### 4.1 — Add DXY & Gold fetchers to `collectors/price.py`
- [x] P4.1: Add DXY & Gold fetchers to collectors/price.py I AM HERE
- [ ] `fetch_dxy_candles(budget, limit=30)` — uses `_fetch_yahoo_symbol_candles(budget, "DX-Y.NYB", "5m", "1d", limit)`
- [ ] `fetch_gold_candles(budget, limit=30)` — uses `_fetch_yahoo_symbol_candles(budget, "GC=F", "5m", "1d", limit)`
- [ ] `fetch_macro_assets(budget)` → `{"dxy": List[Candle], "gold": List[Candle]}` (with 1s throttle between calls)

#### 4.2 — Create `intelligence/macro.py`
- [x] P4.2: Create intelligence/macro.py with analyze_macro_correlation function I AM HERE
- [ ] `analyze_macro_correlation(dxy, gold, btc, direction)` →
  `{"dxy_bias": str, "gold_confirm": bool, "dxy_roc": float, "gold_roc": float, "pts": float}`

```python
def analyze_macro_correlation(dxy, gold, btc, direction):
    def _roc(candles, period=20):
        if len(candles) < period + 1:
            return 0.0
        return (candles[-1].close - candles[-period].close) / candles[-period].close

    dxy_roc = _roc(dxy)
    gold_roc = _roc(gold)
    result = {"dxy_bias": "NEUTRAL", "gold_confirm": False,
              "dxy_roc": round(dxy_roc, 5), "gold_roc": round(gold_roc, 5), "pts": 0.0}

    dxy_thresh = 0.002  # 0.2% move
    if direction == "LONG":
        if dxy_roc > dxy_thresh:
            result["dxy_bias"], result["pts"] = "HEADWIND", result["pts"] - 3.0
        elif dxy_roc < -dxy_thresh:
            result["dxy_bias"], result["pts"] = "TAILWIND", result["pts"] + 3.0
    elif direction == "SHORT":
        if dxy_roc > dxy_thresh:
            result["dxy_bias"], result["pts"] = "TAILWIND", result["pts"] + 3.0
        elif dxy_roc < -dxy_thresh:
            result["dxy_bias"], result["pts"] = "HEADWIND", result["pts"] - 3.0

    # Gold confirmation (positive correlation with BTC)
    if gold_roc > 0.003 and _roc(btc) > 0:
        result["gold_confirm"] = True
        result["pts"] += 2.0

    return result
```

#### 4.3 — Integrate into `compute_score()`
- [x] P4.3: Integrate Macro Correlation into compute_score() in engine.py I AM HERE
- [ ] After liquidity block:
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

#### 4.4 — Wire up in `app.py`
- [ ] After existing macro fetch:
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
- [ ] Per-timeframe loop (after direction known):
```python
if macro_assets["dxy"] or macro_assets["gold"]:
    intel.macro = analyze_macro_correlation(
        macro_assets["dxy"], macro_assets["gold"], candles, direction)
```

#### 4.5 — Config & Tests
- [ ] Add to `config.py`:
```python
MACRO_CORRELATION = {
    "roc_period": 20, "dxy_threshold": 0.002, "gold_threshold": 0.003,
    "headwind_penalty": -3, "tailwind_bonus": 3, "gold_confirm_bonus": 2,
}
```
- [ ] Create `tests/test_macro.py`:
  - DXY up + LONG → HEADWIND (negative)
  - DXY down + LONG → TAILWIND (positive)
  - Gold up + BTC up → GOLD_CONFIRM
  - SHORT direction (inverted DXY logic)
  - Empty candle lists → graceful defaults

```bash
PYTHONPATH=. python -m pytest tests/test_macro.py -v
```

---

## Phase 5: AI Sentiment Engine — Local NLP

> **Concept:** VADER scores each headline -1 to +1, with a crypto-specific extended lexicon.
> - Composite > 0.3 → `SENTIMENT_BULL` (+4 pts)
> - Composite < -0.3 → `SENTIMENT_BEAR` (-4 pts)
> - Keeps existing `NEWS_DICT` keyword logic as fallback.

**Files:** `intelligence/sentiment.py`, `engine.py`, `config.py`, `requirements.txt`, `app.py`
**Depends on:** P0 | **Cost:** $0 (VADER runs 100% locally)
**New dependency:** `vaderSentiment>=3.3`

### Why VADER?

| | VADER | OpenAI | Local LLM |
|:--|:------|:-------|:----------|
| Cost | Free | $$$ | Free but slow |
| Speed | <1ms/headline | 500ms/call | 2-5s/call |
| Privacy | Local | Cloud | Local |
| Deps | 1 pip package | API key | 4GB+ model |

### Tasks

#### 5.1 — Install dependency
- [ ] Add `vaderSentiment>=3.3` to `requirements.txt`
- [ ] `python -m pip install vaderSentiment`

#### 5.2 — Create `intelligence/sentiment.py`
- [ ] Singleton `SentimentEngine` with crypto-extended lexicon (30+ terms)
- [ ] `analyze_sentiment(headlines)` → `{"composite": float, "bullish_pct": int, "bearish_pct": int, "count": int, "fallback": bool}`

```python
_engine_instance = None

class SentimentEngine:
    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        self.analyzer = SentimentIntensityAnalyzer()
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

    def score_headline(self, text):
        return self.analyzer.polarity_scores(text)["compound"]

    def score_batch(self, headlines):
        scores = [self.score_headline(h.title if hasattr(h, 'title') else str(h))
                  for h in headlines[:50]]
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

def get_engine():
    global _engine_instance
    if _engine_instance is None:
        try:
            _engine_instance = SentimentEngine()
        except ImportError:
            return None
    return _engine_instance

def analyze_sentiment(headlines):
    engine = get_engine()
    if engine is None:
        return {"composite": 0.0, "bullish_pct": 0, "bearish_pct": 0,
                "count": 0, "fallback": True}
    result = engine.score_batch(headlines)
    result["fallback"] = False
    return result
```

#### 5.3 — Integrate into `compute_score()`
- [ ] After macro block:
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
            "score": sent["composite"], "bull_pct": sent["bullish_pct"], "bear_pct": sent["bearish_pct"]}
```
- [ ] **Keep existing `NEWS_DICT`** keyword logic as fallback.

#### 5.4 — Wire up in `app.py`
- [ ] After news collection:
```python
from intelligence.sentiment import analyze_sentiment
if INTELLIGENCE_FLAGS.get("sentiment_enabled", True) and news:
    intel.sentiment = analyze_sentiment(news)
```

#### 5.5 — Config & Tests
- [ ] Add to `config.py`:
```python
SENTIMENT = {"strong_threshold": 0.3, "weak_threshold": 0.05,
             "bull_pts": 4, "bear_pts": -4, "max_headlines": 50}
```
- [ ] Create `tests/test_sentiment.py`:
  - Bullish headline → positive score
  - Bearish headline → negative score
  - Crypto terms ("BTC ETF approved") → strongly positive
  - Mixed headlines → near-neutral
  - Empty list → graceful default
  - VADER not installed (mock ImportError) → fallback
  - Singleton pattern works

```bash
python -m pip install vaderSentiment
PYTHONPATH=. python -m pytest tests/test_sentiment.py -v
# Smoke test:
python -c "from intelligence.sentiment import analyze_sentiment; from collectors.social import Headline; print(analyze_sentiment([Headline('Bitcoin ETF approved massive inflow', 'test')]))"
```

---

## Phase 6: Multi-Timeframe Confluence Heatmap

> **Concept:** Visual grid showing alignment across timeframes × intelligence layers.
> Green = aligned, Red = conflicting, Yellow = neutral. One-line emoji summary for Telegram.

**Files:** `intelligence/confluence.py`, `engine.py`, `app.py`, `scripts/pid-129/generate_dashboard.py`
**Depends on:** P1–P5 | **Cost:** $0

### Tasks

- [ ] **6.1** — Create `intelligence/confluence.py` with `build_confluence_grid(scores_by_tf)`:
  - Takes `Dict[str, AlertScore]`
  - Builds grid: `{layer: {tf: {"signal": "BULL"|"BEAR"|"NEUTRAL", "strength": float}}}`
  - Normalizes each `score_breakdown` dimension to -1.0 → +1.0
  - Computes `consensus_pct = green_cells / total_cells * 100`
  - Returns `{"grid": dict, "consensus_pct": int, "summary": str}`
- [ ] **6.2** — Integrate: after computing all AlertScores across TFs, call `build_confluence_grid()`, store in `context`
- [ ] **6.3** — Dashboard: render grid as color-coded HTML table (#00ffcc / #ff4d4d / #ffd700)
- [ ] **6.4** — Telegram: append one-line summary to `_format_alert()`
- [ ] **6.5** — Tests in `tests/test_confluence.py`:
  - All bullish → 100% consensus
  - Mixed → partial
  - All bearish → 0%
  - Single timeframe

```bash
PYTHONPATH=. python -m pytest tests/test_confluence.py -v
```

---

## Phase 7: Smart Alert Enrichment & Dashboard Upgrade

> Presentation polish — make intelligence visible to the user.

**Files:** `app.py`, `scripts/pid-129/generate_dashboard.py`, `scripts/pid-129/generate_scorecard.py`
**Depends on:** P1–P6 | **Cost:** $0

### Tasks

- [ ] **7.1** — Enrich `_format_alert()` with conditional intelligence block:
  ```
  🧠 Intelligence:
  ├ Squeeze: 🔥 FIRE
  ├ POC: $67,500 (ABOVE_VALUE)
  ├ Liquidity: Sell wall @ $68,500 (0.3%)
  ├ Macro: DXY ↑ HEADWIND | Gold ↓
  ├ Sentiment: -0.35 (70% bearish)
  └ Confluence: 78% aligned
  ```
  Only show layers that have data (skip None/missing).
- [ ] **7.2** — Dashboard cards: Squeeze status, POC level, Macro pulse, Sentiment gauge per TF
- [ ] **7.3** — Persist intelligence in `PersistentLogger.log_alert()` — save `record["intelligence"]` from `score.context`, use `.get()` for backward compat
- [ ] **7.4** — Scorecard: win rate per intelligence code (e.g. "SQUEEZE_FIRE: 75% win rate"), handle missing `intelligence` key
- [ ] **7.5** — CSS polish: smooth transitions, collapsible sections, mobile responsive grid
- [ ] **7.6** — Update README.md with all layers, feature flags, quick start guide

---

## Phase 8: Score Recalibration & Threshold Tuning

> v2.0 had ~±50 pts max. v3.0 adds up to ±24 more. Thresholds must adjust.

**Files:** `config.py`, `engine.py`
**Depends on:** P1–P7 | **Cost:** $0

### Point Budget

| Source | Max + | Max - |
|:-------|:------|:------|
| v2.0 existing | ~+58 | ~-62 |
| Squeeze | +8 | 0 |
| Volume Profile | +3 | -3 |
| Liquidity | +3 | -3 |
| Macro (DXY+Gold) | +5 | -3 |
| Sentiment | +4 | -4 |
| **v3.0 total** | **~+81** | **~-77** |

### Tasks

- [ ] **8.1** — Document all point sources with max +/- contributions
- [ ] **8.2** — Scale `TIMEFRAME_RULES` thresholds up ~15%:
  ```python
  TIMEFRAME_RULES = {
      "5m":  {"min_rr": 1.35, "trade_long": 78, "trade_short": 22, "watch_long": 64, "watch_short": 36},
      "15m": {"min_rr": 1.25, "trade_long": 76, "trade_short": 24, "watch_long": 62, "watch_short": 38},
      "1h":  {"min_rr": 1.15, "trade_long": 72, "trade_short": 28, "watch_long": 60, "watch_short": 40},
  }
  ```
  Comment old values above for rollback.
- [ ] **8.3** — Optional: normalize raw score to fixed 0–100 range before threshold check
- [ ] **8.4** — Tests in `tests/test_score_calibration.py`: max bullish > trade_long, max bearish < trade_short, neutral ≈ 50

---

## Phase 9: Historical Intelligence Backtest

> Prove each layer improves outcomes with historical data.

**Files:** `tools/intelligence_backtest.py`, `tools/collect_historical.py`
**Depends on:** ALL | **Cost:** $0

### Tasks

- [ ] **9.1** — Create `tools/collect_historical.py`: fetch 7d of 5m/15m/1h candles from Kraken, save to `data/historical/` as JSON. Respect rate limits. Run once.
- [ ] **9.2** — Create `tools/intelligence_backtest.py`: replay candles through `compute_score()` with/without `IntelligenceBundle`. Track win rate, avg R:R, alert count. Generate `reports/intelligence_impact.md`.
- [ ] **9.3** — Per-layer ablation: run backtest with each layer individually disabled via `INTELLIGENCE_FLAGS`. Report per-layer contribution.
- [ ] **9.4** — Tests in `tests/test_backtest.py`: synthetic history, report generation, ablation logic.

**Success:** Report shows v3.0 ≥ v2.0 performance (or identifies non-contributing layers for removal).

---

## Phase 10: Error Handling & Circuit Breakers

> One layer failure must NEVER crash the system.

**Files:** `intelligence/__init__.py`, `app.py`, `engine.py`
**Depends on:** P0 | **Cost:** $0

### Tasks

- [ ] **10.1** — Create `_collect_intelligence()` in `app.py`: single orchestrator with per-layer `try/except`, returns `IntelligenceBundle` with whatever succeeded, logs `degraded_layers` list
- [ ] **10.2** — `CircuitBreaker` class in `intelligence/__init__.py`:
  - Track per-layer consecutive failure count
  - Trip after 3 failures → skip layer for 10 cycles
  - Auto-reset after cooldown
  - Methods: `should_skip(layer)`, `record_failure(layer)`, `record_success(layer)`, `tick()`
- [ ] **10.3** — Wrap each `# --- Intelligence Layer ---` block in `compute_score()` with `try/except`
- [ ] **10.4** — Tests in `tests/test_circuit_breaker.py`:
  - One layer fails, others continue
  - Breaker trips after N failures
  - Breaker resets after cooldown
  - `compute_score()` with partial `IntelligenceBundle`

---

## Phase 11: Observability & Structured Logging

> Enables production debugging.

**Files:** `intelligence/*.py`, `app.py`, `config.py`
**Depends on:** P0 | **Cost:** $0

### Tasks

- [ ] **11.1** — Each intelligence module gets a named logger (`intel.squeeze`, `intel.volume_profile`, etc.). Log raw input values and computed result.
- [ ] **11.2** — Cycle summary: `logger.info("Cycle intel summary", extra={...})` at end of each cycle
- [ ] **11.3** — `DEBUG_INTELLIGENCE = False` in `config.py` — gate verbose logging behind this flag

---

## Execution Order

```
Phase 0: Infrastructure ──────────────────────────────┐  MUST BE FIRST (✅ DONE)
                                                       │
Phase 1: Squeeze ──────────────┐                       │
Phase 2: Volume Profile ───────┤  All need P0          │
Phase 3: Liquidity Walls ──────┤  CAN RUN IN PARALLEL  │
Phase 4: Macro Correlation ────┤                       │
Phase 5: AI Sentiment ─────────┘                       │
                                                       │
Phase 10: Error Handling ──────── (can start after P0, recommended before P6)
Phase 11: Observability ───────── (can start after P0)
                                                       │
Phase 6: Confluence Heatmap ────── (needs P1–P5)       │
Phase 7: Alert Enrichment ─────── (needs P1–P6)        │
Phase 8: Score Recalibration ───── (needs P1–P7)       │
Phase 9: Historical Backtest ───── (needs ALL)         │
```

---

## Dependencies

| Package | Version | Purpose | Phase |
|:--------|:--------|:--------|:------|
| `vaderSentiment` | >=3.3 | Local NLP sentiment | P5 |

Everything else uses existing `httpx`, `json`, `math`, `dataclasses` and free APIs.

---

## Risk Register

| # | Risk | Severity | Mitigation |
|:--|:-----|:---------|:-----------|
| 1 | Yahoo rate-limits DXY/Gold | MED | 5-min polling, cache, share fetcher |
| 2 | VADER misreads crypto slang | LOW | 30+ term extended lexicon + keyword fallback |
| 3 | Order book staleness (5-min) | LOW | Context only, never primary driver |
| 4 | Squeeze false positives | MED | Require ≥1 other layer via confluence |
| 5 | Score inflation | HIGH | P8 recalibration + point budget doc |
| 6 | Old logs lack `intelligence` | MED | All reads use `.get()` with defaults |
| 7 | `compute_score()` merge conflicts | HIGH | Isolated `# --- Intel Layer ---` blocks |
| 8 | Single layer crash | HIGH | P10 circuit breakers |
| 9 | VADER init latency | LOW | Lazy singleton `get_engine()` |
| 10 | VP POC irrelevant in trends | LOW | Lower weight when regime=TREND |
| 11 | Alert clutter | MED | Conditional display, collapsible sections |

---

## Quick Reference

```bash
# Run (single cycle / continuous)
PYTHONPATH=. python app.py --once
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

- [ ] `AlertScore` has `context` field populated by all intelligence layers
- [ ] `IntelligenceBundle` carries data between collectors and engine
- [ ] Squeeze detector fires during volatility compression releases
- [ ] Volume Profile POC calculated and displayed
- [ ] Liquidity walls fetched and flag dangerous positions
- [ ] DXY/Gold correlation context in alerts
- [ ] AI sentiment replaces keyword matching (with fallback)
- [ ] Confluence heatmap on dashboard
- [ ] Telegram alerts show formatted intelligence summary
- [ ] Intelligence data persisted for historical analysis
- [ ] Scorecard reports intelligence layer performance
- [ ] Score thresholds recalibrated for new point range
- [ ] Backtest proves v3.0 ≥ v2.0 performance
- [ ] Every layer has error handling (no single-point-of-failure)
- [ ] Every layer has structured debug logging
- [ ] Feature flags enable/disable each layer independently
- [ ] All tests pass: `PYTHONPATH=. python -m pytest tests/ -v`
- [ ] README updated with v3.0 docs
- [ ] BudgetManager Yahoo limit fixed (10, not 0)
- [ ] Zero paid APIs — all free tier

---

_Single source of truth for v3.0 development. Update checkboxes as tasks complete._
