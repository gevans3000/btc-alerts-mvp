# Phase Checkups — Missing / Incomplete Items from Phases 10-26

> **Status:** WORKING DOCUMENT  
> **Last Updated:** 2026-03-02  
> **Purpose:** Track items from past phases that were documented but not fully implemented

---

## CRITICAL: Items That Affect Profitability Directly

| # | Issue | Phase Reference | Status | Impact |
|---|-------|-----------------|--------|--------|
| 1 | **min_rr enforcement in engine.py** | Phase 20:133-134 | ✅ IMPLEMENTED | Trades below timeframe `min_rr` are now blocked before final signal publish |
| 2 | **Kelly % on Live Tape** | Phase 25:24, 331-360 | ✅ IMPLEMENTED | `kelly_pct` now shown in Live Tape grid as live-updating Kelly % |
| 3 | **Circuit breaker dashboard prominence** | Phase 26:78+ | ✅ IMPLEMENTED | Added large banner + execute button lock while circuit breaker is active |
| 4 | **Session edge stats** | Phase 25:27 | ✅ IMPLEMENTED (API) | Added per-session win-rate stats in `_portfolio_stats()` payload (`session_stats`) |
| 5 | **Regime-specific win rates** | Phase 25/26 | ✅ IMPLEMENTED (API) | Added per-regime win-rate stats in `_portfolio_stats()` payload (`regime_stats`) |

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
| **min_rr enforcement** | ✅ | Enforced in `engine.py`; signals below timeframe threshold are blocked |

### Phase 20 Resolution
- `engine.py` now checks computed `rr_ratio` against `TIMEFRAME_RULES[timeframe]["min_rr"]` before final publish.
- Alerts breaching threshold are marked `NO-TRADE` / `SKIP` with a blocker reason.

---

## Phase 21 — ✅ DONE

- Phase 21 doc marks complete (Premium UX/UI polish) ✅
- No open profitability carry-over identified from this phase ✅

---

## Phase 22 — ✅ DONE

- Phase 22 doc marks complete (recipes + confluence rubric) ✅
- No open profitability carry-over identified from this phase ✅

---

## Phase 23 — ✅ DONE

- Phase 23 doc marks complete (recipe-aware execution + MTF confirmation) ✅
- No open profitability carry-over identified from this phase ✅

---

## Phase 24 — ✅ DONE

- Phase 24 doc marks complete (backend rewrite + watcher/API/analytics/commands) ✅
- No open profitability carry-over identified from this phase ✅

---

## Phase 25 — ⚠️ PARTIAL

| Item | Status | Notes |
|------|--------|-------|
| Vol regime extraction | ✅ | In dashboard_server.py |
| Auto-pilot muting | ✅ | Regime-based recipe suppression |
| Kelly calculation | ✅ | In _portfolio_stats() |
| Kelly display in Execute Modal | ✅ | Phase 25:360 shows Kelly in modal |
| Kelly on Live Tape | ✅ | Added `live-kelly` tile bound to `data.stats.kelly_pct` in WS handler |
| Session data in alerts | ✅ | `session` field in alerts |
| Regime data in alerts | ✅ | `regime` field in alerts |

---

## Phase 26 — ⚠️ PARTIAL

| Item | Status | Notes |
|------|--------|-------|
| Circuit breaker calculation | ✅ | DD > 8% or streak <= -4 |
| Circuit breaker in WS payload | ✅ | `circuit_breaker` key present |
| **Circuit breaker prominence** | ✅ | Added large red lockout banner + execution button lock when active |
| Data age tracking | ✅ | `data_age_seconds` in payload |

---

## Quick Wins Implemented

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

Then update WS handler to populate from `data.stats.kelly_pct`.

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


## Parallel Merge Plan (Independent Workstreams)

> Goal: each stream can be implemented and merged independently with minimal conflict risk.

1. **Stream A — Engine R:R Gate** (`engine.py`)
   - Enforce `min_rr` blocker before tier/action finalization.
2. **Stream B — Dashboard Safety Signals** (`generate_dashboard.py`)
   - Add Live Tape Kelly tile + prominent circuit-breaker banner/execute lock.
3. **Stream C — Edge Attribution Analytics** (`dashboard_server.py`, optional small dashboard panel)
   - Add `session_stats` and `regime_stats` into `_portfolio_stats()` for performance filtering.

Merge order: **A → C → B** (backend schema first, UI binding last).

---

## What Most Improves Higher-Probability Trades (Priority)

1. **Hard-block low R:R trades** (min_rr enforcement) — immediate expectancy protection.
2. **Prominent circuit-breaker UI lockout** — prevents revenge trades during drawdown/streak stress.
3. **Session/regime win-rate visibility** — enables selective deployment only where edge is proven.
4. **Live Kelly on tape** — keeps sizing consistent with current edge quality.

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

## Phase 27 — ✅ DONE

- Strict Signal Filtration & Vetoes ✅
- API Fallback Rotation Pipeline (Binance → CoinGecko → CryptoCompare) ✅
- Signal Confluence Upgrade (Delta/CVD scoring) ✅
- Low-Footprint Execution (caching) ✅
- Confluence Score in decision_trace JSON ✅

---

*This document will be updated as we review more phases and implement fixes.*
