# Phase Checkups — Missing / Incomplete Items from Phases 10-26

> **Status:** WORKING DOCUMENT  
> **Last Updated:** 2026-03-01  
> **Purpose:** Track items from past phases that were documented but not fully implemented

---

## CRITICAL: Items That Affect Profitability Directly

| # | Issue | Phase Reference | Status | Impact |
|---|-------|-----------------|--------|--------|
| 1 | **min_rr NOT enforced in engine.py** | Phase 20:133-134 | ❌ NOT IMPLEMENTED | Trades execute with 0.67-0.82 R:R despite min_rr thresholds (1.35/1.25/1.15) |
| 2 | **Kelly % not displayed on Live Tape** | Phase 25:24, 331-360 | ⚠️ PARTIAL | Calculated in dashboard_server.py but not shown in Live Tape grid |
| 3 | **Circuit breaker shows in data but not prominent on dashboard** | Phase 26:78+ | ⚠️ PARTIAL | `circuit_breaker` in WS payload but no large "DO NOT TRADE" banner |
| 4 | **Session edge stats not displayed** | Phase 25:27 | ❌ NOT IMPLEMENTED | Session data collected but no per-session win rate shown |
| 5 | **Regime-specific win rates not shown** | Phase 25/26 | ❌ NOT IMPLEMENTED | Can't filter by regime (trend/range/chop) performance |

---

## Phase 10 — ✅ DONE

- Live BTC Price ✅
- Risk Gate (Trade Safety) ✅
- Equity Curve ✅
- Confluence Heatmap ✅
- Regime Detection ✅
- Execution Modal ✅

---

## Phase 11 — ✅ DONE

- Dead function removed ✅
- against_count tracked ✅
- Radar IDs added ✅
- WebSocket dynamic update ✅
- Net score display ✅

---

## Phase 12 — ✅ DONE

- trace["codes"] fix ✅
- Code mappings (HTF, FG, Derivatives, ML) ✅
- Live Orderbook ✅

---

## Phase 13 — ✅ DONE

- r_multiple field fix ✅
- Wall threshold 5.0→2.0 ✅
- ML threshold 35→20 ✅
- SQUEEZE_ON mapped ✅
- JSONL fields (action, rr_ratio, etc) ✅
- Execution Matrix entry/stop/TP ✅

---

## Phase 14 — ✅ DONE (All items implemented)

- Spread estimation ✅
- Momentum threshold 0.3→0.15 ✅
- Orderbook limit 50→200 ✅
- Funding thresholds fixed ✅
- OI/Basis thresholds lowered ✅
- Context fallback ✅
- Flow codes added ✅
- POC proximity 0.5%→1.5% ✅

---

## Phase 15 — ✅ DONE

- Provider fallback chain ✅
- Budget limits updated ✅
- OKX derivatives fallback ✅
- OKX orderbook fallback ✅
- OKX flows fallback ✅
- Yahoo delays ✅

---

## Phase 16 — ✅ DONE

- TIMEFRAME_RULES dict fix ✅
- fetch_orderbook(budget_manager) ✅
- Fallback constructors fixed ✅
- SHORT confidence abs() ✅
- Duplicate build_verdict_context removed ✅
- WS payload size reduced ✅
- Spread estimate 0.00002→0.00004 ✅
- Streak on zero fix ✅
- Risk Gate logic fix ✅

---

## Phase 17 — ✅ DONE

New intelligence modules created:
- intelligence/structure.py ✅
- intelligence/session_levels.py ✅
- intelligence/sweeps.py ✅
- intelligence/anchored_vwap.py ✅
- intelligence/volume_impulse.py ✅
- intelligence/oi_classifier.py ✅
- intelligence/auto_rr.py ✅
- Volume profile LVN enhancement ✅
- Engine wiring ✅
- Radar probe updates ✅

---

## Phase 18 — ✅ DONE (All items documented)

- Context fields expanded ✅
- Volume impulse polarity split ✅
- Key Levels panel ✅
- RVol + Vol Regime cells ✅
- Lifecycle limit to 10 ✅
- 15 Radar Probes ✅
- Confidence/Tier gating ✅
- Dashboard live data ✅
- Position size calculator ✅
- Lower confidence thresholds ✅
- Institutional Context Sentinel ✅

---

## Phase 19 — ✅ DONE (All 14 fixes documented)

All fixes marked as done in phase doc:
- FIX 12: Score normalization (SCORE_MULTIPLIER) ✅
- FIX 10: A+ tier guard ✅
- FIX 13: Graduated Execution Decision ✅
- FIX 14: Auto-close stale NEUTRAL trades ✅
- FIX 1-9, 11: Probe fixes ✅

---

## Phase 20 — ⚠️ PARTIALLY DONE

| Item | Status | Notes |
|------|--------|-------|
| Score calibration (FIX 1) | ✅ | SCORE_MULTIPLIER = 7.0 in engine.py |
| Probe diagnostics (FIX 2) | ✅ | Tooltips added |
| Recent Signals panel (FIX 3) | ✅ | Last 10 alerts table |
| System accuracy badge (FIX 4) | ✅ | Edge (last N) shown |
| **min_rr enforcement** | ❌ | **CRITICAL: Defined in config.py but NOT enforced in engine.py** |

### Phase 20 Known Issue
- The `min_rr` values are in `config.py`:
  ```python
  "5m":  {"min_rr": 1.35, ...}
  "15m": {"min_rr": 1.25, ...}
  "1h":  {"min_rr": 1.15, ...}
  ```
- But `engine.py` never checks `rr_ratio < min_rr` before allowing trades
- Result: Trades execute at 0.67-0.82 R:R despite thresholds

---

## Phase 21 — Status Unknown

> Not reviewed in detail yet

---

## Phase 22 — Status Unknown

> Not reviewed in detail yet

---

## Phase 23 — Status Unknown

> Not reviewed in detail yet

---

## Phase 24 — Status Unknown

> Not reviewed in detail yet

---

## Phase 25 — ⚠️ PARTIAL

| Item | Status | Notes |
|------|--------|-------|
| Vol regime extraction | ✅ | In dashboard_server.py |
| Auto-pilot muting | ✅ | Regime-based recipe suppression |
| Kelly calculation | ✅ | In _portfolio_stats() |
| Kelly display in Execute Modal | ✅ | Phase 25:360 shows Kelly in modal |
| Kelly NOT shown on Live Tape | ❌ | kelly_pct calculated but not in Live Tape grid |
| Session data in alerts | ✅ | `session` field in alerts |
| Regime data in alerts | ✅ | `regime` field in alerts |

---

## Phase 26 — ⚠️ PARTIAL

| Item | Status | Notes |
|------|--------|-------|
| Circuit breaker calculation | ✅ | DD > 8% or streak <= -4 |
| Circuit breaker in WS payload | ✅ | `circuit_breaker` key present |
| **Circuit breaker NOT prominently displayed** | ❌ | No large "STOP TRADING" banner |
| Data age tracking | ✅ | `data_age_seconds` in payload |

---

## Quick Wins to Implement

### 1. Enforce min_rr (HIGHEST PRIORITY)
**File:** `engine.py` - Add around line 470-480

```python
# After blockers are collected, before _tier_and_action call:
cfg = TIMEFRAME_RULES.get(timeframe, TIMEFRAME_RULES["5m"])
if rr < cfg.get("min_rr", 1.2):
    blockers.append(f"R:R {rr:.2f} below {cfg['min_rr']} threshold")
```

### 2. Add Kelly % to Live Tape
**File:** `generate_dashboard.py` - Add to live-grid section

```python
<div class="stat-card"><div class="stat-label">Kelly %</div><div id="live-kelly" class="live-value">--</div></div>
```

Then update JS to populate from `window._lastStats.kelly_pct`.

### 3. Add Large "WAIT" Indicator
**File:** `generate_dashboard.py` - Add prominent banner when:
- Confluence < 4 signals OR
- R:R < 1.2 OR  
- Circuit breaker active

### 4. Add Session Win Rates
**File:** `dashboard_server.py` - Add to _portfolio_stats()

Calculate win rate per session (asia/london/ny/weekend) from closed trades.

### 5. Add Regime Win Rates
**File:** `dashboard_server.py` - Add to _portfolio_stats()

Calculate win rate per regime (trend/range/chop) from closed trades.

---

## Testing Commands

```powershell
# Test engine imports
python -c "from engine import compute_score; print('Engine OK')"

# Test dashboard generation
python scripts/pid-129/generate_dashboard.py

# Test one cycle
python app.py --once

# Check recent alerts for R:R
python -c "import json; lines=open('logs/pid-129-alerts.jsonl').read().strip().splitlines(); a=json.loads(lines[-1]); print(f'RR: {a.get(\"rr_ratio\")}, Direction: {a.get(\"direction\")}')"

# Check min_rr config
python -c "from config import TIMEFRAME_RULES; print(TIMEFRAME_RULES)"
```

---

*This document will be updated as we review more phases and implement fixes.*
