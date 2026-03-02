# Phase Checkups — Implementation Instructions (Phases 10–27)

> **Purpose:** Tell an implementing agent exactly what is broken or missing and how to fix it.
> **Scope:** Phases 10–27 only. Do not go beyond Phase 27.
> **Last Audited:** 2026-03-02 (full codebase read, every fix below is confirmed against actual code)

---

## STATUS OVERVIEW

| Phase Range | Status |
|-------------|--------|
| Phases 10–26 | ✅ All items confirmed implemented. No action required. |
| Phase 27 | ⚠️ 3 confirmed gaps. Instructions below. |

---

## PHASE 27 — 3 ITEMS TO FIX

### FIX 1 — CRITICAL: `alert.confidence_score` AttributeError in `app.py`

**What is broken:**
`app.py` line 370 references `alert.confidence_score` on an `AlertScore` object. The `AlertScore` dataclass (`intelligence/__init__.py:21`) only has a field named `confidence`, not `confidence_score`. Every time a non-NEUTRAL alert fires and is passed to `portfolio.on_alert()`, this raises `AttributeError: 'AlertScore' object has no attribute 'confidence_score'`, silently caught by the outer try/except, and the portfolio trade is never recorded.

**File:** `app.py`

**Find this exact line (around line 370):**
```python
                confidence=int(alert.confidence_score or 0),
```

**Replace it with:**
```python
                confidence=int(alert.confidence or 0),
```

**Verify:**
```bash
python -c "
from intelligence import AlertScore
a = AlertScore.__new__(AlertScore)
a.confidence = 72
print(int(a.confidence or 0))  # must print 72
print('PASS')
"
python app.py --once
# Should run with no AttributeError in logs
```

---

### FIX 2 — HIGH: 4h candles never fetched, Macro Veto silently disabled

**What is broken:**
`engine.py` has a Phase 27 macro veto that checks 4h trend bias before allowing a 5m/15m signal (engine.py ~line 451):
```python
if is_ltf and candles_4h and len(candles_4h) >= 30:
    bias_4h = _trend_bias(candles_4h)
```
But `collectors/price.py:fetch_btc_multi_timeframe_candles()` only defines timeframes `5m`, `15m`, `1h` in its `frames` dict (lines 206–210). So `btc_tf.get("4h", [])` in `app.py:274` is always an empty list. The macro veto's 4h guard fires immediately and the veto is **completely skipped every run**.

**File:** `collectors/price.py`

**Find this exact block (lines 205–210):**
```python
def fetch_btc_multi_timeframe_candles(budget: BudgetManager, limit: int = 120) -> Dict[str, List[Candle]]:
    frames = {
        "5m": {"kraken": 5, "bybit": "5", "binance": "5m", "coinbase": 300, "bitstamp": 300},
        "15m": {"kraken": 15, "bybit": "15", "binance": "15m", "coinbase": 900, "bitstamp": 900},
        "1h": {"kraken": 60, "bybit": "60", "binance": "1h", "coinbase": 3600, "bitstamp": 3600},
    }
```

**Replace it with (add the `"4h"` entry):**
```python
def fetch_btc_multi_timeframe_candles(budget: BudgetManager, limit: int = 120) -> Dict[str, List[Candle]]:
    frames = {
        "5m": {"kraken": 5, "bybit": "5", "binance": "5m", "coinbase": 300, "bitstamp": 300},
        "15m": {"kraken": 15, "bybit": "15", "binance": "15m", "coinbase": 900, "bitstamp": 900},
        "1h": {"kraken": 60, "bybit": "60", "binance": "1h", "coinbase": 3600, "bitstamp": 3600},
        "4h": {"kraken": 240, "bybit": "240", "binance": "4h", "coinbase": 14400, "bitstamp": 14400},
    }
```

Do not change anything else in the function. The rest of the loop already handles the new key automatically.

**Verify:**
```bash
python -c "
from collectors.price import fetch_btc_multi_timeframe_candles
from collectors.base import BudgetManager
bm = BudgetManager()
tf = fetch_btc_multi_timeframe_candles(bm, limit=35)
assert '4h' in tf, 'FAIL: 4h key missing'
assert len(tf['4h']) >= 30, f'FAIL: only {len(tf[\"4h\"])} 4h candles'
print(f'4h candles: {len(tf[\"4h\"])}  PASS')
"
```

---

### FIX 3 — MEDIUM: `confluence_score` missing from `decision_trace`

**What is broken:**
Phase 27 requires the signal engine to produce a `confluence_score` key inside the `decision_trace` JSON (Phase_27.md verification checklist). Currently the rubric score lives at `decision_trace["rubric"]["score"]` but there is no top-level `decision_trace["confluence_score"]`. The JSONL logs and any downstream consumer reading `decision_trace.confluence_score` will get `None`.

**File:** `engine.py`

**Find this exact line (around line 444):**
```python
    trace["rubric"] = {"score": rubric_score, "details": rubric_details}
```

**Insert one line immediately after it:**
```python
    trace["rubric"] = {"score": rubric_score, "details": rubric_details}
    trace["confluence_score"] = rubric_score
```

Do not modify `rubric_score`, `rubric_details`, or anything else in that block.

**Verify:**
```bash
python app.py --once
python -c "
import json
lines = open('logs/pid-129-alerts.jsonl').read().strip().splitlines()
a = json.loads(lines[-1])
cs = (a.get('decision_trace') or {}).get('confluence_score')
print(f'confluence_score = {cs}')
assert cs is not None, 'FAIL: confluence_score missing'
print('PASS')
"
```

---

## FULL VERIFICATION (run after all 3 fixes)

```bash
# 1. Engine and config import cleanly
python -c "from engine import compute_score; from config import validate_config; validate_config(); print('Imports OK')"

# 2. One full cycle with no errors
python app.py --once

# 3. Check last alert for all required fields
python -c "
import json
a = json.loads(open('logs/pid-129-alerts.jsonl').readlines()[-1])
tr = a.get('decision_trace', {})
checks = {
    'confidence':       a.get('confidence'),
    'tier':             a.get('tier'),
    'direction':        a.get('direction'),
    'rr_ratio':         a.get('rr_ratio'),
    'confluence_score': tr.get('confluence_score'),
    'rubric':           tr.get('rubric'),
    'blockers':         tr.get('blockers'),
}
for k, v in checks.items():
    status = 'OK' if v is not None else 'MISSING'
    print(f'  {k:<20} {status}  ({v})')
"

# 4. Dashboard server starts without error
python scripts/pid-129/dashboard_server.py &
# Open http://localhost:8000 — should show live BTC price, no red errors
```

---

## DASHBOARD HEALTH CHECKLIST

The dashboard at `http://localhost:8000` should show all of the following. If any are broken, check the WebSocket payload from `dashboard_server.py:get_dashboard_data()`.

| Panel / Element | Expected | Server Key |
|----------------|----------|------------|
| Live BTC price | Updates every 5s | `orderbook.mid` (from `data/last_cycle.json`) |
| Confidence score | 0–100 integer | `alerts[].confidence` |
| Tier badge | A+ / B / WATCH / NO-TRADE | `alerts[].tier` |
| Direction | LONG / SHORT / NEUTRAL | `alerts[].direction` |
| R:R ratio | e.g. 2.3 | `alerts[].rr_ratio` |
| Regime badge | trend / range / chop | `alerts[].regime` |
| Kelly % tile | Live updating | `stats.kelly_pct` |
| Circuit breaker | Red lockout banner when `active=true` | `circuit_breaker.active` |
| Recent signals table | Last 10 alerts | `alerts[]` array |
| Win rate | % | `stats.win_rate` |
| Profit factor | number | `stats.profit_factor` |
| Session stats | asia/london/ny win rates | `stats.session_stats` |
| Regime stats | trend/range/chop win rates | `stats.regime_stats` |
| Execution modal | Opens on signal click, shows entry/stop/TP | `alerts[].entry_zone` etc |

If the dashboard shows "Data Stale" or "Risk Gate RED" when the engine is running: confirm `data/last_cycle.json` exists and has a timestamp within the last 2 minutes. The server reads this file for engine liveness (not the JSONL log).

---

## WHAT IS ALREADY DONE (do not re-implement)

Phases 10–26 are fully implemented and tested. The following are confirmed working:

- All 13+ intelligence probes wired in engine.py (structure, sweeps, vwap, volume_impulse, oi_classifier, auto_rr, squeeze, sentiment, volume_profile, liquidity, macro_correlation, recipes, detectors)
- min_rr enforcement gate before signal publish (engine.py ~line 516)
- Phase 27 vetoes in engine.py: macro (1h+4h), order-flow (taker ratio), chop-zone (value area) — all three gate signals via the `blockers` list
- Multi-provider fallback chain in all collectors (price/derivatives/flows) with BudgetManager
- Engine heartbeat (`data/last_cycle.json`) with btc_price written by app.py every cycle
- Dashboard reads heartbeat for BTC price and engine liveness (dashboard_server.py ~line 676)
- Circuit breaker banner + execute button lock when active
- Kelly% on Live Tape
- Session stats and regime stats in `_portfolio_stats()`
- SCORE_MULTIPLIER = 7.0x normalization
- Confluence rubric (A+/B tier gate, 6-point scale)
