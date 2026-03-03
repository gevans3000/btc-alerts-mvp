# Phase 28 Hardened — Final Dashboard & Logic Fixes

**Objective**: Fix every remaining dashboard display bug, data wiring issue, and logic error so the system achieves A+ operational quality. Every edit is exact — apply verbatim.

**DO NOT TOUCH**: `config.py`, `app.py`, `core/infrastructure.py`, `collectors/` directory, any file in `intelligence/` other than what is specified.

**RULES**: No new files. No refactoring. No comments beyond what is specified. No type hints. No docstrings. Apply edits character-for-character.

---

## Bug 1: Funding / Basis / OI Delta Never Populate [DONE]

**Root Cause**: The JS reads `wsCtx.derivatives` (line 1312), but `derivatives` lives at `data.derivatives` (a top-level key in the WebSocket JSON), not inside `cached_context`. So `wsCtx.derivatives` is always `undefined` and the elements show "—".

**File**: `dashboard.html`  
**Location**: Line 1312 (inside `ws.onmessage` handler)

**FIND** (exact):
```javascript
                    // ── Phase 26 Task 7.2: Smart Money UI ──
                    const wsDeriv = wsCtx.derivatives || {};
```

**REPLACE WITH** (exact):
```javascript
                    // ── Phase 26 Task 7.2: Smart Money UI ──
                    const wsDeriv = data.derivatives || {};
```

**Why**: `data` is the parsed WebSocket message. `data.derivatives` contains `funding_rate`, `oi_change_pct`, `basis_pct`.

---

## Bug 2: Live State Uses Mock Values ($50k Entry / $49k Stop) [DONE]

**Root Cause**: `state` object initializes with `entryPrice: 50000.0, tp1Price: 52000.0, stopPrice: 49000.0` and is never updated from portfolio data. The Live Execution Matrix and distance-to-TP/stop calculations use these stale mock values.

**File**: `dashboard.html`  
**Location**: Line 1089

**FIND** (exact):
```javascript
        let state = { livePrice: 0, spread: 0, inTrade: false, entryPrice: 50000.0, tp1Price: 52000.0, stopPrice: 49000.0, direction: "LONG" };
```

**REPLACE WITH** (exact):
```javascript
        let state = { livePrice: 0, spread: 0, inTrade: false, entryPrice: 0, tp1Price: 0, stopPrice: 0, direction: "LONG" };
```

Then, add state sync from portfolio. **FIND** (in ws.onmessage, line ~1202, inside the try block):
```javascript
                    const po = data.portfolio || {}; els.balance.textContent = fmtMoney(Number(po.balance || 0), 2); const st = data.stats || {}; window._lastStats = st; window._lastBalance = Number(po.balance || 0); els.winrate.textContent = Number(st.win_rate || 0).toFixed(2) + '%'; els.pf.textContent = Number(st.profit_factor || 0).toFixed(2); if (els.kelly) els.kelly.textContent = (Number(st.kelly_pct || 0) * 100).toFixed(2) + '%';
```

**REPLACE WITH** (exact):
```javascript
                    const po = data.portfolio || {}; els.balance.textContent = fmtMoney(Number(po.balance || 0), 2); const st = data.stats || {}; window._lastStats = st; window._lastBalance = Number(po.balance || 0); els.winrate.textContent = Number(st.win_rate || 0).toFixed(2) + '%'; els.pf.textContent = Number(st.avg_r || 0).toFixed(2); if (els.kelly) els.kelly.textContent = (Number(st.kelly_pct || 0) * 100).toFixed(2) + '%';
                    const positions = po.positions || [];
                    if (positions.length > 0) {
                        const p0 = positions[0];
                        state.inTrade = true;
                        state.direction = p0.direction || 'LONG';
                        state.entryPrice = Number(p0.entry_price) || 0;
                        state.stopPrice = Number(p0.sl) || 0;
                        state.tp1Price = Number(p0.tp1) || 0;
                    } else {
                        state.inTrade = false;
                    }
```

**Why**: (a) The stats field is `avg_r` not `profit_factor` — the `pf` element label says "Avg R (7d)". (b) Portfolio positions now sync into `state` so the live execution panel shows real entry/stop/TP, not $50k mocks.

---

## Bug 3: Performance Metrics / Confidence Calibration Sections Are Static Empty [DONE]

**Root Cause**: These sections in the HTML body (lines 782-795) are hard-coded as `<p>No portfolio data available.</p>`. They are never dynamically rendered from `data.stats`.

**File**: `dashboard.html`  
**Location**: Lines 781-795

**FIND** (exact):
```html
            <section style="margin-bottom: 1.5rem;">
                <h2>Performance Metrics</h2>
                <p>No portfolio data available.</p>
            </section>

            <section class="panel">
                <h2>Timeframe Edge Scoreboard</h2>
                <p class="mini">No portfolio data available.</p>
            </section>


            <section class="panel">
                <h2>Confidence Calibration</h2>
                <p class="mini">No portfolio data available.</p>
            </section>
```

**REPLACE WITH** (exact):
```html
            <section style="margin-bottom: 1.5rem;">
                <h2>Performance Metrics</h2>
                <div id="perf-metrics-body"><p class="mini">Loading...</p></div>
            </section>

            <section class="panel">
                <h2>Timeframe Edge Scoreboard</h2>
                <div id="tf-edge-body"><p class="mini">Loading...</p></div>
            </section>

            <section class="panel">
                <h2>Confidence Calibration</h2>
                <div id="conf-cal-body"><p class="mini">Loading...</p></div>
            </section>
```

Then, add the rendering logic. **FIND** (in ws.onmessage handler, right after the BS-filter block, line ~1406):
```javascript
                    // ── Phase 25: Execution Copilot ──
```

**INSERT BEFORE** that line:
```javascript
                    // ── Phase 28: Performance Metrics rendering ──
                    const pmEl = document.getElementById('perf-metrics-body');
                    if (pmEl && st.total_trades > 0) {
                        pmEl.innerHTML = '<div class="stats-grid">'
                            + '<div class="stat-card"><div class="stat-label">Win Rate</div><div class="live-value">' + (st.win_rate * 100).toFixed(1) + '%</div></div>'
                            + '<div class="stat-card"><div class="stat-label">Avg R</div><div class="live-value">' + Number(st.avg_r).toFixed(2) + '</div></div>'
                            + '<div class="stat-card"><div class="stat-label">Total R</div><div class="live-value">' + Number(st.total_r).toFixed(2) + '</div></div>'
                            + '<div class="stat-card"><div class="stat-label">Trades</div><div class="live-value">' + st.total_trades + '</div></div>'
                            + '<div class="stat-card"><div class="stat-label">Streak</div><div class="live-value">' + st.streak + '</div></div>'
                            + '<div class="stat-card"><div class="stat-label">Open uPnL</div><div class="live-value" style="color:' + (st.open_upnl >= 0 ? 'var(--accent)' : '#ff4d4d') + '">' + fmtMoney(st.open_upnl, 0) + '</div></div>'
                            + '</div>';
                    } else if (pmEl) { pmEl.innerHTML = '<p class="mini">No closed trades yet.</p>'; }
                    const tfEl = document.getElementById('tf-edge-body');
                    if (tfEl && st.tf_stats) {
                        let tfH = '<table class="matrix-table"><thead><tr><th>TF</th><th>Trades</th><th>Win%</th><th>Avg R</th></tr></thead><tbody>';
                        for (const [tf, s] of Object.entries(st.tf_stats)) { tfH += '<tr><td>' + tf + '</td><td>' + s.count + '</td><td>' + (s.win_rate * 100).toFixed(0) + '%</td><td>' + Number(s.avg_r).toFixed(2) + '</td></tr>'; }
                        tfH += '</tbody></table>';
                        tfEl.innerHTML = tfH;
                    }
                    const ccEl = document.getElementById('conf-cal-body');
                    if (ccEl && st.recipe_stats) {
                        let ccH = '<table class="matrix-table"><thead><tr><th>Recipe</th><th>Trades</th><th>Win%</th><th>Avg R</th></tr></thead><tbody>';
                        for (const [r, s] of Object.entries(st.recipe_stats)) { ccH += '<tr><td>' + r + '</td><td>' + s.count + '</td><td>' + (s.win_rate * 100).toFixed(0) + '%</td><td>' + Number(s.avg_r).toFixed(2) + '</td></tr>'; }
                        ccH += '</tbody></table>';
                        ccEl.innerHTML = ccH;
                    }

```

---

## Bug 4: Closed Trade Shows "WIN" with Negative PnL [DONE]

**Root Cause**: In `_portfolio_stats` (dashboard_server.py), the outcome field from the portfolio JSON is used directly. But `portfolio.json` stores whatever `outcome_tracker.py` wrote. The outcome_tracker has a SHORT TP1 comparison bug (see Bug 5).

Additionally, the stats function doesn't validate: if `r_multiple < 0`, the outcome should never be "WIN".

**File**: `scripts/pid-129/dashboard_server.py`  
**Location**: Inside `_portfolio_stats` function, around line 257-270 (where closed trades are processed)

**FIND** the loop that builds `r_values` from closed trades. Look for the line that reads `r_multiple`:
```python
            r = trade.get("r_multiple", 0)
```

**REPLACE WITH**:
```python
            r = trade.get("r_multiple", 0)
            if r < 0 and trade.get("outcome", "").startswith("WIN"):
                trade["outcome"] = "LOSS"
```

**Why**: Defensive correction — if r_multiple is negative, it's a loss regardless of what outcome_tracker wrote.

---

## Bug 5: outcome_tracker.py SHORT TP Comparison Inverted [DONE]

**Root Cause**: For SHORT trades, TP1 is a price BELOW entry. The current code checks `current_price <= tp1`, but TP1 for shorts is already below entry, so this resolves immediately when price drops at all — even before actually reaching the target. The real check should compare absolute distance.

Also, for SHORT TP2: `current_price <= tp2` — TP2 is even lower than TP1 for shorts, so this is correct directionally but can fire too early if TP values in the alert are stored incorrectly (as positive offsets).

**File**: `tools/outcome_tracker.py`  
**Location**: Lines 102-114

**FIND** (exact):
```python
        elif direction == "SHORT":
            if tp2 and current_price <= tp2:
                resolved = True
                outcome = "WIN_TP2"
                r_multiple = abs(entry - tp2) / risk
            elif current_price <= tp1:
                resolved = True
                outcome = "WIN_TP1"
                r_multiple = abs(entry - tp1) / risk
            elif current_price >= sl:
                resolved = True
                outcome = "LOSS"
                r_multiple = -1.0
```

**REPLACE WITH** (exact):
```python
        elif direction == "SHORT":
            if current_price >= sl:
                resolved = True
                outcome = "LOSS"
                r_multiple = -1.0
            elif tp2 and tp2 < entry and current_price <= tp2:
                resolved = True
                outcome = "WIN_TP2"
                r_multiple = abs(entry - tp2) / risk
            elif tp1 and tp1 < entry and current_price <= tp1:
                resolved = True
                outcome = "WIN_TP1"
                r_multiple = abs(entry - tp1) / risk
```

**Why**: (a) Check stop-loss FIRST (most important for risk management). (b) Guard `tp < entry` ensures SHORT TPs are actually below entry price. Prevents false WIN on malformed alerts where TP values might be stored as ATR offsets rather than absolute prices.

Also fix the LONG side to check SL first:

**FIND** (exact):
```python
        if direction == "LONG":
            if tp2 and current_price >= tp2:
                resolved = True
                outcome = "WIN_TP2"
                r_multiple = abs(tp2 - entry) / risk
            elif current_price >= tp1:
                resolved = True
                outcome = "WIN_TP1"
                r_multiple = abs(tp1 - entry) / risk
            elif current_price <= sl:
                resolved = True
                outcome = "LOSS"
                r_multiple = -1.0
```

**REPLACE WITH** (exact):
```python
        if direction == "LONG":
            if current_price <= sl:
                resolved = True
                outcome = "LOSS"
                r_multiple = -1.0
            elif tp2 and tp2 > entry and current_price >= tp2:
                resolved = True
                outcome = "WIN_TP2"
                r_multiple = abs(tp2 - entry) / risk
            elif tp1 and tp1 > entry and current_price >= tp1:
                resolved = True
                outcome = "WIN_TP1"
                r_multiple = abs(tp1 - entry) / risk
```

---

## Bug 6: Auto-Pilot Mutes the Recipes Phase 28 Relaxed [DONE]

**Root Cause**: In `dashboard_server.py` lines 817-819, during `vol_regime == "low"`, auto-pilot mutes `BOS_CONTINUATION` and `VOL_EXPANSION`. But the Phase 28 fixes specifically relaxed these recipes to fire more. The current vol regime is "low" (RVOL 0.39), so these mutes are actively suppressing the signals we just unblocked.

**File**: `scripts/pid-129/dashboard_server.py`  
**Location**: Lines 814-819

**FIND** (exact):
```python
        if vol_regime == "expansion":
            for name in ("HTF_REVERSAL",):
                auto_muted_recipes[name] = auto_expiry
        elif vol_regime == "low":
            for name in ("BOS_CONTINUATION", "VOL_EXPANSION"):
                auto_muted_recipes[name] = auto_expiry
```

**REPLACE WITH** (exact):
```python
        if vol_regime == "expansion":
            for name in ("HTF_REVERSAL",):
                auto_muted_recipes[name] = auto_expiry
```

**Why**: Removing the low-vol mute. VOL_EXPANSION is specifically designed to catch the transition OUT of low volatility. Muting it during low vol defeats the purpose. BOS_CONTINUATION was relaxed in Phase 28 to fire with wider tolerances — muting it undermines that.

---

## Bug 7: data_age_seconds Reports Alert Age, Not Engine Age [DONE]

**Root Cause**: `data_age_seconds` (line 726) is computed from `last_alert_time` (the timestamp of the last tradeable alert). But the engine may have run recently without generating a new tradeable alert (all NO-TRADE). This makes the dashboard show "DATA STALE" even when the engine is running fine.

The heartbeat file `data/last_cycle.json` IS already read (line 711-719) but only used for `alerts_stale`, not for `data_age_seconds`.

**File**: `scripts/pid-129/dashboard_server.py`  
**Location**: Line 726

**FIND** (exact):
```python
        data_age_seconds = now_ts - last_alert_time if last_alert_time > 0 else 9999
```

**REPLACE WITH** (exact):
```python
        data_age_seconds = now_ts - engine_time if engine_time > 0 else 9999
```

**Why**: `engine_time` already combines heartbeat + alert fallback (line 723). Using it for `data_age_seconds` means the dashboard shows freshness based on when the engine last ran, not when it last produced a tradeable signal.

---

## Bug 8: Win Rate Display Shows Decimal Instead of Percentage [DONE]

**Root Cause**: `st.win_rate` is a value like `0.75` (75%). The JS displays it as `0.75%` instead of `75.00%` because it doesn't multiply by 100.

**File**: `dashboard.html`  
**Location**: Line 1202 (in ws.onmessage)

**FIND** (exact):
```javascript
els.winrate.textContent = Number(st.win_rate || 0).toFixed(2) + '%';
```

**REPLACE WITH** (exact):
```javascript
els.winrate.textContent = (Number(st.win_rate || 0) * 100).toFixed(1) + '%';
```

---

## Verification Checklist

After applying all edits, run these commands:

### Check 1: Data Freshness
```bash
python app.py --once
```
Expected: Exit code 0. Then check dashboard at http://localhost:8002/ — the sync label should show a recent timestamp, NOT "DATA STALE" (unless the cycle was > 2 minutes ago).

### Check 2: Funding / OI Delta Populated
Open http://localhost:8002/ in a browser. The "Funding / Basis" card should show values like `0.0055% | -0.04%`. The "OI Delta (5m)" card should show a percentage like `-0.56%`. If they still show "—", check browser console for JS errors.

### Check 3: Live State Sync
The Execution Copilot should show the actual entry price of any open position (e.g., `SHORT @ $67,668`), NOT `$50,000`. The distTP1 and distStop values should be relative to the real position, not mock values.

### Check 4: Performance Metrics Render
The "Performance Metrics" section should show stat cards (Win Rate, Avg R, Total R, Trades, Streak, Open uPnL). "Timeframe Edge Scoreboard" should show a table. "Confidence Calibration" should show recipe stats.

### Check 5: Outcome Tracker
```bash
python -c "from tools.outcome_tracker import resolve_outcomes; resolve_outcomes()"
```
Expected: No trades incorrectly labeled as WIN when r_multiple is negative.

### Check 6: Auto-Pilot Not Muting Phase 28 Recipes
Open http://localhost:8002/ — the auto-pilot indicator should NOT say "2 muted" with BOS_CONTINUATION and VOL_EXPANSION. It should show "ALL" or "FLOOR: 50".

### Check 7: Win Rate Format
The "Win Rate (7d)" card should show "0.0%" not "0.00%".

### Final: Full Cycle
```bash
python app.py --once
```
Expected: Exit code 0, no tracebacks. Dashboard refreshes with all fields populated.
