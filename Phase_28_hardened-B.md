# Phase 28-B: Dashboard Transformation — "One-Click Edge"

**Goal:** Transform EMBER COMMAND from a sprawling 12-section scroll into a singular, perfectly calibrated Bitcoin futures dashboard where a single glance + single click yields a mathematically verified, high-confidence LONG or SHORT play.

**Status:** SPEC READY — awaiting implementation
**Author:** Claude Opus 4.6 analysis session, 2026-03-03
**Depends on:** Phase 28 (hardening complete)

---

## Problem Statement

The current dashboard has **good bones but critical UX and data problems**:

1. **12+ scrollable sections** — a trader must scroll 6 screens to reach a decision. Opposite of "one-click."
2. **Confluence Radar derives state from reason_codes only** — probes with data but no emitted code show gray (⚫). The radar looks dead even when probes are active.
3. **Stale signals displayed without auto-invalidation** — Best Long can be 713 minutes old with no mechanism to expire it.
4. **Rich backend data never surfaces** — the 6-point confluence rubric, score breakdown, recipe trade plans, degraded probe flags, HTF confirmation status are all computed but invisible.
5. **No 4H/Daily bias layer** — the most important directional filter for swing structure is absent.
6. **"Loading..." sections** — Timeframe Edge Scoreboard and Confidence Calibration never populate (JS bug).
7. **No CVD, no macro event calendar** — real gaps in data collection.
8. **Kelly/edge stats on tiny sample** — no minimum sample gate before influencing sizing.

---

## Design Philosophy

### The "Command Screen" Principle
A fighter pilot's HUD doesn't scroll. Everything needed for a kill-or-no-kill decision is in one viewport. EMBER COMMAND should work the same way:

- **Above the fold (no scroll):** Current price, direction verdict, confluence score, gate status, execute button
- **Below the fold (optional detail):** Supporting evidence, historical performance, chart

### The "Traffic Light" Decision Model
The dashboard should answer ONE question: **"Should I trade right now, and which direction?"**

- **GREEN:** High-confidence setup detected. All gates pass. One-click execute available.
- **AMBER:** Setup exists but blocked by one or more gates. Shows what's missing.
- **RED:** No valid setup. System says WAIT. No execute button visible.

---

## Implementation Plan

### TIER 1 — Critical Fixes (Do First)

#### 1.1 Fix Confluence Radar to Read `cached_context` Directly
**File:** `dashboard_server.py` (HTML/JS section)
**Problem:** Radar only fires from `reason_codes` string matching. If a probe produces data but doesn't emit a code, it shows gray.
**Fix:** Change radar logic to derive probe state from `cached_context` fields:

```
Squeeze:    ctx.squeeze.state === 'SQUEEZE_FIRE' → 🟢, 'SQUEEZE_ON' → 🟡
Momentum:   ctx.volume_impulse.rvol > 1.5 → 🟢, < 0.5 → 🔴
Funding:    ctx.derivatives.funding_rate < -0.01 → 🟢(long), > 0.03 → 🔴
Gold Macro: ctx.macro_correlation.gold === 'rising' → 🟢, 'falling' → 🔴
Fear&Greed: ctx.sentiment.score < -0.5 → 🟢(fear=buy), > 0.5 → 🔴(greed=sell)
Order Book: ctx.liquidity.bid_walls > ctx.liquidity.ask_walls * 1.3 → 🟢
OI/Basis:   ctx.derivatives.oi_change_pct > 2 → 🟢, basis logic
Structure:  ctx.structure.event contains 'BULL' → 🟢, 'BEAR' → 🔴
Levels:     ctx.session_levels proximity check → 🟢/🔴
AVWAP:      ctx.avwap.position === 'above' → 🟢, 'below' → 🔴
VP Status:  ctx.volume_profile.near_poc → 🟡, above_value → 🟢
Auto R:R:   ctx.auto_rr.rr > 2.0 → 🟢, < 1.0 → 🔴
Trend(HTF): Check htf_aligned code presence + structure.trend
ML Model:   Check ML_CONFIDENCE_BOOST code
DXY Macro:  ctx.macro_correlation.dxy === 'falling' → 🟢(for longs)
```

**Why first:** The radar is the heart of the system. If it looks dead, the whole dashboard looks broken.

#### 1.2 Auto-Invalidate Stale Signals
**File:** `dashboard_server.py` → `_compute_profit_preflight()`
**Problem:** Best Long/Short candidates persist for 700+ minutes.
**Fix:**
- Add `MAX_SIGNAL_AGE_SECONDS = 1800` (30 minutes) to config.py
- In `_compute_profit_preflight()`, filter out candidates older than MAX_SIGNAL_AGE_SECONDS
- If best candidate is stale, set `operator_decision = "WAIT"` with reason "No fresh signals"
- On frontend: don't render stale candidates at all — show "Scanning for fresh setup..." instead

#### 1.3 Fix "Loading..." Sections
**File:** `dashboard_server.py` (JS section)
**Problem:** Timeframe Edge Scoreboard and Confidence Calibration show "Loading..." forever.
**Fix:** The JS that populates these tables likely has a bug where `stats.tf_stats` or `stats.recipe_stats` is undefined or empty on first load. Add null checks and render "No data yet (need 5+ trades)" if empty.

#### 1.4 Surface the 6-Point Confluence Rubric
**File:** `dashboard_server.py` (backend + HTML)
**Problem:** The rubric `{structure, location, anchors, derivatives, momentum, volatility}` is computed in engine.py but never sent to dashboard.
**Fix:**
- In `get_dashboard_data()` or `_compute_profit_preflight()`, extract `decision_trace.rubric` from the best candidate alert
- Send it in the WebSocket payload under `profit_preflight.rubric`
- Render as a 6-segment visual bar in the Verdict Center (each segment lights up green when the category contributes)

#### 1.5 Add Score Breakdown Visualization
**File:** `dashboard_server.py` (HTML)
**Problem:** `score_breakdown` (trend_alignment, momentum, volatility, volume, htf, penalty) is in every alert but invisible.
**Fix:** Render as a horizontal stacked bar or 6-cell mini-grid next to the confidence number in candidate cards. Color: green for positive, red for penalty.

---

### TIER 2 — Layout Consolidation (The Big UX Win)

#### 2.1 Restructure to Single-Viewport Command Screen
**Current layout (scrolling):**
```
[Live Tape]           — 3 rows of stat cards
[Trade Checklist]     — static checkboxes
[Best Long/Short]     — two candidate cards
[Verdict Center]      — price, key levels, radar, safety, execute
[Chart]               — TradingView embed
[Execution Copilot]   — position management
[Execution Matrix]    — 5m/15m/1h alignment table
[Performance]         — stats grid
[TF Scoreboard]       — Loading...
[Confidence Cal]      — Loading...
[Active Lifecycle]    — trade table
[Recent Signals]      — signal table
[Active Signals]      — empty
[Intelligence Report] — morning briefing text
```

**Proposed layout (single viewport + expandable):**
```
┌──────────────────────────────────────────────────────────────────┐
│ HEADER: EMBER COMMAND | BTC $66,682 ▼ | Live Feed: ONLINE      │
├────────────────────┬─────────────────────────────────────────────┤
│                    │                                             │
│  VERDICT PANEL     │  CONTEXT PANEL                              │
│  (Left ~35%)       │  (Right ~65%)                               │
│                    │                                             │
│  Direction: LONG   │  ┌─ Tape Strip ─────────────────────────┐  │
│  Confidence: 85    │  │ RVol 0.78x | Spread 2.7 | OI +0.11% │  │
│  Gate: GREEN       │  │ Funding 0.007% | Taker 1.62 | F&G 52 │  │
│                    │  └───────────────────────────────────────┘  │
│  ┌─ Rubric ─────┐ │                                             │
│  │ ■ Structure  │ │  ┌─ Confluence Radar ─────────────────────┐ │
│  │ ■ Location   │ │  │ ████████████░░░░░ 9/15 STRONG          │ │
│  │ ■ Anchors    │ │  │ 🟢Squeeze 🟢Momentum 🟢Structure ...  │ │
│  │ ■ Derivatives│ │  └───────────────────────────────────────┘  │
│  │ ■ Momentum   │ │                                             │
│  │ □ Volatility │ │  ┌─ Key Levels ──────────────────────────┐  │
│  └──────────────┘ │  │ PDH 70,100  POC 68,989  PDL 65,269   │  │
│                    │  │ VAH 69,810  AVWAP 66,545 ▲  VAL 67,298│ │
│  Entry: 67,000     │  │ Structure: BOS_BULL | Liq: EQH        │  │
│  Stop:  66,600     │  └───────────────────────────────────────┘  │
│  TP1:   67,720     │                                             │
│  R:R:   1.80       │  ┌─ Execution Matrix (compact) ──────────┐ │
│  Risk:  0.77%      │  │ 1h: LONG B 23 | 15m: — 92 | 5m: LONG │ │
│                    │  │        A+ 80  | Regime: trend          │  │
│  ┌──────────────┐ │  └───────────────────────────────────────┘  │
│  │ 🟢 EXECUTE   │ │                                             │
│  │   LONG       │ │  ┌─ Position Copilot ─────────────────────┐ │
│  └──────────────┘ │  │ SHORT @ $66,509 | PnL: -$23 (-0.33%)  │  │
│                    │  │ ⚠️ PATIENCE — within noise range       │  │
│  Safety: ✅✅✅✅✅ │  └───────────────────────────────────────┘  │
│                    │                                             │
├────────────────────┴─────────────────────────────────────────────┤
│ [▸ Chart] [▸ Performance] [▸ Signals] [▸ Intelligence Report]   │
│ (collapsible accordion panels — hidden by default)              │
└──────────────────────────────────────────────────────────────────┘
```

**Key changes:**
- Everything above the fold — no scrolling needed for the trade decision
- Verdict Panel (left) = the "what to do" answer
- Context Panel (right) = the "why" evidence
- Chart, Performance, Signals, Intelligence Report become **collapsible accordion panels** below
- Remove the redundant Trade Checklist (it's duplicated by Trade Safety)
- Remove "Active Signals" section (always empty, redundant with Best Long/Short)
- Merge Performance Metrics + TF Scoreboard + Confidence Calibration into one accordion

#### 2.2 Compact Tape Strip
**Current:** 3 rows of 6 cards each (18 stat cards).
**Proposed:** Single horizontal strip with only the 8 most actionable metrics:
```
BTC $66,682 | Spread 2.7 | RVol 0.78x | Taker 1.62 | Funding 0.007% | OI Δ +0.11% | F&G 52 | Risk: AMBER
```
Balance, Win Rate, Kelly %, Avg R move to the Performance accordion.

#### 2.3 Compact Execution Matrix
**Current:** Full table with 3 columns of detailed data.
**Proposed:** Single row showing alignment at a glance:
```
1h LONG (B·23) → 15m NO-TRADE (—·92) → 5m LONG (A+·80)
Regime: trend | Session: london | Playbook: 1h=bias · 15m=setup · 5m=trigger
```
If all 3 agree → show green "ALIGNED". If conflict → show amber/red with the conflict.

---

### TIER 3 — New Data Layers

#### 3.1 Add 4H Bias to Engine Output
**Files:** `engine.py`, `intelligence/structure.py`
**Problem:** 4H candles are fetched (`candles_4h`) but no 4H structure is surfaced.
**Fix:**
- In `engine.py compute_score()`, after calling structure probe on 5m/15m/1h, also call it on 4h candles
- Store result in `decision_trace.context.structure_4h = {trend, event, last_pivot_high, last_pivot_low}`
- Add to alert `reason_codes`: `HTF_4H_BULLISH` / `HTF_4H_BEARISH`
- Dashboard: show 4H bias in Execution Matrix and as a hard gate in Verdict Panel
- **Gate rule:** If 4H trend opposes signal direction → AMBER gate, warn "Against 4H trend"

#### 3.2 Add Fear & Greed Numeric to Tape
**Problem:** F&G shows in radar but not as a number in the tape strip.
**Fix:** Already in `cached_context.sentiment.score` — extract and display as a 0-100 value (convert from -1/+1 range) in the tape strip. Color: green < 25 (fear), red > 75 (greed).

#### 3.3 Add Degraded Probes Indicator
**File:** `dashboard_server.py`
**Problem:** When probes fail (API timeout, stale data), `decision_trace.degraded` is set but invisible.
**Fix:** If `degraded` array is non-empty, show a yellow warning badge next to confluence radar: "⚠️ 2 probes degraded: candles, sentiment". Reduces false confidence in a signal with missing data.

#### 3.4 Add Minimum Sample Gate for Edge Stats
**File:** `dashboard_server.py` → `_portfolio_stats()`
**Problem:** Kelly %, Win Rate, Avg R computed on 2 trades — statistically meaningless.
**Fix:**
- If `total_trades < 20`, display stats grayed out with "(N trades — need 20+ for significance)"
- If `total_trades < 20`, Kelly % should show "N/A" instead of influencing position sizing
- Recipe-specific stats need 10+ trades per recipe before showing win rate

#### 3.5 Add CVD (Cumulative Volume Delta) — NEW DATA COLLECTION
**Files:** `collectors/`, `intelligence/`, `engine.py`
**Problem:** CVD is not collected anywhere in the codebase. Taker ratio gives a hint but CVD divergences are a key signal.
**Fix (future phase — requires new collector):**
- Add CVD calculation to `collectors/` — aggregate buy/sell volume over last N candles
- Create `intelligence/cvd.py` probe — detect CVD divergences (price new high + CVD lower = bearish)
- Add to decision_trace and radar
- **Note:** This is a significant new feature. Consider Phase 29.

#### 3.6 Add Macro Event Calendar — NEW DATA SOURCE
**Problem:** No awareness of FOMC, CPI, jobs reports.
**Fix (future phase — requires external API):**
- Add `collectors/macro_calendar.py` — fetch from free API (e.g., ForexFactory scrape or investing.com API)
- Store next high-impact event timestamp
- Dashboard: show countdown "⚠️ FOMC in 2h14m" in tape strip
- Gate rule: If high-impact event within 30 minutes → AMBER gate, warn "Macro event imminent"
- **Note:** This is a significant new feature. Consider Phase 29.

---

### TIER 4 — Polish & Reliability

#### 4.1 WebSocket Reconnection Improvement
**Problem:** WS can disconnect silently, leaving stale data displayed.
**Fix:** Add exponential backoff reconnect with visual indicator (pulsing orange dot). Current reconnect exists but UX is unclear.

#### 4.2 Responsive Mobile View
**Problem:** Dashboard is designed for wide screens.
**Fix:** For mobile, show only the Verdict Panel (direction + gate + execute). Context panel accessible via swipe or tab. Low priority.

#### 4.3 Audio Alerts Enhancement
**Problem:** Chime plays on A+ alert but no differentiation.
**Fix:**
- Different tones for LONG vs SHORT
- No sound for NO-TRADE (current behavior is correct)
- Optional voice: "Long setup, A-plus, confidence 85"

---

## Implementation Order

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | 1.1 Fix Confluence Radar (read cached_context) | 2h | Critical — radar is the heart |
| P0 | 1.2 Auto-invalidate stale signals (30min max) | 1h | Critical — removes ghost signals |
| P0 | 1.3 Fix Loading... sections (JS null check) | 30min | Easy win — currently broken |
| P1 | 2.1 Restructure to single-viewport layout | 4h | Major UX — the transformation |
| P1 | 2.2 Compact tape strip (18 cards → 8 inline) | 1h | Cleaner, less scrolling |
| P1 | 2.3 Compact execution matrix (table → inline) | 1h | Less visual noise |
| P1 | 1.4 Surface 6-point confluence rubric | 1.5h | Shows WHY a setup is A+ |
| P1 | 1.5 Score breakdown visualization | 1h | Visual confidence decomposition |
| P2 | 3.1 Add 4H bias to engine + dashboard | 3h | Real directional edge improvement |
| P2 | 3.2 Add F&G numeric to tape | 30min | Easy data already exists |
| P2 | 3.3 Add degraded probes indicator | 30min | Trust calibration |
| P2 | 3.4 Minimum sample gate for stats | 1h | Prevents overconfidence |
| P3 | 3.5 CVD — new collector + probe | 4h+ | Phase 29 candidate |
| P3 | 3.6 Macro calendar — new data source | 4h+ | Phase 29 candidate |
| P3 | 4.1–4.3 Polish items | 2h | Nice-to-have |

**Total estimated effort for P0+P1:** ~11 hours
**Total estimated effort for P0+P1+P2:** ~16 hours

---

## Files Modified

| File | Changes |
|------|---------|
| `scripts/pid-129/dashboard_server.py` | Radar logic, layout HTML, JS updates, stale filter, rubric data |
| `engine.py` | Surface 4H structure in decision_trace, ensure rubric/breakdown in payload |
| `config.py` | Add MAX_SIGNAL_AGE_SECONDS = 1800 |
| `intelligence/structure.py` | 4H structure analysis (if not already running on 4H candles) |

---

## Success Criteria

1. Dashboard loads with **zero scroll needed** for a trade decision
2. Confluence Radar shows **accurate probe states** (no false grays)
3. No signal older than 30 minutes displayed as "best"
4. 6-point rubric visible — operator can see exactly which categories fired
5. Single green EXECUTE button = mathematically verified, all gates pass
6. "Loading..." sections eliminated
7. All existing tests pass (`PYTHONPATH=. python -m pytest tests/ -v`)

---

## What This Does NOT Change

- Engine scoring logic (no threshold changes)
- Alert JSONL format (backward compatible)
- Auto-tune / DNA system
- Collector infrastructure
- Paper trading / execution logic
- WebSocket protocol (additive fields only)

---

## Notes for Implementing AI

1. The dashboard HTML is **embedded as a string in `dashboard_server.py`** — it's one massive file. The HTML template is served inline.
2. The confluence radar JS is in the `connectWS()` handler — look for the `updateRadar` or probe-mapping logic.
3. `cached_context` is the key data source — it's a merged dict of the last alert's `decision_trace.context`. All probe data lives there.
4. The execute button modal has a 3-second countdown safety mechanism — preserve this.
5. Test with `python app.py --once` to generate a fresh alert, then check the dashboard reflects it within 2 seconds via WebSocket.
6. The `_light_alerts()` function strips heavy data — make sure any new fields you need are preserved through this filter.
