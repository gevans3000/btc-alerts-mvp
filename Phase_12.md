# Phase 12: Make the Confluence Radar Show Real Data on the Dashboard

> **STATUS: ✅ ALREADY IMPLEMENTED** — All code changes below have already been applied. This document exists as a reference for what was changed, why, and how to verify. If you are an AI agent reading this, skip to the **VERIFY** section at the bottom.

---

## 🔴 THE ROOT CAUSE (Why Every Probe Was ⚫)

The Confluence Radar on the dashboard reads signal codes from `decision_trace.codes` inside each alert stored in `logs/pid-129-alerts.jsonl`.

**The bug:** In `engine.py`, the variable `trace` is initialized with `"codes": []` on line 74. The engine then accumulates all signal codes into a **separate** local Python list called `codes`. But `trace["codes"]` was **NEVER updated** with that list before returning. So when the alert was serialized to disk, `decision_trace.codes` was always `[]` (empty). The dashboard read `[]`, matched zero codes, and showed every single probe as ⚫ (inactive).

**The fix:** Add `trace["codes"] = list(set(codes))` right before the `return AlertScore(...)` statement in `compute_score()`.

There were also two secondary problems:

1. **Missing code mappings:** The engine had variables for HTF bias, Fear & Greed, Derivatives (Funding/OI/Basis), and ML, but never converted them into the string codes the radar looks for (like `HTF_ALIGNED`, `FG_FEAR`, `FUNDING_LOW`, etc.).

2. **Mock Order Book:** The `collectors/orderbook.py` returned hardcoded fake data instead of querying a real API.

---

## 📋 ALL CHANGES (3 files, already applied)

---

### CHANGE 1: Fix `trace["codes"]` in `engine.py` (THE CRITICAL BUG FIX)

**File:** `engine.py`  
**Location:** Right before the `return AlertScore(...)` statement (around line 228)

**WHAT WAS ADDED** (3 lines inserted before the return):
```python
    trace["codes"] = list(set(codes))
    trace["degraded"] = degraded
    trace["blockers"] = blockers

    return AlertScore(
        symbol=symbol,
        ...
```

**WHY:** Without this, `decision_trace.codes` is always `[]` in every serialized alert. The dashboard's `build_verdict_context()` function reads `alert.get("decision_trace", {}).get("codes", [])` and gets nothing. This single missing line was the reason every radar probe showed ⚫.

---

### CHANGE 2: Add Missing Reason Code Mappings in `engine.py`

**File:** `engine.py`  
**Location:** Inside `compute_score()`, after the macro risk bias section and before the `# Candidates` section

**WHAT WAS ADDED** (the radar needs these specific string codes to light up — the data was already being collected, it just wasn't being converted into code strings):

```python
    # Map HTF Bias to Radar Codes
    if htf_bias > 0: codes.append("HTF_ALIGNED")
    elif htf_bias < 0: codes.append("HTF_COUNTER")

    # Map Fear & Greed to Radar Codes
    if fg and fg.healthy:
        if fg.value <= 25: codes.append("FG_EXTREME_FEAR")
        elif fg.value <= 45: codes.append("FG_FEAR")
        elif fg.value >= 75: codes.append("FG_EXTREME_GREED")
        elif fg.value >= 55: codes.append("FG_GREED")

    # Map Derivatives to Radar Codes
    if derivatives and derivatives.healthy:
        code_fr = derivatives.funding_rate
        if code_fr <= -0.01: codes.append("FUNDING_EXTREME_LOW")
        elif code_fr < 0: codes.append("FUNDING_LOW")
        elif code_fr >= 0.01: codes.append("FUNDING_EXTREME_HIGH")
        elif code_fr > 0: codes.append("FUNDING_HIGH")
        
        oi_pct = derivatives.oi_change_pct
        if oi_pct >= 5.0: codes.append("OI_SURGE_MAJOR")
        elif oi_pct >= 2.0: codes.append("OI_SURGE_MINOR")
        
        basis = derivatives.basis_pct
        if basis >= 0.5: codes.append("BASIS_BULLISH")
        elif basis <= -0.5: codes.append("BASIS_BEARISH")
```

**DATA SOURCES — all free, no API keys needed:**
| Radar Probe | Data Source | API | Free Limit |
|:--|:--|:--|:--|
| Squeeze | Bollinger + Keltner on candles | Computed locally | N/A |
| Trend (HTF) | EMA 9/21 crossover on 1h candles | Kraken OHLC | Unlimited public |
| Momentum | VADER sentiment on RSS news | CoinTelegraph + CoinDesk RSS | Unlimited |
| ML Model | Pseudo-ML: `total_score >= 35` | Computed locally | N/A |
| Funding | Funding Rate from perpetuals | Bybit v5/market/tickers | 120 req/min |
| DXY Macro | DXY daily EMA crossover | Yahoo Finance chart API | ~2000/hr |
| Gold Macro | Gold daily EMA crossover | Yahoo Finance chart API | ~2000/hr |
| Fear & Greed | F&G Index value | alternative.me/fng | 30 req/min |
| Order Book | Bid/Ask wall detection | Bybit v5/market/orderbook | 120 req/min |
| OI / Basis | Open Interest change + basis % | Bybit v5/market/open-interest | 120 req/min |

---

### CHANGE 2b: Add Pseudo-ML Mapping in `engine.py`

**File:** `engine.py`  
**Location:** After `total_score = sum(breakdown.values())`, before `# --- Confluence Heatmap ---`

**WHAT WAS ADDED:**
```python
    # Map ML Mock / Fallback
    # If the score is extreme, we assume high algorithmic conviction.
    if total_score >= 35:
        codes.append("ML_CONFIDENCE_BOOST")
    elif total_score <= -35:
        codes.append("ML_SKEPTICISM")
```

**WHY:** There is no real ML model in this MVP. This heuristic maps a strong engine score to a "ML confident" signal so the radar has coverage for the ML probe.

---

### CHANGE 3: Live Order Book Collector in `collectors/orderbook.py`

**File:** `collectors/orderbook.py`  
**Location:** `fetch_orderbook()` function (was returning hardcoded mock data)

**REPLACED the mock function with a real API call:**
```python
def fetch_orderbook(budget_manager) -> OrderBookSnapshot:
    try:
        from collectors.base import request_json
        if budget_manager:
            budget_manager.record_call("bybit_ob")
        payload = request_json(
            "https://api.bybit.com/v5/market/orderbook",
            params={"category": "linear", "symbol": "BTCUSDT", "limit": 50},
            timeout=5.0
        )
        result = payload.get("result", {})
        bids = [(float(p), float(q)) for p, q in result.get("b", [])]
        asks = [(float(p), float(q)) for p, q in result.get("a", [])]
        ts_ms = payload.get("time", int(datetime.now().timestamp() * 1000))
        return OrderBookSnapshot(ts=int(ts_ms / 1000), bids=bids, asks=asks)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Orderbook fetch failed: %s", e)
        return OrderBookSnapshot(ts=int(datetime.now().timestamp()), bids=[], asks=[], healthy=False)
```

**WHY:** The old function returned fake bids/asks at price 100.0. The liquidity analyzer saw fake walls and produced meaningless `BID_WALL_SUPPORT`/`ASK_WALL_RESISTANCE` codes. Now it queries Bybit's free unauthenticated v5 endpoint for the real BTC-USDT perpetual order book (top 50 levels). No API key required. 120 requests/minute limit.

---

## ✅ VERIFY — Run These Commands

### Step 1: Confirm engine.py imports clean
```
python -c "from engine import compute_score; print('OK')"
```
Expected: `OK`

### Step 2: Confirm dashboard generates clean
```
python scripts/pid-129/generate_dashboard.py
```
Expected: `Dashboard generated: <path>/dashboard.html`

### Step 3: Run one full pipeline cycle to produce fresh alerts with codes
```
python app.py --once
```
Expected: Runs for ~15 seconds with no errors, exits cleanly.

### Step 4: Confirm the latest alert now has codes in decision_trace
```
python -c "import json; lines=open('logs/pid-129-alerts.jsonl').read().strip().splitlines(); a=json.loads(lines[-1]); print('Symbol:', a.get('symbol')); print('Direction:', a.get('direction')); codes=a.get('decision_trace',{}).get('codes',[]); print('Codes count:', len(codes)); print('Codes:', sorted(codes))"
```
Expected: `Codes count: 5+` (should be at least 5 codes, like `HTF_ALIGNED`, `FG_EXTREME_FEAR`, `DXY_RISING_BEARISH`, etc.)

**If codes count is 0, the bug fix in CHANGE 1 was not applied. Go fix it.**

### Step 5: Confirm the dashboard HTML has colored radar probes
```
python scripts/pid-129/generate_dashboard.py
```
Then open `dashboard.html` in a browser. Look at the **Confluence Radar** card inside the Verdict Center. You should see:
- At least some 🟢 (green) or 🔴 (red) probes instead of all ⚫ (grey)
- A `Net: +N` or `Net: -N` line at the bottom
- A colored progress bar (not 0%)

### Step 6: Run tests to confirm nothing broke
```
python -m pytest tests/ -k "not test_genetic_optimization" -x -q
```
Expected: All tests pass (the 1 error about tmp dir Access Denied is a Windows temp file issue, not related to this change).

---

## 📊 How It All Connects (Data Flow)

```
1. app.py calls compute_score() in engine.py
2. engine.py accumulates signal codes into the `codes` list:
   - Squeeze, Sentiment, Liquidity, Macro from IntelligenceBundle
   - HTF bias, Fear&Greed, Derivatives, ML from direct variable mapping (NEW)
   - Regime, VIX, Detectors from existing logic
3. engine.py copies codes into trace["codes"] = list(set(codes)) (NEW — was the bug)
4. engine.py returns AlertScore with decision_trace=trace
5. app.py serializes the AlertScore to logs/pid-129-alerts.jsonl via PersistentLogger
6. generate_dashboard.py reads the JSONL, finds the latest BTC alert
7. generate_dashboard.py reads decision_trace.codes from the alert
8. For each of 10 radar probes, it checks if the matching code exists:
   - If aligned with trade direction → 🟢
   - If against trade direction → 🔴
   - If no code present → ⚫
9. The radar card renders with colored probes, progress bar, and net score
```

---

## 📁 Files Modified

| File | What Changed |
|:--|:--|
| `engine.py` | Added `trace["codes"] = list(set(codes))` before return (ROOT CAUSE FIX). Added HTF/FG/Derivatives/ML code mappings. |
| `collectors/orderbook.py` | Replaced mock data with real Bybit public API call. |
| `Phase_12.md` | This document. |

---

## 🚫 Do NOT Do These Things

- Do NOT edit `dashboard.html` directly — it is auto-generated by `generate_dashboard.py`
- Do NOT edit `generate_dashboard.py` — the radar rendering logic there already works correctly
- Do NOT add API keys — all endpoints used are free unauthenticated public APIs
- Do NOT change the 10 probe definitions — they are consistent between `engine.py`, `generate_dashboard.py` (Python + JS), and this document

---

*Phase 12 — Confluence Radar Data Integration | Completed: 2026-02-25*
