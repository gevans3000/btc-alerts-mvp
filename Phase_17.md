# Phase 17 — Confluence Indicator Minimum Stack ✅ COMPLETED 2026-02-26

> **AGENT INSTRUCTIONS:** This phase adds new intelligence modules and radar codes to the existing engine. You are NOT changing the dashboard layout. You are adding new detection functions in `intelligence/`, wiring new reason codes into `engine.py`, and adding them to the radar probe arrays in `generate_dashboard.py`. Follow each step exactly. Do NOT break existing functionality.

---

## ⚠️ RULES

1. **No dashboard layout changes.** Only add new codes to existing radar probe arrays.
2. **No new API calls.** All indicators below use candle data (`List[Candle]`) already fetched.
3. **No new dependencies.** Use only `utils.py` functions + stdlib `math`/`statistics`.
4. **Each new module = one file** in `intelligence/`. Follow the pattern of `squeeze.py`.
5. **Test after each step:** `python -c "from config import validate_config; validate_config(); print('OK')"`
6. **Full test after all steps:** `python app.py --once` (no tracebacks)

---

## � API BUDGET AUDIT — Read This Before Writing Any Code

**Every new module in this phase is pure computation. Zero new HTTP calls.**

### How This Works

All data this phase needs is **already fetched once per cycle** in `app.py`:

| Data | Fetched By | Budget per Cycle |
|---|---|---|
| BTC candles (5m/15m/1h) | `fetch_btc_multi_timeframe_candles()` | 3 Kraken calls |
| Derivatives (funding, OI, basis) | `fetch_derivatives_context()` | 1 Bybit or OKX call |
| Flows (taker ratio, L/S) | `fetch_flow_context()` | 1 Bybit or OKX call |
| Orderbook | `fetch_orderbook()` | 1 Bybit or OKX call |

The 7 new intelligence modules in this phase receive `candles: List[Candle]` and `derivatives: DerivativesSnapshot` as **function arguments** — objects already in memory. They do **no I/O whatsoever**.

### Banned Imports in New Files

The new files under `intelligence/` must **NOT** import any of these:

```
httpx          → makes HTTP calls
requests       → makes HTTP calls
collectors.*   → fetches from APIs (EXCEPTION: oi_classifier.py imports DerivativesSnapshot dataclass only — no fetch calls)
urllib         → makes HTTP calls
aiohttp        → makes HTTP calls
```

### Mandatory Pre-Commit Check

**Run this grep before every commit to confirm zero new API calls in new files:**

```powershell
Select-String -Path "intelligence\structure.py","intelligence\session_levels.py","intelligence\sweeps.py","intelligence\anchored_vwap.py","intelligence\volume_impulse.py","intelligence\oi_classifier.py","intelligence\auto_rr.py" -Pattern "httpx|requests|urllib|fetch_|request_json|BudgetManager" | Select-Object FileName, LineNumber, Line
```

**Expected output: NO matches.** Any match = API call snuck in = do not commit, fix it first.

The ONE allowed `collectors` import is in `oi_classifier.py`:
```python
from collectors.derivatives import DerivativesSnapshot  # DATACLASS ONLY — no fetch
```
This is a type annotation import. It does not call any API.

### Current API Limits (for reference)

From `collectors/base.py` `BudgetManager.LIMITS`:

| Provider | Max Calls | Window |
|---|---|---|
| bybit | 24 | 60s |
| okx | 30 | 60s |
| kraken | 24 | 60s |
| yahoo | 20 | 300s |
| coingecko | 10 | 60s |

**This phase adds 0 calls to any of these budgets.** The existing cycle uses approximately 6–10 calls per provider per cycle. All headroom remains intact.

---

## �📊 EXISTING vs NEW — What We Already Have

| Indicator | Status | Where |
|---|---|---|
| VWAP + reclaim/reject | ✅ EXISTS | `utils.py:vwap()`, `detectors.py` |
| Bollinger Bands / Squeeze | ✅ EXISTS | `utils.py:bollinger_bands()`, `squeeze.py` |
| EMA trend filter (9/21) | ✅ EXISTS | `utils.py:ema()`, `market_context.py:_trend_bias()` |
| RSI divergence | ✅ EXISTS | `utils.py:rsi_divergence()`, `detectors.py` |
| Swing levels (pivots) | ✅ EXISTS | `utils.py:swing_levels()` |
| Volume Profile POC | ✅ EXISTS | `intelligence/volume_profile.py` |
| Volume delta | ✅ EXISTS | `utils.py:volume_delta()` |
| ATR + regime | ✅ EXISTS | `utils.py:atr()`, `market_context.py:_regime()` |
| Donchian breakout | ✅ EXISTS | `utils.py:donchian_break()`, `detectors.py` |
| Funding rate | ✅ EXISTS | `collectors/derivatives.py`, `engine.py` |
| OI change | ✅ EXISTS | `collectors/derivatives.py`, `engine.py` |
| Basis | ✅ EXISTS | `collectors/derivatives.py`, `engine.py` |
| L/S ratio | ✅ EXISTS | `collectors/flows.py`, `engine.py` |
| Session labels | ✅ EXISTS | `market_context.py:_session_label()` |
| Order book walls | ✅ EXISTS | `liquidity.py`, `orderbook.py:_detect_walls()` |
| Macro (DXY/Gold) | ✅ EXISTS | `macro_correlation.py` |
| **Market structure (BOS/CHoCH)** | 🆕 NEW | Need `intelligence/structure.py` |
| **Liquidity sweep detection** | 🆕 NEW | Need `intelligence/sweeps.py` |
| **Equal highs/lows** | 🆕 NEW | Combine with `intelligence/sweeps.py` |
| **Session high/low + sweep** | 🆕 NEW | Need `intelligence/session_levels.py` |
| **PDH/PDL** | 🆕 NEW | Combine with `intelligence/session_levels.py` |
| **Anchored VWAP** | 🆕 NEW | Need `intelligence/anchored_vwap.py` |
| **Volume impulse (relative spike)** | 🆕 NEW | Need `intelligence/volume_impulse.py` |
| **Compression→Expansion** | 🆕 ENHANCE | Extend `squeeze.py` with ATR percentile |
| **Price–OI classifier** | 🆕 NEW | Need `intelligence/oi_classifier.py` |
| **Micro volatility (ATR percentile)** | 🆕 NEW | Combine with compression detector |
| **R:R to nearest liquidity** | 🆕 NEW | Need `intelligence/auto_rr.py` |
| **LVN air pocket** | 🆕 ENHANCE | Extend `volume_profile.py` |

---

## 📋 STEPS

---

### STEP 1: Create `intelligence/structure.py` — Market Structure (BOS/CHoCH)

Covers: **5m#1, 15m#2, 1h#1**

This module detects Break of Structure (BOS) and Change of Character (CHoCH) from pivot points.

**Create file:** `intelligence/structure.py`

```python
"""Market Structure: BOS (Break of Structure) and CHoCH (Change of Character)."""
from typing import List, Dict, Any, Tuple
from utils import Candle
import logging

logger = logging.getLogger(__name__)


def _find_pivots(candles: List[Candle], left: int = 3, right: int = 3) -> List[Dict]:
    """Find pivot highs and lows using left/right bar comparison."""
    pivots = []
    for i in range(left, len(candles) - right):
        # Pivot High
        is_ph = all(candles[i].high >= candles[i - j].high for j in range(1, left + 1)) and \
                all(candles[i].high >= candles[i + j].high for j in range(1, right + 1))
        if is_ph:
            pivots.append({"type": "high", "price": candles[i].high, "index": i, "ts": candles[i].ts})
        # Pivot Low
        is_pl = all(candles[i].low <= candles[i - j].low for j in range(1, left + 1)) and \
                all(candles[i].low <= candles[i + j].low for j in range(1, right + 1))
        if is_pl:
            pivots.append({"type": "low", "price": candles[i].low, "index": i, "ts": candles[i].ts})
    return pivots


def detect_structure(candles: List[Candle], left: int = 3, right: int = 3) -> Dict[str, Any]:
    """
    Detect BOS and CHoCH from recent candle data.

    Returns:
        {
            "trend": "bullish" | "bearish" | "neutral",
            "last_event": "BOS_BULL" | "BOS_BEAR" | "CHOCH_BULL" | "CHOCH_BEAR" | None,
            "last_pivot_high": float,
            "last_pivot_low": float,
            "codes": ["STRUCTURE_BOS_BULL"] etc.,
            "pts": float
        }
    """
    if len(candles) < 20:
        return {"trend": "neutral", "last_event": None, "last_pivot_high": 0, "last_pivot_low": 0, "codes": [], "pts": 0}

    pivots = _find_pivots(candles, left, right)
    if len(pivots) < 4:
        return {"trend": "neutral", "last_event": None, "last_pivot_high": 0, "last_pivot_low": 0, "codes": [], "pts": 0}

    # Get the last few highs and lows
    highs = [p for p in pivots if p["type"] == "high"]
    lows = [p for p in pivots if p["type"] == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return {"trend": "neutral", "last_event": None, "last_pivot_high": 0, "last_pivot_low": 0, "codes": [], "pts": 0}

    last_price = candles[-1].close
    prev_high = highs[-2]["price"]
    last_high = highs[-1]["price"]
    prev_low = lows[-2]["price"]
    last_low = lows[-1]["price"]

    # Determine current trend from higher highs / higher lows vs lower highs / lower lows
    hh = last_high > prev_high  # Higher high
    hl = last_low > prev_low    # Higher low
    lh = last_high < prev_high  # Lower high
    ll = last_low < prev_low    # Lower low

    codes = []
    pts = 0.0
    event = None

    if hh and hl:
        # Bullish structure
        trend = "bullish"
        # BOS = price breaks above the last pivot high
        if last_price > last_high:
            event = "BOS_BULL"
            codes.append("STRUCTURE_BOS_BULL")
            pts = 5.0
    elif lh and ll:
        # Bearish structure
        trend = "bearish"
        if last_price < last_low:
            event = "BOS_BEAR"
            codes.append("STRUCTURE_BOS_BEAR")
            pts = -5.0
    elif hh and ll:
        trend = "neutral"  # Expanding — no clear structure
    elif lh and hl:
        trend = "neutral"  # Contracting — range
    else:
        trend = "neutral"

    # CHoCH: was bearish (LH+LL) but now made a higher high, or vice versa
    if lh and not ll and last_price > last_high:
        event = "CHOCH_BULL"
        codes.append("STRUCTURE_CHOCH_BULL")
        pts = 6.0
        trend = "shift_bullish"
    elif hh and not hl and last_price < last_low:
        event = "CHOCH_BEAR"
        codes.append("STRUCTURE_CHOCH_BEAR")
        pts = -6.0
        trend = "shift_bearish"

    return {
        "trend": trend,
        "last_event": event,
        "last_pivot_high": last_high,
        "last_pivot_low": last_low,
        "codes": codes,
        "pts": pts,
    }
```

**VERIFY:**
```
python -c "from intelligence.structure import detect_structure; print('STEP 1 OK')"
```

---

### STEP 2: Create `intelligence/session_levels.py` — PDH/PDL + Session High/Low + Sweep

Covers: **5m#4, 5m#5, 15m#3, 15m#6, 1h#2**

Computes prior-day high/low and session (Asia/London/NY) high/low from candle data. Detects sweeps (wick through + close back).

**Create file:** `intelligence/session_levels.py`

```python
"""Session levels: PDH/PDL, session high/low, sweep detection."""
from datetime import datetime, timezone
from typing import List, Dict, Any
from utils import Candle
import logging

logger = logging.getLogger(__name__)


def _candle_dt(c: Candle) -> datetime:
    return datetime.fromtimestamp(int(float(c.ts)), tz=timezone.utc)


def _session_of(dt: datetime) -> str:
    h = dt.hour
    if 0 <= h < 8:
        return "asia"
    elif 8 <= h < 13:
        return "london"
    else:
        return "ny"


def compute_session_levels(candles: List[Candle]) -> Dict[str, Any]:
    """
    From candle history, compute:
     - PDH / PDL (prior day high/low)
     - Current session high/low (asia/london/ny)
     - Sweep flags (price wicked through then closed back)

    Returns dict with codes list and level values.
    """
    if len(candles) < 50:
        return {"pdh": 0, "pdl": 0, "session_high": 0, "session_low": 0, "codes": [], "pts": 0}

    now_dt = _candle_dt(candles[-1])
    today = now_dt.date()
    current_session = _session_of(now_dt)

    # Split candles by day
    prior_day_candles = []
    today_candles = []
    session_candles = []

    for c in candles:
        dt = _candle_dt(c)
        if dt.date() < today:
            prior_day_candles.append(c)
        elif dt.date() == today:
            today_candles.append(c)
            if _session_of(dt) == current_session:
                session_candles.append(c)

    # Only keep last full day for PDH/PDL
    if prior_day_candles:
        last_day = _candle_dt(prior_day_candles[-1]).date()
        prior_day_candles = [c for c in prior_day_candles if _candle_dt(c).date() == last_day]

    pdh = max((c.high for c in prior_day_candles), default=0)
    pdl = min((c.low for c in prior_day_candles), default=0)
    session_high = max((c.high for c in session_candles), default=0) if session_candles else 0
    session_low = min((c.low for c in session_candles), default=0) if session_candles else 0

    codes = []
    pts = 0.0
    last = candles[-1]

    # Sweep detection: wick through level but close back inside
    if pdh > 0 and last.high > pdh and last.close < pdh:
        codes.append("PDH_SWEEP_BEAR")
        pts -= 4.0
    if pdl > 0 and last.low < pdl and last.close > pdl:
        codes.append("PDL_SWEEP_BULL")
        pts += 4.0
    # Reclaim: close above PDH or below PDL
    if pdh > 0 and last.close > pdh:
        codes.append("PDH_RECLAIM_BULL")
        pts += 3.0
    if pdl > 0 and last.close < pdl:
        codes.append("PDL_BREAK_BEAR")
        pts -= 3.0

    # Session level sweep
    if session_high > 0 and last.high > session_high and last.close < session_high and len(session_candles) > 5:
        codes.append("SESSION_HIGH_SWEEP")
        pts -= 2.0
    if session_low > 0 and last.low < session_low and last.close > session_low and len(session_candles) > 5:
        codes.append("SESSION_LOW_SWEEP")
        pts += 2.0

    return {
        "pdh": round(pdh, 2), "pdl": round(pdl, 2),
        "session_high": round(session_high, 2), "session_low": round(session_low, 2),
        "session": current_session,
        "codes": codes, "pts": pts,
    }
```

**VERIFY:**
```
python -c "from intelligence.session_levels import compute_session_levels; print('STEP 2 OK')"
```

---

### STEP 3: Create `intelligence/sweeps.py` — Equal Highs/Lows + Liquidity Sweep Detection

Covers: **5m#2, 5m#3, 15m#4, 15m#5, 1h#4**

Detects equal highs/lows (resting stop clusters) and takeout/sweep events.

**Create file:** `intelligence/sweeps.py`

```python
"""Equal highs/lows and liquidity sweep detection."""
from typing import List, Dict, Any
from utils import Candle
import logging

logger = logging.getLogger(__name__)


def detect_equal_levels(candles: List[Candle], tolerance_pct: float = 0.001, min_touches: int = 2, lookback: int = 50) -> Dict[str, Any]:
    """
    Detect equal highs and equal lows (resting liquidity).
    Also detect takeout/sweep: wick through the cluster then close back.

    Returns:
        {
            "equal_highs": [price, ...],
            "equal_lows": [price, ...],
            "sweep_high": bool,  # Just swept above equal highs
            "sweep_low": bool,   # Just swept below equal lows
            "codes": [],
            "pts": float
        }
    """
    if len(candles) < 20:
        return {"equal_highs": [], "equal_lows": [], "sweep_high": False, "sweep_low": False, "codes": [], "pts": 0}

    subset = candles[-lookback:]
    last = candles[-1]
    ref = last.close

    # Cluster highs by proximity
    highs = [c.high for c in subset[:-1]]
    lows = [c.low for c in subset[:-1]]

    def _find_clusters(levels: List[float], tol: float) -> List[float]:
        if not levels:
            return []
        sorted_lvls = sorted(levels)
        clusters = []
        group = [sorted_lvls[0]]
        for lvl in sorted_lvls[1:]:
            if abs(lvl - group[0]) / max(group[0], 1e-9) <= tol:
                group.append(lvl)
            else:
                if len(group) >= min_touches:
                    clusters.append(sum(group) / len(group))
                group = [lvl]
        if len(group) >= min_touches:
            clusters.append(sum(group) / len(group))
        return clusters

    eq_highs = _find_clusters(highs, tolerance_pct)
    eq_lows = _find_clusters(lows, tolerance_pct)

    codes = []
    pts = 0.0

    # Filter to nearby levels (within 1% of current price)
    eq_highs = [h for h in eq_highs if abs(h - ref) / ref < 0.01]
    eq_lows = [l for l in eq_lows if abs(l - ref) / ref < 0.01]

    if eq_highs:
        codes.append("EQUAL_HIGHS_NEARBY")
    if eq_lows:
        codes.append("EQUAL_LOWS_NEARBY")

    # Sweep detection
    sweep_high = False
    sweep_low = False
    for h in eq_highs:
        if last.high > h and last.close < h:
            sweep_high = True
            codes.append("EQH_SWEEP_BEAR")
            pts -= 4.0
            break
    for l in eq_lows:
        if last.low < l and last.close > l:
            sweep_low = True
            codes.append("EQL_SWEEP_BULL")
            pts += 4.0
            break

    return {
        "equal_highs": [round(h, 2) for h in eq_highs],
        "equal_lows": [round(l, 2) for l in eq_lows],
        "sweep_high": sweep_high,
        "sweep_low": sweep_low,
        "codes": codes,
        "pts": pts,
    }
```

**VERIFY:**
```
python -c "from intelligence.sweeps import detect_equal_levels; print('STEP 3 OK')"
```

---

### STEP 4: Create `intelligence/anchored_vwap.py` — Anchored VWAP from Swing

Covers: **5m#8, 15m#8, 1h#13**

Computes VWAP anchored from the most recent significant swing high/low, plus deviation bands.

**Create file:** `intelligence/anchored_vwap.py`

```python
"""Anchored VWAP from the last significant swing point."""
from typing import List, Dict, Any
from utils import Candle
from math import sqrt
import logging

logger = logging.getLogger(__name__)


def compute_anchored_vwap(candles: List[Candle], lookback_for_anchor: int = 50) -> Dict[str, Any]:
    """
    Find the last major swing (highest high or lowest low in lookback),
    then compute VWAP from that point forward with ±1σ and ±2σ bands.

    Returns:
        {
            "avwap": float,       # Anchored VWAP value
            "upper_1": float,     # +1 std dev band
            "lower_1": float,     # -1 std dev band
            "anchor_price": float,
            "anchor_type": "high" | "low",
            "price_vs_avwap": "above" | "below" | "at",
            "codes": [],
            "pts": float
        }
    """
    if len(candles) < 20:
        return {"avwap": 0, "upper_1": 0, "lower_1": 0, "anchor_price": 0, "anchor_type": "high", "price_vs_avwap": "at", "codes": [], "pts": 0}

    # Find anchor: highest high or lowest low in lookback
    subset = candles[-lookback_for_anchor:] if len(candles) >= lookback_for_anchor else candles
    max_high = max(range(len(subset)), key=lambda i: subset[i].high)
    min_low = min(range(len(subset)), key=lambda i: subset[i].low)

    # Use whichever is more recent as anchor
    if max_high > min_low:
        anchor_idx = max_high
        anchor_type = "high"
        anchor_price = subset[anchor_idx].high
    else:
        anchor_idx = min_low
        anchor_type = "low"
        anchor_price = subset[anchor_idx].low

    # Compute VWAP from anchor forward
    vwap_candles = subset[anchor_idx:]
    if len(vwap_candles) < 3:
        return {"avwap": 0, "upper_1": 0, "lower_1": 0, "anchor_price": anchor_price, "anchor_type": anchor_type, "price_vs_avwap": "at", "codes": [], "pts": 0}

    cum_vol = 0.0
    cum_tp_vol = 0.0
    cum_tp2_vol = 0.0
    for c in vwap_candles:
        tp = (c.high + c.low + c.close) / 3.0
        cum_vol += c.volume
        cum_tp_vol += tp * c.volume
        cum_tp2_vol += tp * tp * c.volume

    if cum_vol == 0:
        return {"avwap": 0, "upper_1": 0, "lower_1": 0, "anchor_price": anchor_price, "anchor_type": anchor_type, "price_vs_avwap": "at", "codes": [], "pts": 0}

    avwap = cum_tp_vol / cum_vol
    variance = max(0, (cum_tp2_vol / cum_vol) - avwap * avwap)
    std = sqrt(variance)
    upper_1 = avwap + std
    lower_1 = avwap - std

    last_price = candles[-1].close
    codes = []
    pts = 0.0

    if last_price > avwap:
        pos = "above"
    elif last_price < avwap:
        pos = "below"
    else:
        pos = "at"

    # Reclaim/reject signals
    prev_close = candles[-2].close if len(candles) >= 2 else last_price
    if prev_close < avwap and last_price > avwap:
        codes.append("AVWAP_RECLAIM_BULL")
        pts += 3.0
    elif prev_close > avwap and last_price < avwap:
        codes.append("AVWAP_REJECT_BEAR")
        pts -= 3.0

    # Band extremes
    if last_price > upper_1:
        codes.append("AVWAP_ABOVE_1SD")
    elif last_price < lower_1:
        codes.append("AVWAP_BELOW_1SD")

    return {
        "avwap": round(avwap, 2), "upper_1": round(upper_1, 2), "lower_1": round(lower_1, 2),
        "anchor_price": round(anchor_price, 2), "anchor_type": anchor_type,
        "price_vs_avwap": pos, "codes": codes, "pts": pts,
    }
```

**VERIFY:**
```
python -c "from intelligence.anchored_vwap import compute_anchored_vwap; print('STEP 4 OK')"
```

---

### STEP 5: Create `intelligence/volume_impulse.py` — Relative Volume Spike

Covers: **5m#12, 15m#9, 5m#18 (micro vol)**

Detects candles where volume is N× the rolling average (impulse). Also flags ATR percentile regime.

**Create file:** `intelligence/volume_impulse.py`

```python
"""Volume impulse detector and micro-volatility regime."""
from typing import List, Dict, Any
from utils import Candle, atr, percentile_rank
import logging

logger = logging.getLogger(__name__)


def detect_volume_impulse(candles: List[Candle], vol_lookback: int = 20, spike_mult: float = 2.0, atr_lookback: int = 50) -> Dict[str, Any]:
    """
    1. Volume impulse: current candle volume vs rolling average.
    2. ATR percentile: current ATR rank over history for regime flag.

    Returns:
        {
            "rvol": float,              # Relative volume (current / avg)
            "is_spike": bool,
            "atr_percentile": float,    # 0–100
            "vol_regime": "low" | "normal" | "expansion",
            "codes": [],
            "pts": float
        }
    """
    if len(candles) < vol_lookback + 5:
        return {"rvol": 1.0, "is_spike": False, "atr_percentile": 50, "vol_regime": "normal", "codes": [], "pts": 0}

    volumes = [c.volume for c in candles[-(vol_lookback + 1):-1]]
    avg_vol = sum(volumes) / len(volumes) if volumes else 1.0
    current_vol = candles[-1].volume
    rvol = current_vol / max(avg_vol, 1e-9)
    is_spike = rvol >= spike_mult

    # ATR percentile
    atr_series = []
    for i in range(20, min(len(candles), atr_lookback + 20)):
        a = atr(candles[:i], 14)
        if a is not None:
            atr_series.append(a)
    current_atr = atr(candles, 14) or 0.0
    atr_pct = percentile_rank(atr_series, current_atr) if atr_series else 50.0

    if atr_pct >= 80:
        vol_regime = "expansion"
    elif atr_pct <= 20:
        vol_regime = "low"
    else:
        vol_regime = "normal"

    codes = []
    pts = 0.0

    if is_spike:
        codes.append("VOLUME_IMPULSE")
        pts += 2.0  # Neutral — direction determined by price action context
    if vol_regime == "expansion":
        codes.append("VOL_REGIME_EXPANSION")
    elif vol_regime == "low":
        codes.append("VOL_REGIME_LOW")

    return {
        "rvol": round(rvol, 2), "is_spike": is_spike,
        "atr_percentile": round(atr_pct, 1), "vol_regime": vol_regime,
        "codes": codes, "pts": pts,
    }
```

**VERIFY:**
```
python -c "from intelligence.volume_impulse import detect_volume_impulse; print('STEP 5 OK')"
```

---

### STEP 6: Create `intelligence/oi_classifier.py` — Price–OI Relationship Classifier

Covers: **5m#15, 5m#16, 15m#12, 15m#16, 1h#7**

Classifies the price–OI relationship: price↑+OI↑ = new longs, price↑+OI↓ = short covering, etc.

**Create file:** `intelligence/oi_classifier.py`

```python
"""Price–OI relationship classifier."""
from typing import Dict, Any
from collectors.derivatives import DerivativesSnapshot
import logging

logger = logging.getLogger(__name__)


def classify_price_oi(price_change_pct: float, derivatives: DerivativesSnapshot) -> Dict[str, Any]:
    """
    Classify relationship between price change and OI change.

    4 regimes:
    - price↑ + OI↑  = NEW_LONGS (bullish continuation)
    - price↑ + OI↓  = SHORT_COVERING (weak rally, may reverse)
    - price↓ + OI↑  = NEW_SHORTS (bearish continuation)
    - price↓ + OI↓  = LONG_LIQUIDATION (capitulation, may reverse)

    Returns: {"regime": str, "codes": [], "pts": float}
    """
    if not derivatives or not derivatives.healthy:
        return {"regime": "UNKNOWN", "codes": [], "pts": 0}

    oi_pct = derivatives.oi_change_pct
    codes = []
    pts = 0.0

    # Thresholds: meaningful moves only
    price_up = price_change_pct > 0.1
    price_down = price_change_pct < -0.1
    oi_up = oi_pct > 0.3
    oi_down = oi_pct < -0.3

    if price_up and oi_up:
        regime = "NEW_LONGS"
        codes.append("OI_NEW_LONGS")
        pts = 3.0
    elif price_up and oi_down:
        regime = "SHORT_COVERING"
        codes.append("OI_SHORT_COVERING")
        pts = -1.0  # Weak rally
    elif price_down and oi_up:
        regime = "NEW_SHORTS"
        codes.append("OI_NEW_SHORTS")
        pts = -3.0
    elif price_down and oi_down:
        regime = "LONG_LIQUIDATION"
        codes.append("OI_LONG_LIQUIDATION")
        pts = 1.0  # Capitulation = potential reversal
    else:
        regime = "NEUTRAL"

    return {"regime": regime, "codes": codes, "pts": pts}
```

**VERIFY:**
```
python -c "from intelligence.oi_classifier import classify_price_oi; print('STEP 6 OK')"
```

---

### STEP 7: Enhance `intelligence/volume_profile.py` — Add LVN (Low Volume Node) Detection

Covers: **5m#21, 15m#10, 1h#5**

Add LVN "air pocket" detection to the existing volume profile module.

**File:** `intelligence/volume_profile.py`

**FIND this exact text** (lines 34–37):

```python
    idx = bins.index(max(bins))
    poc = lo + (idx + 0.5) * bin_size
    near = abs(candles[-1].close - poc) / poc <= poc_pct
    return {"poc": round(poc, 2), "near_poc": near, "pts": poc_pts if near else 0, "profile_bins": num_bins}
```

**REPLACE WITH:**

```python
    idx = bins.index(max(bins))
    poc = lo + (idx + 0.5) * bin_size
    near = abs(candles[-1].close - poc) / poc <= poc_pct

    # VAH / VAL (Value Area = 70% of total volume centered on POC)
    total_vol = sum(bins)
    target_vol = total_vol * 0.70
    cum = bins[idx]
    lo_idx, hi_idx = idx, idx
    while cum < target_vol and (lo_idx > 0 or hi_idx < num_bins - 1):
        add_lo = bins[lo_idx - 1] if lo_idx > 0 else 0
        add_hi = bins[hi_idx + 1] if hi_idx < num_bins - 1 else 0
        if add_hi >= add_lo and hi_idx < num_bins - 1:
            hi_idx += 1
            cum += add_hi
        elif lo_idx > 0:
            lo_idx -= 1
            cum += add_lo
        else:
            break
    vah = lo + (hi_idx + 1) * bin_size
    val = lo + lo_idx * bin_size

    # LVN detection: bins with < 20% of POC volume near current price
    poc_vol = bins[idx]
    lvn_threshold = poc_vol * 0.20
    last_price = candles[-1].close
    lvn_zones = []
    for b in range(num_bins):
        if bins[b] < lvn_threshold:
            lvn_price = lo + (b + 0.5) * bin_size
            if abs(lvn_price - last_price) / last_price < 0.02:  # Within 2%
                lvn_zones.append(round(lvn_price, 2))

    codes = []
    extra_pts = 0
    if lvn_zones:
        codes.append("LVN_NEARBY")
        extra_pts = 2

    # Inside vs outside value area
    if val <= last_price <= vah:
        codes.append("INSIDE_VALUE")
    elif last_price > vah:
        codes.append("ABOVE_VALUE")
    elif last_price < val:
        codes.append("BELOW_VALUE")

    return {
        "poc": round(poc, 2), "vah": round(vah, 2), "val": round(val, 2),
        "near_poc": near, "pts": (poc_pts if near else 0) + extra_pts,
        "profile_bins": num_bins, "lvn_zones": lvn_zones, "codes": codes,
    }
```

**VERIFY:**
```
python -c "from intelligence.volume_profile import compute_volume_profile; from utils import Candle; cs = [Candle(str(i), 100+i*0.1, 101+i*0.1, 99+i*0.1, 100.5+i*0.1, 1000) for i in range(120)]; r = compute_volume_profile(cs); print('STEP 7 OK:', 'vah' in r, 'val' in r, 'lvn_zones' in r)"
```

---

### STEP 8: Create `intelligence/auto_rr.py` — R:R to Nearest Liquidity

Covers: **5m#25, 15m#25, 1h#22**

Auto-computes R:R from current price to the nearest opposing liquidity cluster.

**Create file:** `intelligence/auto_rr.py`

```python
"""Auto R:R computation to nearest liquidity."""
from typing import List, Dict, Any
from utils import Candle, swing_levels, atr
import logging

logger = logging.getLogger(__name__)


def compute_auto_rr(candles: List[Candle], direction: str) -> Dict[str, Any]:
    """
    Given a direction (LONG/SHORT), compute:
     - Entry = current close
     - Stop = nearest opposing swing level (support for long, resistance for short)
     - Target = nearest same-side level beyond entry
     - R:R ratio

    Returns: {"entry": float, "stop": float, "target": float, "rr": float, "codes": [], "pts": float}
    """
    if len(candles) < 30 or direction not in ("LONG", "SHORT"):
        return {"entry": 0, "stop": 0, "target": 0, "rr": 0, "codes": [], "pts": 0}

    entry = candles[-1].close
    levels = swing_levels(candles, lookback=50, tolerance=0.002)
    local_atr = atr(candles, 14) or (entry * 0.01)

    above = sorted([l for l in levels if l > entry])
    below = sorted([l for l in levels if l < entry], reverse=True)

    if direction == "LONG":
        stop = below[0] if below else entry - local_atr * 2
        target = above[0] if above else entry + local_atr * 2
    else:
        stop = above[0] if above else entry + local_atr * 2
        target = below[0] if below else entry - local_atr * 2

    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = reward / risk if risk > 0 else 0

    codes = []
    pts = 0.0

    if rr >= 2.0:
        codes.append("AUTO_RR_EXCELLENT")
        pts = 3.0
    elif rr >= 1.2:
        codes.append("AUTO_RR_ADEQUATE")
        pts = 1.0
    else:
        codes.append("AUTO_RR_POOR")
        pts = -2.0

    return {
        "entry": round(entry, 2), "stop": round(stop, 2),
        "target": round(target, 2), "rr": round(rr, 2),
        "codes": codes, "pts": pts,
    }
```

**VERIFY:**
```
python -c "from intelligence.auto_rr import compute_auto_rr; print('STEP 8 OK')"
```

---

### STEP 9: Wire ALL New Modules into `engine.py`

Now connect every new module into the scoring engine. All new codes flow into `decision_trace.codes` and are automatically picked up by the dashboard radar.

**File:** `engine.py`

**FIND this exact text** (lines 1–3):

```python
from typing import Dict, Any, List, Optional, Tuple
from config import INTELLIGENCE_FLAGS
from intelligence import IntelligenceBundle, AlertScore
```

**REPLACE WITH:**

```python
from typing import Dict, Any, List, Optional, Tuple
from config import INTELLIGENCE_FLAGS
from intelligence import IntelligenceBundle, AlertScore
from intelligence.structure import detect_structure
from intelligence.session_levels import compute_session_levels
from intelligence.sweeps import detect_equal_levels
from intelligence.anchored_vwap import compute_anchored_vwap
from intelligence.volume_impulse import detect_volume_impulse
from intelligence.oi_classifier import classify_price_oi
from intelligence.auto_rr import compute_auto_rr
```

**THEN FIND this exact text** (lines 188–192, right after the flows mapping):

```python
    # Candidates
    candidates, c_reasons, c_codes = _detector_candidates(candles)
    reasons.extend(c_reasons)
    codes.extend(c_codes)
    trace["candidates"] = candidates
```

**INSERT BEFORE that block** (above the `# Candidates` comment):

```python
    # --- Phase 17: New Intelligence Layers ---
    # Market Structure (BOS/CHoCH)
    try:
        struct = detect_structure(candles)
        codes.extend(struct["codes"])
        breakdown["momentum"] += struct["pts"]
        trace["context"]["structure"] = {"trend": struct["trend"], "event": struct["last_event"]}
    except Exception:
        pass

    # Session Levels (PDH/PDL + sweep)
    try:
        sess_lvl = compute_session_levels(candles)
        codes.extend(sess_lvl["codes"])
        breakdown["htf"] += sess_lvl["pts"]
        trace["context"]["session_levels"] = {"pdh": sess_lvl["pdh"], "pdl": sess_lvl["pdl"]}
    except Exception:
        pass

    # Equal Highs/Lows + Sweep
    try:
        eql = detect_equal_levels(candles)
        codes.extend(eql["codes"])
        breakdown["momentum"] += eql["pts"]
        trace["context"]["equal_levels"] = {"eq_highs": len(eql["equal_highs"]), "eq_lows": len(eql["equal_lows"])}
    except Exception:
        pass

    # Anchored VWAP
    try:
        avwap = compute_anchored_vwap(candles)
        codes.extend(avwap["codes"])
        breakdown["momentum"] += avwap["pts"]
        trace["context"]["avwap"] = {"value": avwap["avwap"], "position": avwap["price_vs_avwap"]}
    except Exception:
        pass

    # Volume Impulse + Micro Volatility
    try:
        vimp = detect_volume_impulse(candles)
        codes.extend(vimp["codes"])
        breakdown["volume"] += vimp["pts"]
        trace["context"]["volume_impulse"] = {"rvol": vimp["rvol"], "regime": vimp["vol_regime"]}
    except Exception:
        pass

    # Price–OI Classifier (needs price change from candles + derivatives)
    if derivatives and derivatives.healthy and len(candles) >= 2:
        try:
            price_chg = ((candles[-1].close - candles[-2].close) / candles[-2].close) * 100
            oi_class = classify_price_oi(price_chg, derivatives)
            codes.extend(oi_class["codes"])
            breakdown["momentum"] += oi_class["pts"]
            trace["context"]["oi_regime"] = oi_class["regime"]
        except Exception:
            pass

```

> ⚠️ Make sure this block goes ABOVE the `# Candidates` comment line. Do not delete the Candidates block.

**THEN** — after the `direction = ...` line (line 222) and before the exit levels section, add auto R:R:

**FIND this exact text** (lines 222–224):

```python
    direction = "LONG" if pts > 0 else "SHORT" if pts < 0 else "NEUTRAL"
    
    tp_cfg = TP_MULTIPLIERS.get(regime_name, TP_MULTIPLIERS["default"])
```

**REPLACE WITH:**

```python
    direction = "LONG" if pts > 0 else "SHORT" if pts < 0 else "NEUTRAL"

    # Auto R:R to nearest liquidity
    try:
        auto_rr = compute_auto_rr(candles, direction)
        codes.extend(auto_rr["codes"])
        trace["context"]["auto_rr"] = {"rr": auto_rr["rr"], "target": auto_rr["target"], "stop": auto_rr["stop"]}
    except Exception:
        pass

    tp_cfg = TP_MULTIPLIERS.get(regime_name, TP_MULTIPLIERS["default"])
```

**VERIFY:**
```
python -c "from engine import compute_score; print('STEP 9 OK')"
```

---

### STEP 10: Add New Codes to Dashboard Radar Probes

Add the new codes to the existing radar probe arrays in `generate_dashboard.py` so they show as 🟢/🔴 on the dashboard.

**File:** `scripts/pid-129/generate_dashboard.py`

**FIND this exact text** in `build_verdict_context()` (line 396–402):

```python
    probes = [
        ("Squeeze", ["SQUEEZE_FIRE", "SQUEEZE_ON"], []), ("Trend (HTF)", ["HTF_ALIGNED"], ["HTF_COUNTER"]),
        ("Momentum", ["SENTIMENT_BULL", "FLOW_TAKER_BULLISH"], ["SENTIMENT_BEAR", "FLOW_TAKER_BEARISH"]), ("ML Model", ["ML_CONFIDENCE_BOOST"], ["ML_SKEPTICISM"]),
        ("Funding", ["FUNDING_EXTREME_LOW", "FUNDING_LOW"], ["FUNDING_EXTREME_HIGH", "FUNDING_HIGH"]),
        ("DXY Macro", ["DXY_FALLING_BULLISH"], ["DXY_RISING_BEARISH"]), ("Gold Macro", ["GOLD_RISING_BULLISH"], ["GOLD_FALLING_BEARISH"]),
        ("Fear & Greed", ["FG_EXTREME_FEAR", "FG_FEAR"], ["FG_EXTREME_GREED", "FG_GREED"]),
        ("Order Book", ["BID_WALL_SUPPORT"], ["ASK_WALL_RESISTANCE"]), ("OI / Basis", ["OI_SURGE_MAJOR", "OI_SURGE_MINOR", "BASIS_BULLISH"], ["BASIS_BEARISH"]),
    ]
```

**REPLACE WITH:**

```python
    probes = [
        ("Squeeze", ["SQUEEZE_FIRE", "SQUEEZE_ON"], []), ("Trend (HTF)", ["HTF_ALIGNED"], ["HTF_COUNTER"]),
        ("Momentum", ["SENTIMENT_BULL", "FLOW_TAKER_BULLISH", "VOLUME_IMPULSE"], ["SENTIMENT_BEAR", "FLOW_TAKER_BEARISH"]), ("ML Model", ["ML_CONFIDENCE_BOOST"], ["ML_SKEPTICISM"]),
        ("Funding", ["FUNDING_EXTREME_LOW", "FUNDING_LOW"], ["FUNDING_EXTREME_HIGH", "FUNDING_HIGH"]),
        ("DXY Macro", ["DXY_FALLING_BULLISH"], ["DXY_RISING_BEARISH"]), ("Gold Macro", ["GOLD_RISING_BULLISH"], ["GOLD_FALLING_BEARISH"]),
        ("Fear & Greed", ["FG_EXTREME_FEAR", "FG_FEAR"], ["FG_EXTREME_GREED", "FG_GREED"]),
        ("Order Book", ["BID_WALL_SUPPORT"], ["ASK_WALL_RESISTANCE"]), ("OI / Basis", ["OI_SURGE_MAJOR", "OI_SURGE_MINOR", "BASIS_BULLISH", "OI_NEW_LONGS"], ["BASIS_BEARISH", "OI_NEW_SHORTS"]),
        ("Structure", ["STRUCTURE_BOS_BULL", "STRUCTURE_CHOCH_BULL"], ["STRUCTURE_BOS_BEAR", "STRUCTURE_CHOCH_BEAR"]),
        ("Levels", ["PDL_SWEEP_BULL", "EQL_SWEEP_BULL", "SESSION_LOW_SWEEP", "PDH_RECLAIM_BULL"], ["PDH_SWEEP_BEAR", "EQH_SWEEP_BEAR", "SESSION_HIGH_SWEEP", "PDL_BREAK_BEAR"]),
        ("AVWAP", ["AVWAP_RECLAIM_BULL"], ["AVWAP_REJECT_BEAR"]),
    ]
```

**THEN** — update the JavaScript `wsPD` array on line 623 (inside `connectWS`).

**FIND this exact substring** on line 623:

```
[['BID_WALL_SUPPORT'],['ASK_WALL_RESISTANCE'],'Order Book'],[['OI_SURGE_MAJOR','OI_SURGE_MINOR','BASIS_BULLISH'],['BASIS_BEARISH'],'OI / Basis']]
```

**REPLACE WITH this exact substring:**

```
[['BID_WALL_SUPPORT'],['ASK_WALL_RESISTANCE'],'Order Book'],[['OI_SURGE_MAJOR','OI_SURGE_MINOR','BASIS_BULLISH','OI_NEW_LONGS'],['BASIS_BEARISH','OI_NEW_SHORTS'],'OI / Basis'],[['STRUCTURE_BOS_BULL','STRUCTURE_CHOCH_BULL'],['STRUCTURE_BOS_BEAR','STRUCTURE_CHOCH_BEAR'],'Structure'],[['PDL_SWEEP_BULL','EQL_SWEEP_BULL','SESSION_LOW_SWEEP','PDH_RECLAIM_BULL'],['PDH_SWEEP_BEAR','EQH_SWEEP_BEAR','SESSION_HIGH_SWEEP','PDL_BREAK_BEAR'],'Levels'],[['AVWAP_RECLAIM_BULL'],['AVWAP_REJECT_BEAR'],'AVWAP']]
```

> ⚠️ This ONLY replaces the end of the `wsPD` array. The `]]` at the old end becomes `],...new probes...]]`. Do NOT replace the entire line.

**VERIFY:**
```
python scripts/pid-129/generate_dashboard.py
```

Must print `Dashboard generated:` with no errors.

---

### STEP 11: Wire New Modules into `app.py` `_collect_intelligence()`

The new modules compute from candles only — no new API calls. But `volume_profile.py` was enhanced (Step 7), so just verify imports work.

**No changes needed in `app.py`** — the new modules are called directly in `engine.py` (Step 9), not through `_collect_intelligence()`. The engine already receives `candles` and `derivatives` as parameters.

**VERIFY:**
```
python app.py --once
```

Should complete with no tracebacks and new codes visible in the output.

---

### STEP 12: Final Verification

```
python -c "from config import validate_config; validate_config(); print('1. Config OK')"
python -c "from intelligence.structure import detect_structure; print('2. Structure OK')"
python -c "from intelligence.session_levels import compute_session_levels; print('3. Session Levels OK')"
python -c "from intelligence.sweeps import detect_equal_levels; print('4. Sweeps OK')"
python -c "from intelligence.anchored_vwap import compute_anchored_vwap; print('5. AVWAP OK')"
python -c "from intelligence.volume_impulse import detect_volume_impulse; print('6. Volume Impulse OK')"
python -c "from intelligence.oi_classifier import classify_price_oi; print('7. OI Classifier OK')"
python -c "from intelligence.auto_rr import compute_auto_rr; print('8. Auto R:R OK')"
python -c "from engine import compute_score; print('9. Engine OK')"
python scripts/pid-129/generate_dashboard.py
python -m pytest tests/ -x -q
python app.py --once
```

All must pass with no errors.

---

## 🚫 Do NOT

- Do NOT change dashboard CSS or HTML layout
- Do NOT add new API endpoints or collectors
- Do NOT install new Python packages
- Do NOT modify `dashboard_server.py`
- Do NOT rename any existing files
- Do NOT remove any existing radar probes

---

## 📁 New Files Created

| File | Purpose |
|:--|:--|
| `intelligence/structure.py` | BOS/CHoCH detection from pivots |
| `intelligence/session_levels.py` | PDH/PDL + session high/low + sweep |
| `intelligence/sweeps.py` | Equal highs/lows + takeout detection |
| `intelligence/anchored_vwap.py` | VWAP from last swing + deviation bands |
| `intelligence/volume_impulse.py` | Relative volume spike + ATR regime |
| `intelligence/oi_classifier.py` | Price–OI relationship (new longs/shorts/covering/liquidation) |
| `intelligence/auto_rr.py` | Auto R:R to nearest swing levels |

## 📁 Files Modified

| File | Changes |
|:--|:--|
| `intelligence/volume_profile.py` | Added VAH/VAL, LVN detection, inside/outside value codes |
| `engine.py` | Added imports + wiring for all 7 new modules + auto_rr |
| `scripts/pid-129/generate_dashboard.py` | Added 3 new radar probes (Structure, Levels, AVWAP) to Python + JS arrays |

---

*Phase 17 — Confluence Indicator Minimum Stack | Created: 2026-02-26*
*7 new intelligence modules, 1 enhanced, 3 new radar probes*
*All computed from existing candle data — zero new API calls*
