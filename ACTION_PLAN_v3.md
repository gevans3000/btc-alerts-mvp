# ACTION PLAN v3.0 — EMBER APEX (LEAN)

> **Goal:** Add 2 high-signal intelligence layers to the existing BTC alert system.
> **Constraint:** Zero paid APIs. Minimal new code. Ship fast.
> **Created:** 2026-02-18

---

## Progress Tracker

| Phase | Name | Status | Time |
|:------|:-----|:-------|:-----|
| 0 | Infrastructure Preconditions | ✅ DONE | — |
| 1 | Squeeze Detector | ✅ DONE | 30 min |
| 2 | AI Sentiment | ✅ DONE | 30 min |
| 3 | Wiring & Error Handling | ✅ DONE | 30 min |

**That's it. 3 phases. ~90 minutes total.**

---

## What Changed From the Old Plan

Removed 8 phases that added complexity for marginal signal:

| Cut | Why |
|:----|:----|
| Volume Profile / POC | POC shifts too fast on 5m/15m BTC to be actionable |
| Liquidity Walls | REST orderbook snapshots every 5 min = stale noise, not real wall data |
| Macro Correlation (DXY/Gold) | DXY on 5m candles is noise. Macro matters on daily, not intraday |
| Confluence Heatmap | With 2 layers, a heatmap is just a list |
| Dashboard Upgrade | Polish later, ship first |
| Score Recalibration | Not needed — we're only adding ±12 pts, not ±24 |
| Historical Backtest | Separate project. Do it after v3 ships |
| Observability Phase | Just use `logging.getLogger(__name__)` inline. Not a phase |

---

## Architecture (What v3 Actually Adds)

```
EXISTING SYSTEM (untouched)          NEW (intelligence/)
──────────────────────────           ───────────────────
collectors/                          intelligence/
├ price.py                           ├ __init__.py        (IntelligenceBundle dataclass)
├ social.py (headlines)  ──────────► ├ sentiment.py       (VADER + crypto lexicon)
├ flows.py                           └ squeeze.py         (TTM Squeeze on candles)
├ derivatives.py
                                     app.py changes:
engine.py                            └ _collect_intelligence()  (~30 lines)
└ compute_score(..., intel=Bundle)     wraps both layers in try/except
                                       returns Bundle with whatever succeeded
```

**New files:** 2 (`intelligence/squeeze.py`, `intelligence/sentiment.py`)
**Modified files:** 3 (`intelligence/__init__.py`, `engine.py`, `app.py`)
**New dependency:** 1 (`vaderSentiment>=3.3`)
**New API calls:** 0

---

## Phase 0: Infrastructure ✅ DONE

Already completed. No action needed.

- [x] `AlertScore.context: Dict` field exists
- [x] `IntelligenceBundle` dataclass in `intelligence/__init__.py`
- [x] `compute_score()` accepts `intel: Optional[IntelligenceBundle]`
- [x] `INTELLIGENCE_FLAGS` dict in `config.py`
- [x] Yahoo budget fix applied

---

## Phase 1: Squeeze Detector

> BB contracts inside KC = coiled spring. Release = explosive move.
> - `SQUEEZE_FIRE` = just released → **+8 pts** (this is the money signal)
> - `SQUEEZE_ON` = coiling, no points yet
> - `NONE` = normal

**Status:** Core `intelligence/squeeze.py` exists. Needs wiring + tests.

### Tasks

#### 1.1 — `intelligence/squeeze.py` ✅ EXISTS

Already has `keltner_channels()` and `detect_squeeze()`. No changes needed.

Returns: `{"state": "SQUEEZE_ON"|"SQUEEZE_FIRE"|"NONE", "pts": int, "bb_width": float, "kc_width": float}`

#### 1.2 — Integration in `engine.py` ✅ EXISTS

Already has the `# --- Intelligence Layer: Squeeze ---` block in `compute_score()`.

#### 1.3 — Wire in `app.py`

Add this where candles are available:

```python
from intelligence.squeeze import detect_squeeze

if INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
    try:
        intel.squeeze = detect_squeeze(candles)
    except Exception as e:
        logger.warning(f"Squeeze failed: {e}")
```

#### 1.4 — Tests (`tests/test_squeeze.py`)

4 test cases, nothing fancy:

```python
def test_squeeze_on():        # BB inside KC → SQUEEZE_ON
def test_squeeze_fire():      # was inside, now outside → SQUEEZE_FIRE, pts=8
def test_squeeze_none():      # normal volatility → NONE
def test_short_candles():     # <22 candles → graceful NONE
```

```bash
PYTHONPATH=. python -m pytest tests/test_squeeze.py -v
```

---

## Phase 2: AI Sentiment

> VADER scores headlines -1 to +1 with a crypto-extended lexicon.
> - Composite > 0.3 → `SENTIMENT_BULL` **+4 pts**
> - Composite < -0.3 → `SENTIMENT_BEAR` **-4 pts**
> - Falls back to existing keyword matching if VADER not installed.

**Status:** Core `intelligence/sentiment.py` exists. Needs wiring + tests.

### Tasks

#### 2.1 — Install dependency

```bash
pip install vaderSentiment>=3.3
# Add to requirements.txt: vaderSentiment>=3.3
```

#### 2.2 — `intelligence/sentiment.py` ✅ EXISTS

Already has `SentimentEngine` class with crypto lexicon (30+ terms) and `analyze_sentiment()`.

Returns: `{"composite": float, "bullish_pct": int, "bearish_pct": int, "count": int, "fallback": bool}`

#### 2.3 — Integration in `engine.py`

Add after squeeze block:

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
        score_obj.context["sentiment"] = {
            "score": sent["composite"],
            "bull_pct": sent["bullish_pct"],
            "bear_pct": sent["bearish_pct"],
        }
```

Keep existing `NEWS_DICT` keyword logic as fallback.

#### 2.4 — Wire in `app.py`

Add after news/headlines are collected:

```python
from intelligence.sentiment import analyze_sentiment

if INTELLIGENCE_FLAGS.get("sentiment_enabled", True) and news:
    try:
        intel.sentiment = analyze_sentiment(news)
    except Exception as e:
        logger.warning(f"Sentiment failed: {e}")
```

#### 2.5 — Tests (`tests/test_sentiment.py`)

5 test cases:

```python
def test_bullish_headline():    # "Bitcoin ETF approved" → positive
def test_bearish_headline():    # "Exchange hacked funds stolen" → negative
def test_mixed_neutral():       # mixed bag → near zero
def test_empty_list():          # [] → graceful default
def test_vader_missing():       # mock ImportError → fallback=True
```

```bash
PYTHONPATH=. python -m pytest tests/test_sentiment.py -v
```

---

## Phase 3: Wiring & Error Handling

> One function in `app.py` that calls both layers safely. That's it.

### Tasks

#### 3.1 — Create `_collect_intelligence()` in `app.py`

One function, ~30 lines. Catches all errors per-layer:

```python
def _collect_intelligence(candles, news, btc_price):
    """Call all intelligence layers. Never crashes. Returns whatever succeeded."""
    intel = IntelligenceBundle()
    degraded = []

    # Squeeze
    if INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
        try:
            intel.squeeze = detect_squeeze(candles)
        except Exception as e:
            logger.warning(f"Squeeze degraded: {e}")
            degraded.append("squeeze")

    # Sentiment
    if INTELLIGENCE_FLAGS.get("sentiment_enabled", True) and news:
        try:
            intel.sentiment = analyze_sentiment(news)
        except Exception as e:
            logger.warning(f"Sentiment degraded: {e}")
            degraded.append("sentiment")

    if degraded:
        logger.info(f"Intelligence degraded layers: {degraded}")

    return intel
```

#### 3.2 — Call it in the main loop

Replace any existing per-layer calls with:

```python
intel = _collect_intelligence(candles, news, btc_price)
score = compute_score(..., intel=intel)
```

#### 3.3 — Enrich alert message

Add to `_format_alert()` — only show what exists:

```python
intel_lines = []
if score.context.get("squeeze"):
    intel_lines.append(f"Squeeze: {score.context['squeeze']}")
if score.context.get("sentiment"):
    s = score.context["sentiment"]
    intel_lines.append(f"Sentiment: {s['score']:.2f} ({s['bull_pct']}% bull)")
if intel_lines:
    msg += "\n🧠 Intel:\n" + "\n".join(f"  {l}" for l in intel_lines)
```

#### 3.4 — Quick smoke test

```bash
PYTHONPATH=. python app.py --once
# Should see intelligence context in alert output, no crashes
```

---

## Point Budget

| Source | Max + | Max - |
|:-------|:------|:------|
| v2.0 existing | ~+58 | ~-62 |
| Squeeze (FIRE) | +8 | 0 |
| Sentiment | +4 | -4 |
| **v3.0 total** | **~+70** | **~-66** |

v2 thresholds stay valid. No recalibration needed.

---

## Config Additions (all in `config.py`)

```python
SQUEEZE = {"bb_period": 20, "bb_std": 2.0, "kc_period": 20, "kc_atr_mult": 1.5, "fire_bonus_pts": 8}
SENTIMENT = {"strong_threshold": 0.3, "bull_pts": 4, "bear_pts": -4, "max_headlines": 50}
```

---

## Verification Checklist

```bash
# All tests
PYTHONPATH=. python -m pytest tests/ -v

# Phase-specific
PYTHONPATH=. python -m pytest tests/test_preconditions.py -v   # P0
PYTHONPATH=. python -m pytest tests/test_squeeze.py -v         # P1
PYTHONPATH=. python -m pytest tests/test_sentiment.py -v       # P2

# Smoke
PYTHONPATH=. python app.py --once
```

---

## Definition of Done (v3.0)

- [x] `detect_squeeze()` wired into main loop via `_collect_intelligence()`
- [x] `analyze_sentiment()` wired into main loop via `_collect_intelligence()`
- [x] `compute_score()` receives `IntelligenceBundle`, adds pts when present
- [x] Each layer wrapped in `try/except` — one failure never crashes the system
- [x] Telegram alerts show intelligence context when available
- [x] `INTELLIGENCE_FLAGS` can disable each layer independently
- [x] All tests pass
- [x] `vaderSentiment` in `requirements.txt`
- [x] Zero paid APIs

---

_Single source of truth for v3.0. 3 phases. ~150 lines of new code. Ship it._
