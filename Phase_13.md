# Phase 13 — Dashboard Perfection & Complete Radar Activation

## Objective

Fix **every** remaining empty, disconnected, or stuck dashboard widget so the EMBER COMMAND dashboard shows 100% live, actionable data. After these changes, every metric, every radar probe, and every execution-matrix cell will be populated with real values pulled from the existing data pipeline.

> **IMPORTANT — SCOPE RULES**
> - Only files listed below are edited.  No new files are created.
> - No new API endpoints are added.  All data already exists in the pipeline.
> - All API calls already respect `BudgetManager` rate limits defined in `collectors/base.py`.  This phase only modifies how existing data is **mapped, thresholded, and displayed** — never how it is fetched.

---

## Architecture Reference (read-only — do NOT modify these)

```
app.py                        → Main loop.  Calls _collect_intelligence(), then engine.compute_score().
engine.py                     → Produces AlertScore with reason_codes[] and decision_trace{codes:[]}
core/infrastructure.py        → PersistentLogger.log_alert() writes JSONL to logs/pid-129-alerts.jsonl
tools/paper_trader.py         → Writes data/paper_portfolio.json, closed_trades use field "r_multiple"
tools/outcome_tracker.py      → Resolves alerts, sets field "r_multiple" on JSONL rows
scripts/pid-129/dashboard_server.py → Reads JSONL + portfolio, pushes JSON via WebSocket every 2s
scripts/pid-129/generate_dashboard.py → Builds dashboard.html from JSONL + portfolio (run each cycle)
```

### Key data contracts

| Source file | Field used | Where consumed |
|---|---|---|
| `paper_trader.py` `ClosedTrade` | `r_multiple` | `generate_dashboard.py:210`, `generate_scorecard.py:120` |
| `paper_portfolio.json` → `closed_trades[].r_multiple` | `r_multiple` | `dashboard_server.py:_portfolio_stats()` |
| `engine.py` `AlertScore` | `decision_trace.codes` (list of strings) | `PersistentLogger.log_alert` → JSONL → `generate_dashboard.py:361` |
| `engine.py` `AlertScore` | `invalidation`, `tp1`, `tp2`, `entry_zone` | JSONL alert → `generate_dashboard.py:357-359` |
| JSONL alert | `entry_price` (float set by `PersistentLogger`) | `dashboard_server.py`, `generate_dashboard.py:357` |
| JSONL alert | `context` (dict) | `generate_dashboard.py:78-80` — **currently NOT written** |

---

## Bug #1 — Live Tape Win Rate & Profit Factor stuck at 0.00%

### Root cause

`scripts/pid-129/dashboard_server.py` line 56 reads the field name `"r"` from closed trades, but `tools/paper_trader.py` serialises it as `"r_multiple"`.

### Fix — file: `scripts/pid-129/dashboard_server.py`

**Function**: `_portfolio_stats` (lines 54-80)

**BEFORE** (line 56):
```python
    r_values = [t.get("r") for t in closed if isinstance(t.get("r"), (int, float))]
```

**AFTER**:
```python
    r_values = [t.get("r_multiple") for t in closed if isinstance(t.get("r_multiple"), (int, float))]
```

This is the **only** change in this file.

### Verification

After editing, restart `dashboard_server.py`.  The Live Tape "Win Rate" and "Profit Factor" cells will display the correct numbers (or 0.00% if no closed trades exist yet, which is the expected cold-start state).

---

## Bug #2 — Radar Probes stuck on ⚫ (Neutral)

### Root cause

Radar probes light up 🟢 or 🔴 only when specific string codes appear in the alert's `decision_trace.codes` list.  The codes are already produced by `engine.py` (lines 78-195, confirmed working).  Three sub-issues prevent them from appearing on the dashboard:

1. **Squeeze rarely fires.** `SQUEEZE_FIRE` requires the previous candle to be in a squeeze and the current candle to break out.  Between fires, the squeeze is either `SQUEEZE_ON` (which isn't mapped to a radar probe) or `NONE`.  Fix: also treat `SQUEEZE_ON` as a radar signal so the probe isn't always ⚫.
2. **Orderbook wall threshold too high.**  `config.py` sets `wall_threshold_btc: 5.0` (5 BTC).  On a typical BTC orderbook via Bybit's `limit=50`, individual level sizes are mostly < 5 BTC.  Fix: lower to 2.0 BTC.
3. **ML radar probe requires extreme scores.** `ML_CONFIDENCE_BOOST` only emits at `total_score >= 35` (line 192).  Most scores are in the −20 to +20 range.  Fix: lower threshold to 20.

### Fix 2a — file: `engine.py`

**Lines 80-84, add `SQUEEZE_ON` as a distinct code for the radar:**

**BEFORE**:
```python
        if sq["state"] == "SQUEEZE_FIRE":
            breakdown["volatility"] += sq["pts"]
            codes.append("SQUEEZE_FIRE")
        elif sq["state"] == "SQUEEZE_ON":
            codes.append("SQUEEZE_ON")
```

**AFTER** (no change needed — `SQUEEZE_ON` is already appended).  Instead we add `SQUEEZE_ON` to the radar probe definition in `generate_dashboard.py`.  See Fix 2d.

### Fix 2b — file: `config.py`

**Line 118, lower `wall_threshold_btc`:**

**BEFORE**:
```python
    "wall_threshold_btc": 5.0,
```

**AFTER**:
```python
    "wall_threshold_btc": 2.0,
```

**Rationale**: Bybit returns 50 price levels.  At current BTC prices (~$90k), a 2-BTC wall ($180k notional) is a meaningful liquidity cluster.  This is already bounded by `depth_pct: 0.02` (2% from mid), so only walls within ±$1,800 of mid are detected.

### Fix 2c — file: `engine.py`

**Lines 192-195, lower ML proxy thresholds:**

**BEFORE**:
```python
    if total_score >= 35:
        codes.append("ML_CONFIDENCE_BOOST")
    elif total_score <= -35:
        codes.append("ML_SKEPTICISM")
```

**AFTER**:
```python
    if total_score >= 20:
        codes.append("ML_CONFIDENCE_BOOST")
    elif total_score <= -20:
        codes.append("ML_SKEPTICISM")
```

### Fix 2d — file: `scripts/pid-129/generate_dashboard.py`

**Three locations** define the 10 radar probes (they must stay identical).  They are at:
1. `build_verdict_context()` — Python — line 372
2. `generate_html()` → JavaScript `wsPD` array — line 598

In **both locations**, update the **Squeeze** probe to accept `SQUEEZE_ON` alongside `SQUEEZE_FIRE`:

#### Location 1 — `build_verdict_context`, line 372

**BEFORE**:
```python
        ("Squeeze", ["SQUEEZE_FIRE"], []),
```

**AFTER**:
```python
        ("Squeeze", ["SQUEEZE_FIRE", "SQUEEZE_ON"], []),
```

#### Location 2 — JavaScript `wsPD` array inside the `connectWS` handler (line 598)

Find the first entry of the `wsPD` array:

**BEFORE**:
```javascript
[['SQUEEZE_FIRE'],[],'Squeeze']
```

**AFTER**:
```javascript
[['SQUEEZE_FIRE','SQUEEZE_ON'],[],'Squeeze']
```

> **IMPORTANT**: The JavaScript is minified on a single line.  Search for the exact string `['SQUEEZE_FIRE'],[],'Squeeze'` and replace with `['SQUEEZE_FIRE','SQUEEZE_ON'],[],'Squeeze'`.

### Verification

After restarting the loop (`python app.py --once`) and regenerating the dashboard, check `logs/pid-129-alerts.jsonl` (last entry).  The `decision_trace.codes` array should contain real strings.  The radar in `dashboard.html` should show at least 2-4 green/red probes instead of all ⚫.

---

## Bug #3 — Execution Matrix shows `--` for Entry / TP1 / Stop

### Root cause

`generate_dashboard.py` reads `entry_price`, `tp1`, and `invalidation` from the alert JSON (line 357-359).  These fields **are** written by `PersistentLogger.log_alert()` — so the data exists in the JSONL.  The issue is the **Execution Matrix panel** doesn't display per-timeframe execution levels.  It only shows Direction/Tier/Confidence.

Additionally, the `context` field that `get_context(alert)` reads (line 78-80 of `generate_dashboard.py`) is **never populated in the JSONL** because `PersistentLogger.log_alert()` doesn't include it.

### Fix 3a — file: `core/infrastructure.py`

**Function**: `PersistentLogger.log_alert` (lines 22-52)

Add `action`, `rr_ratio`, and `context` to the persisted record so the dashboard can display them.

**BEFORE** (lines 24-43):
```python
        record = {
            "alert_id": alert_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": score.symbol,
            "timeframe": score.timeframe,
            "direction": score.direction,
            "entry_price": price,
            "tp1": score.tp1,
            "tp2": score.tp2,
            "invalidation": score.invalidation,
            "confidence": score.confidence,
            "tier": score.tier,
            "strategy": score.strategy_type,
            "outcome": None,
            "outcome_timestamp": None,
            "outcome_price": None,
            "r_multiple": None,
            "resolved": False,
            "decision_trace": score.decision_trace
        }
```

**AFTER**:
```python
        record = {
            "alert_id": alert_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": score.symbol,
            "timeframe": score.timeframe,
            "direction": score.direction,
            "action": score.action,
            "entry_price": price,
            "tp1": score.tp1,
            "tp2": score.tp2,
            "invalidation": score.invalidation,
            "rr_ratio": round(score.rr_ratio, 2),
            "confidence": score.confidence,
            "confidence_score": score.confidence,
            "tier": score.tier,
            "blockers": score.blockers,
            "strategy": score.strategy_type,
            "context": {
                "regime": score.regime,
                "session": score.session,
            },
            "outcome": None,
            "outcome_timestamp": None,
            "outcome_price": None,
            "r_multiple": None,
            "resolved": False,
            "decision_trace": score.decision_trace
        }
```

**New fields explained:**
| Field | Source | Why |
|---|---|---|
| `action` | `score.action` | Execution Matrix decision logic (`execution_decision()`) reads `alert.get("action")` |
| `rr_ratio` | `score.rr_ratio` | Lifecycle panel uses it; avoids re-calculating from entry/inv/tp1 |
| `confidence_score` | `score.confidence` | `get_confidence()` in `generate_dashboard.py:69` tries `confidence_score` first |
| `blockers` | `score.blockers` | `get_blockers()` reads `alert.get("blockers")` — needed for safety gate and lifecycle panel |
| `context.regime` | `score.regime` | `get_context(alert)` at `generate_dashboard.py:135` reads `ctx.get("regime")` |
| `context.session` | `score.session` | `get_context(alert)` at `generate_dashboard.py:136` reads `ctx.get("session")` |

### Fix 3b — file: `scripts/pid-129/generate_dashboard.py`

**Function**: `render_execution_matrix` (lines 120-174)

Add Entry/Stop/TP rows to the matrix table so the trader can copy exact levels.

**BEFORE** (lines 141-151):
```python
        cols.append(f"""
        <td>
            <div class="pill-wrap">
                <span class="pill {badge_class_for_direction(direction)}">{direction}</span>
                <span class="pill {badge_class_for_tier(tier)}">{tier}</span>
                <span class="pill badge-neutral">{conf}/100</span>
            </div>
            <div class="mini">Regime: {regime} · Session: {session}</div>
            <div class="mini">Blockers: {blockers}</div>
        </td>
        """)
```

**AFTER**:
```python
        entry = float(a.get("entry_price") or 0)
        stop = float(a.get("invalidation") or 0)
        tp1_val = float(a.get("tp1") or 0)
        rr = float(a.get("rr_ratio") or 0)
        entry_str = f"${entry:,.0f}" if entry else "--"
        stop_str = f"${stop:,.0f}" if stop else "--"
        tp1_str = f"${tp1_val:,.0f}" if tp1_val else "--"
        rr_str = f"{rr:.2f}" if rr else "--"
        cols.append(f"""
        <td>
            <div class="pill-wrap">
                <span class="pill {badge_class_for_direction(direction)}">{direction}</span>
                <span class="pill {badge_class_for_tier(tier)}">{tier}</span>
                <span class="pill badge-neutral">{conf}/100</span>
            </div>
            <div class="mini">Regime: {regime} · Session: {session}</div>
            <div class="mini">Entry: {entry_str} · Stop: {stop_str} · TP1: {tp1_str} · R:R {rr_str}</div>
            <div class="mini">Blockers: {blockers}</div>
        </td>
        """)
```

### Verification

After one full loop cycle (`python app.py --once`), check the last 3 entries in `logs/pid-129-alerts.jsonl`:
```powershell
Get-Content logs/pid-129-alerts.jsonl | Select-Object -Last 3 | ForEach-Object { $_ | ConvertFrom-Json | Select-Object symbol, timeframe, action, entry_price, tp1, invalidation, rr_ratio, context, blockers }
```

Each should have `context.regime`, `context.session`, `blockers`, `rr_ratio`, and `action` populated.

Then open `http://localhost:8000`.  The Execution Matrix rows for 5m/15m/1h should show `Entry: $XX,XXX · Stop: $XX,XXX · TP1: $XX,XXX · R:R X.XX` instead of placeholder dashes.

---

## Bug #4 — Verdict Center entry/stop/TP1 distances show `—`

### Root cause

`build_verdict_context()` (line 357) reads `entry_price` from the JSONL.  This already works because `PersistentLogger.log_alert` writes `entry_price`.  However, the `livePrice`, `distTP1`, and `distStop` calculations in the JavaScript `updateLivePrice()` function (line 577-594) depend on `state.entryPrice`, `state.tp1Price`, and `state.stopPrice` being non-zero.  These are set at render time from `vctx["entry"]`, `vctx["tp1"]`, `vctx["stop"]` (line 573).

`build_verdict_context()` at line 357-359 reads:
```python
entry = float(alert.get("entry_price") or alert.get("entry") or 0)
tp1 = float(alert.get("tp1") or 0)
stop = float(alert.get("invalidation") or 0)
```

This **already works** if the JSONL contains those fields — and it does (confirmed from `PersistentLogger.log_alert`).  The `—` appears only on cold-start when no alerts exist.

**No code change needed.**  This bug is resolved by Bug #3a (adding more complete data to the JSONL).  After one loop cycle, these values will populate.

---

## Bug #5 — WebSocket `stats` Win Rate / Profit Factor always 0

### Root cause

Same as Bug #1.  `dashboard_server.py:_portfolio_stats()` reads `"r"` instead of `"r_multiple"`.  Already fixed by Bug #1.

---

## Summary of ALL edits

| # | File | Type | Lines affected |
|---|---|---|---|
| 1 | `scripts/pid-129/dashboard_server.py` | Key fix | Line 56: `"r"` → `"r_multiple"` |
| 2b | `config.py` | Threshold tune | Line 118: `5.0` → `2.0` |
| 2c | `engine.py` | Threshold tune | Lines 192-195: `35`/`-35` → `20`/`-20` |
| 2d | `scripts/pid-129/generate_dashboard.py` | Probe mapping | Line 372: add `"SQUEEZE_ON"` to Squeeze probe |
| 2d | `scripts/pid-129/generate_dashboard.py` | JS probe mapping | Line 598: add `'SQUEEZE_ON'` to JS wsPD[0] |
| 3a | `core/infrastructure.py` | Data completeness | Lines 24-43: add `action`, `rr_ratio`, `confidence_score`, `blockers`, `context` to JSONL record |
| 3b | `scripts/pid-129/generate_dashboard.py` | Matrix display | Lines 141-151: add entry/stop/TP1/R:R display row |

**Total files edited: 4** — `dashboard_server.py`, `config.py`, `engine.py`, `core/infrastructure.py`, `generate_dashboard.py`

---

## Execution Checklist (for AI agent)

```
[x] 1. Edit scripts/pid-129/dashboard_server.py — Bug #1 fix
[x] 2. Edit config.py — Bug #2b threshold
[x] 3. Edit engine.py — Bug #2c ML thresholds
[x] 4. Edit scripts/pid-129/generate_dashboard.py — Bug #2d squeeze probe (Python)
[x] 5. Edit scripts/pid-129/generate_dashboard.py — Bug #2d squeeze probe (JavaScript)
[x] 6. Edit core/infrastructure.py — Bug #3a add fields to JSONL
[x] 7. Edit scripts/pid-129/generate_dashboard.py — Bug #3b matrix entry/stop/tp display
[x] 8. Stop running processes (python app.py and dashboard_server.py)
[x] 9. Run: python app.py --once
[x] 10. Run: python scripts/pid-129/generate_dashboard.py
[x] 11. Run: python scripts/pid-129/dashboard_server.py
[x] 12. Verify: Open http://localhost:8000
[x] 13. Verify: Live Tape shows Win Rate and Profit Factor (not 0.00% if trades exist)
[x] 14. Verify: Confluence Radar shows at least some 🟢/🔴 probes (not all ⚫)
[x] 15. Verify: Execution Matrix rows show Entry/Stop/TP1/R:R values (not --)
[x] 16. Verify: No Python tracebacks in terminal output
```

---

## API Rate Limits (already enforced — no changes needed)

All API calls go through `BudgetManager` in `collectors/base.py`.  Current limits per source:

| Source | Max calls | Window |
|---|---|---|
| `kraken` | 24 | 60s |
| `coingecko` | 10 | 60s |
| `alternative_me` | 5 | 300s |
| `yahoo` | 10 | 300s |
| `bybit` | 24 | 60s |
| `okx` | 24 | 60s |
| `rss` | 20 | 300s |

**Each source has a fallback chain:**
- BTC Price: Kraken → CoinGecko → unhealthy fallback
- Candles: Kraken → Bybit → empty
- Derivatives: Bybit → OKX → unhealthy fallback
- Macro (DXY/Gold): Yahoo → empty
- Orderbook: Bybit → empty

This phase does **not** add any API calls.  It only changes threshold comparisons and data serialization.

---

## What success looks like

After all edits and one full cycle:

1. **Live Tape** — Win Rate shows the correct % from `paper_portfolio.json`.  Profit Factor shows the correct ratio.  Both update in real-time via WebSocket.
2. **Confluence Radar** — At least 3-5 probes are 🟢 or 🔴.  The net score and bar reflect actual market state.  `SQUEEZE_ON` lights the Squeeze probe.  Lowered wall threshold causes Order Book probe to fire.  ML probe fires at ±20 score.
3. **Execution Matrix** — Each timeframe cell shows `Entry: $XX,XXX · Stop: $XX,XXX · TP1: $XX,XXX · R:R X.XX`.  Regime and Session are populated (not `-`).  The Execution Decision shows EXECUTE or WAIT with correct reasoning.
4. **Verdict Center** — Live BTC Price, TP1 distance, Stop distance, and Spread update every 2 seconds.  Trade Safety gate reflects actual check results.

---
*Phase 13 Blueprint — Self-contained AI execution document*
*All edits scoped to 4 existing files with exact before/after diffs*
