# Phase 26 — Live-Readiness Hardening (The Final Gate)

**Status:** ✅ DONE
**Depends on:** Phase 25 (✅ DONE)
**Target files:** `scripts/pid-129/dashboard_server.py`, `dashboard.html`
**Goal:** Fill every blank dashboard field with real or intelligently-estimated data, add robust fallbacks for when data sources go offline, and eliminate silent failures — so the trader can trust every number on screen when real money is at stake. Crucially, this phase also lays the groundwork for expanded free API data (smart money edge).

---

## 📋 RULES FOR THE IMPLEMENTING AGENT

1. Read this **entire** document before writing any code.
2. **Only modify** `scripts/pid-129/dashboard_server.py` and `dashboard.html`. Do NOT touch `engine.py`, `config.py`, `app.py`, or any file under `intelligence/` or `collectors/`.
3. Complete tasks **sequentially** (Task 1 → 2 → 3 → 4 → 5 → 6 → 7). Do NOT combine them.
4. After each task, run `python scripts/pid-129/dashboard_server.py` and verify it starts without error. Then reload `http://localhost:8000/` in a browser and confirm no JS console errors.
5. Keep changes focused. Write modular, drop-in code. Do not restructure existing functions.

> **CRITICAL:** This phase does NOT modify the engine or collectors. All fixes are in the **dashboard layer** — the server that reads alert JSONL and the HTML that renders it.

---

## 🔍 CURRENT BLANK FIELDS AUDIT (from live browser inspection)

| # | Field | Element ID | Current Value | Root Cause |
|---|-------|-----------|---------------|------------|
| 1 | Taker Ratio | `tape-taker` | `—` | Dashboard JS reads `data.flows.taker_ratio` but the WS payload has no `flows` key — flow data only exists inside alert `decision_trace.codes` |
| 2 | Sentiment | `tape-sentiment` | `—` (sometimes) | Only populated when the latest alert has `decision_trace.context.sentiment.score` — goes blank between alert cycles |
| 3 | DXY Macro | `tape-dxy` | `—` (sometimes) | Only populated when `decision_trace.context.macro_correlation.dxy` exists — stale during API gaps |
| 4 | Execute Button text | `executeBtn` | Does not restore original text | After circuit breaker deactivates, the button text stays at last state until next WS message — but doesn't restore the original label including the tier color |
| 5 | BS-Filter | `bs-filter-display` | Shows "CLEAR" with no styling | When `bs_severity = 0`, the element has text "CLEAR" but is visually invisible — should either hide or style it |
| 6 | Copilot PnL | copilot detail | Can show NaN | If `size_usdt = 0` or `entry_price = 0`, the PnL calculation divides by zero and shows NaN |

---

## 🛠️ IMPLEMENTATION TASKS

### Task 1: Pipe Flow Data to Dashboard (Fix `tape-taker` = `—`)
**Goal:** The "Taker Ratio" field in the Live Tape section always shows `—` because the WS payload has no `flows` key. Fix by extracting taker ratio from alert decision trace codes, same pattern used in BS-Filter.

#### What to do in `dashboard_server.py`:

**Step 1.1 — Extract taker ratio from alert codes and add to payload.**

Inside `get_dashboard_data()`, the BS-Filter block (Phase 25) already computes `taker_ratio` from alert codes. You can reuse this value. Find the line:
```python
            "bs_severity": bs_severity,
```
**After it**, add:
```python
            "flows": {"taker_ratio": round(taker_ratio, 2)},
```

This creates a `flows` object in the WS payload that the frontend already expects.

#### What to do in `dashboard.html`:

**No changes needed.** The JS at line ~1301 already reads:
```javascript
const taker = (data.flows || {}).taker_ratio;
_el('tape-taker', taker ? taker.toFixed(2) : '—');
```

---

### Task 2: Persist Last-Known Intelligence Context (Anti-Flicker)
**Goal:** When the dashboard refreshes between alert cycles, intelligence fields (Sentiment, DXY, OI Regime, Vol Regime, etc.) should hold their last-known values instead of flickering to `—`.

#### What to do in `dashboard_server.py`:

**Step 2.1 — Cache the last valid decision_trace context.**

At the module level (near the existing `_CACHED_DATA` and `_OVERRIDES` globals), add:

```python
_LAST_CONTEXT = {}  # Last valid intelligence context from alerts
```

Inside `get_dashboard_data()`, just **after** the vol regime extraction loop, add:

```python
    # ── Phase 26: Cache the richest decision_trace.context for display ──
    global _LAST_CONTEXT
    for a in reversed(all_recent_alerts):
        ctx = (a.get("decision_trace") or {}).get("context", {})
        if ctx and len(ctx) > len(_LAST_CONTEXT):
            _LAST_CONTEXT = ctx
            break
```

**Step 2.2 — Add the cached context to the return payload.**

In the return dict, add:
```python
            "cached_context": _LAST_CONTEXT,
```

#### What to do in `dashboard.html`:

**Step 2.3 — Use cached context as fallback for intelligence fields.**

Find the line inside `ws.onmessage` where the latest alert's context is read:
```javascript
                        const wsCtx = ((wsLatest.decision_trace || {}).context) || {};
```
**Replace it with:**
```javascript
                        const alertCtx = ((wsLatest.decision_trace || {}).context) || {};
                        const cachedCtx = data.cached_context || {};
                        // Merge: prefer live alert context, fall back to cached
                        const wsCtx = Object.assign({}, cachedCtx, alertCtx);
```

---

### Task 3: Harden Copilot Against Edge Cases
**Goal:** The Copilot PnL display can show `NaN` or `$NaN` when position data is incomplete. Add defensive guards.

#### What to do in `dashboard.html`:

**Step 3.1 — Guard the PnL calculation against zero/missing values.**

Find the existing Copilot code block (Phase 25). Replace the line:
```javascript
                            const sz = pos.size_usdt || 0;
```
with:
```javascript
                            const sz = Number(pos.size_usdt) || 0;
```

And replace:
```javascript
                            if (entry > 0) {
```
with:
```javascript
                            if (entry > 0 && sz > 0 && isFinite(entry)) {
```

---

### Task 4: Restore Execute Button After Circuit Breaker Clears
**Goal:** When the circuit breaker deactivates, the Execute button text should restore to its original label.

#### What to do in `dashboard.html`:

**Step 4.1 — Restore button state in the WS update.**

Find the existing circuit breaker `else` block (Phase 25, Step 5.2):
```javascript
                        } else {
                            execBtn.disabled = false;
                            execBtn.style.opacity = '1';
                            execBtn.style.cursor = 'pointer';
                        }
```
**Replace it with:**
```javascript
                        } else {
                            execBtn.disabled = false;
                            execBtn.style.opacity = '1';
                            execBtn.style.cursor = 'pointer';
                            // Restore the original label based on latest alert tier
                            const tier = (btcAlerts[0] || {}).tier || 'NO-TRADE';
                            if (tier === 'A+') {
                                execBtn.textContent = '🟢 EXECUTE';
                                execBtn.style.background = '#00cc88';
                            } else if (tier === 'B') {
                                execBtn.textContent = '🟡 EXECUTE (WATCH)';
                                execBtn.style.background = '#cc8800';
                            } else {
                                execBtn.textContent = '⚠️ EXECUTE (HIGH RISK)';
                                execBtn.style.background = '#ff4d4d';
                            }
                        }
```

---

### Task 5: Style the BS-Filter "CLEAR" State
**Goal:** Make the "CLEAR" state reassuring rather than invisible.

#### What to do in `dashboard.html`:

**Step 5.1 — Update the BS-Filter JS.**

Find the existing BS-filter `else` block (Phase 25, Step 3.4):
```javascript
                        } else {
                            bsEl.style.background = 'transparent';
                            bsEl.style.color = 'var(--text-muted)';
                            bsEl.style.border = '1px solid transparent';
                        }
```
**Replace with:**
```javascript
                        } else {
                            bsEl.textContent = '✅ ORDER FLOW CLEAR';
                            bsEl.style.background = 'rgba(0,255,204,0.06)';
                            bsEl.style.color = 'var(--accent)';
                            bsEl.style.border = '1px solid rgba(0,255,204,0.2)';
                        }
```

---

### Task 6: Add Data Freshness Indicator
**Goal:** If alerts are more than 5 minutes stale, warn the trader.

#### What to do in `dashboard_server.py`:

**Step 6.1 — Compute data age.**

Inside `get_dashboard_data()`, after `all_recent_alerts = _load_alerts(limit=50)`, add:

```python
    # ── Phase 26: Data freshness check ──
    data_age_seconds = 9999
    if all_recent_alerts:
        latest_ts = all_recent_alerts[-1].get("timestamp")
        if latest_ts:
            try:
                from datetime import datetime as _dt
                if isinstance(latest_ts, str):
                    alert_time = _dt.fromisoformat(latest_ts.replace("Z", "+00:00"))
                    data_age_seconds = (datetime.now(timezone.utc) - alert_time).total_seconds()
                elif isinstance(latest_ts, (int, float)):
                    data_age_seconds = time.time() - latest_ts
            except Exception:
                pass
```

Add to the return dict:
```python
            "data_age_seconds": round(data_age_seconds, 0),
```

#### What to do in `dashboard.html`:

**Step 6.2 — Show staleness warning in the header.**

Inside `ws.onmessage`, **after** `els.sync.textContent = ...`, add:

```javascript
                    // ── Phase 26: Data Freshness Warning ──
                    const dataAge = data.data_age_seconds || 0;
                    const syncEl = els.sync;
                    if (syncEl) {
                        if (dataAge > 300) {
                            syncEl.textContent = '⚠️ DATA STALE (' + Math.round(dataAge / 60) + 'm old)';
                            syncEl.style.color = '#ff4d4d';
                        } else if (dataAge > 120) {
                            syncEl.textContent = 'Synced: ' + new Date().toLocaleString() + ' (⏳ ' + Math.round(dataAge) + 's ago)';
                            syncEl.style.color = '#ffa500';
                        } else {
                            syncEl.textContent = 'Synced: ' + new Date().toLocaleString();
                            syncEl.style.color = 'var(--text-muted)';
                        }
                    }
```

---

### Task 7: Free API Alpha Injection (Smart Money Edge)
**Goal:** The system already collects `funding_rate`, `basis_pct`, and `oi_change_pct` through Bybit and OKX free APIs, but this critical "Smart Money" data is hidden deep in the context and never shown on the dashboard. Add it.

#### What to do in `dashboard.html`:

**Step 7.1 — Create the Smart Money UI Panel.**

Find the `live-grid` definition (where `stat-card` elements live). We need to inject the Funding Rate and Basis/Premium directly into the tape. 

Add these two stat cards right after the `Taker Ratio` stat card:

```html
            <div class="stat-card" style="border:1px solid rgba(112,0,255,0.3); background:rgba(112,0,255,0.05);">
                <div class="stat-label">Funding / Basis</div>
                <div id="tape-funding" class="live-value" style="color:#b580ff;">—</div>
            </div>
            <div class="stat-card" style="border:1px solid rgba(112,0,255,0.3); background:rgba(112,0,255,0.05);">
                <div class="stat-label">OI Delta (5m)</div>
                <div id="tape-oi-delta" class="live-value" style="color:#b580ff;">—</div>
            </div>
```

**Step 7.2 — Populate the Smart Money UI in JS.**

Inside `ws.onmessage`, right after you assign `const taker = (data.flows || {}).taker_ratio;` and `_el('tape-taker', ...);` (around line 1302), add:

```javascript
                        // ── Phase 26: Smart Money / Derivatives API Data ──
                        const wsDeriv = wsCtx.derivatives || {};
                        const fundRate = wsDeriv.funding_rate;
                        const basis = wsDeriv.basis_pct;
                        const oiDelta = wsDeriv.oi_change_pct;
                        
                        const fundEl = document.getElementById('tape-funding');
                        if (fundEl) {
                            if (fundRate !== undefined && basis !== undefined) {
                                const fStr = (fundRate * 100).toFixed(4) + '%';
                                const bStr = basis > 0 ? '+' + basis.toFixed(2) + '%' : basis.toFixed(2) + '%';
                                fundEl.textContent = fStr + ' | ' + bStr;
                                // Extreme funding > 0.01% or < -0.01% gets colored
                                if (fundRate > 0.0001) fundEl.style.color = '#ff4d4d'; // Expensive longs
                                else if (fundRate < -0.0001) fundEl.style.color = '#00ffcc'; // Expensive shorts
                                else fundEl.style.color = '#b580ff';
                            } else {
                                fundEl.textContent = '—';
                            }
                        }
                        
                        const oiEl = document.getElementById('tape-oi-delta');
                        if (oiEl) {
                            if (oiDelta !== undefined) {
                                oiEl.textContent = (oiDelta > 0 ? '+' : '') + oiDelta.toFixed(2) + '%';
                                if (oiDelta > 1.5) oiEl.style.color = '#00ffcc'; // Large OI injection
                                else if (oiDelta < -1.5) oiEl.style.color = '#ff4d4d'; // Large OI wipeout
                                else oiEl.style.color = '#b580ff';
                            } else {
                                oiEl.textContent = '—';
                            }
                        }
```

---

## ✅ VERIFICATION CHECKLIST FOR THE IMPLEMENTING AGENT

After all 7 tasks are complete, verify each of the following:

1. **Syntax Check**: Run `python scripts/pid-129/dashboard_server.py`. It must start with zero errors.

2. **Task 1 — Taker Ratio**: Open `http://localhost:8000/`. The "Taker Ratio" field in the Live Tape section should show a numeric value (e.g., `1.40` or `0.60`) instead of `—`. If no flow codes exist in alerts, it should show `1.00`.

3. **Task 2 — Anti-Flicker**: Reload the page. Intelligence fields (Sentiment, DXY Macro, OI Regime) should populate immediately from cached context instead of briefly showing `—`.

4. **Task 3 — Copilot NaN guard**: With an open position that has `size_usdt = 0` or missing, the Copilot should show "STANDBY" instead of "NaN" or "$NaN".

5. **Task 4 — Execute Button Restore**: When `circuit_breaker.active = false`, the Execute button should show the tier-colored label (🟢/🟡/⚠️) instead of blank text.

6. **Task 5 — BS-Filter CLEAR**: When `bs_severity = 0`, the BS-Filter should show `✅ ORDER FLOW CLEAR` with a subtle teal accent instead of invisible gray text.

7. **Task 6 — Staleness Warning**: If the latest alert is older than 5 minutes, the sync label should turn red and show `⚠️ DATA STALE (Xm old)`. Under 2 minutes, it should show normal green sync.

8. **Task 7 — Futures Alpha**: The Live Tape must now show exactly two new purple-tinted panels for "Funding / Basis" and "OI Delta (5m)". If the APIs (Bybit/OKX/Bitunix) are returning data, they will show real percentages.

9. **No JS Console Errors**: Open the browser developer console. There should be zero errors.

---

## 🔍 COMMON PITFALLS TO AVOID

| # | Mistake | Correct Approach |
|---|---------|-----------------|
| 1 | Adding `taker_ratio` as a top-level key | Nest it under `"flows": {"taker_ratio": ...}` — the JS expects `data.flows.taker_ratio`. |
| 2 | Replacing `wsCtx` entirely with cached context | **Merge** with `Object.assign({}, cachedCtx, alertCtx)` — live alert context takes priority. |
| 3 | Not guarding `isFinite()` in PnL calc | Missing or `null` prices produce `NaN` — always check `isFinite()` before displaying. |
| 4 | Placing the execute button restore code before `btcAlerts` declaration | The `btcAlerts` variable must be declared first — check line order carefully. |
| 5 | Parsing ISO timestamps without handling `Z` suffix | Python `fromisoformat()` before 3.11 doesn't parse `Z` — replace with `+00:00`. |
| 6 | Mutating `_LAST_CONTEXT` without global declaration | You must add `global _LAST_CONTEXT` inside `get_dashboard_data()` before overwriting it. |
| 7 | Assuming `funding_rate` is always present | Always check `!== undefined` before calling `.toFixed()` on futures data to prevent JS crashes on empty API results. |

---

## ✅ POST-COMPLETION AUDIT — GAPS CLOSED (Found 2026-03-02, Fixed 2026-03-02)

Phase 26 had three unresolved gaps after initial implementation. All four gaps below have been audited and closed. An additional bug (portfolio stats sample size) was discovered and fixed during audit.

---

### Gap 1 — ✅ FIXED: Anti-Flicker JS Applied to `generate_dashboard.py`

**Status:** Fixed in Phase 27 commit. `generate_dashboard.py` lines 1430–1433 now use `Object.assign({{}}, cachedCtx, alertCtx)` merge.

**Original issue:**
Phase 26 Task 2.3 specified replacing the `wsCtx` assignment in `dashboard.html` to merge live alert context with the cached server context:
```javascript
// Required by Phase 26 Task 2.3
const alertCtx = ((wsLatest.decision_trace || {}).context) || {};
const cachedCtx = data.cached_context || {};
const wsCtx = Object.assign({}, cachedCtx, alertCtx);
```
The actual code in `scripts/pid-129/generate_dashboard.py` (line ~1341) still uses the OLD single-source assignment:
```javascript
const wsCtx = ((wsLatest.decision_trace||{{}}).context)||{{}};
```
The dashboard HTML is generated from `generate_dashboard.py`, not from a static `dashboard.html`. The Task 2.3 fix was never applied to the generator. As a result:
- Vol/Regime, OI/Regime, DXY Macro, Sentiment all show `—` whenever the last alert lacks context
- Anti-flicker is only half-implemented (server caches it, JS never reads `cached_context`)

**Confirmed evidence:** The last two alerts in `logs/pid-129-alerts.jsonl` have `strategy: TEST` and `strategy: None` with `decision_trace: {confluence_score: N}` — empty context. The JS reads these and shows `—` for all tape intelligence fields.

**File to fix:** `scripts/pid-129/generate_dashboard.py`

**Find (around line 1341):**
```javascript
const wsCtx = ((wsLatest.decision_trace||{{}}).context)||{{}};
```
**Replace with:**
```javascript
const alertCtx = ((wsLatest.decision_trace||{{}}).context)||{{}};
const cachedCtx = data.cached_context||{{}};
const wsCtx = Object.assign({{}}, cachedCtx, alertCtx);
```
> Note: `{{}}` is the Jinja2-escaped form of `{}` used inside the Python f-string template in `generate_dashboard.py`. Check the surrounding code and match the brace escaping style exactly.

**Verify:** After regenerating and opening the dashboard, Vol/Regime, OI/Regime, DXY Macro, and Sentiment should show real values (from the last alert that had valid context) instead of `—`.

---

### Gap 2 — ✅ FIXED: `_portfolio_stats()` Now Falls Back to JSONL

**Status:** Fixed in Phase 27 commit. `dashboard_server.py` `_portfolio_stats()` lines 163–175 now iterate over alerts when `closed_trades` is empty.

**Additional bug fixed during audit (2026-03-02):** The fallback was passing `all_recent_alerts` (limit=50) which only captured 36 of 79 resolved trades. Fixed to use `_load_alerts(limit=1000)` at line 828 so all historical resolved trades are counted.

**Original issue:**
`data/paper_portfolio.json` contains an empty `closed_trades` list despite 79 resolved trades existing in `logs/pid-129-alerts.jsonl` (36 wins, 41 losses as of 2026-03-02). The dashboard's `_portfolio_stats()` function reads exclusively from `portfolio["closed_trades"]`. Because that list is empty, `win_rate`, `avg_r`, `kelly_pct`, and `profit_factor` all compute to `0.0`.

**Root cause:** The paper portfolio recorder (`tools/paper_trader.py` or `portfolio.on_alert()`) is not writing resolved trades to `data/paper_portfolio.json`. The outcomes are tracked in the JSONL log but never surfaced to the portfolio file that the dashboard reads.

**Impact:**
- Kelly % shows 0% → position sizing guidance is meaningless
- Win Rate shows 0% → circuit breaker streak logic has no signal
- Auto-tuner has no performance data to tune from
- Morning briefing correctly reads 79 resolved trades from JSONL (it reads the log directly) but the dashboard shows nothing

**File to fix:** `scripts/pid-129/dashboard_server.py`

**Fix approach — Make `_portfolio_stats()` fall back to JSONL outcomes when `closed_trades` is empty:**

Inside `_portfolio_stats()`, after computing `closed = portfolio.get("closed_trades", [])`, add a fallback that reads from the JSONL alert log:

```python
def _portfolio_stats(portfolio, current_price=0.0, alerts=None):
    closed = portfolio.get("closed_trades", []) if isinstance(portfolio, dict) else []

    # ── Phase 26 Gap 2 Fix: Fall back to JSONL outcomes if portfolio file is empty ──
    if not closed and alerts:
        for a in alerts:
            outcome = a.get("outcome")
            r = a.get("r_multiple")
            if outcome in ("WIN_TP1", "WIN_TP2", "LOSS", "TIMEOUT") and isinstance(r, (int, float)):
                closed.append({
                    "r_multiple": r,
                    "direction": a.get("direction", "NEUTRAL"),
                    "alert_id": a.get("alert_id"),
                    "outcome": outcome,
                })
    # ... rest of function continues unchanged
```

**Verify:** After the fix, Live Tape should show non-zero Win Rate, Avg R, and Kelly % matching the morning briefing values (~46% win rate, -7.43R total).

---

### Gap 3 — ✅ FIXED: TEST and None-Strategy Alerts Filtered in `_load_alerts()`

**Status:** Fixed in Phase 27 commit. `dashboard_server.py` `_load_alerts()` lines 136–138 now filter out `strategy in (None, "TEST", "SYNTHETIC")`. Verified: JSONL has 97 lines, 95 pass the filter (only 1 TEST + 1 None excluded).

**Original issue:**
Two alerts at the end of `logs/pid-129-alerts.jsonl` had `strategy: "TEST"` and `strategy: None`. Both had nearly empty `decision_trace` with no context, poisoning all tape fields.

---

### Gap 4 — CONTEXT: Negative Expectancy Requires Attention Before Live Execution

**Observed data (2026-03-02):**
- 7-day record: 36 wins / 41 losses (46% win rate)
- Total P&L: **-7.43R** over 79 resolved trades
- Average R per trade is negative (losses larger than wins on average)

**What this means:** A 46% win rate with negative total R means the average loser exceeds the average winner by a significant margin. The R:R targets set by `auto_rr.py` are not being honored at exit, or entries are taken at unfavorable prices relative to the invalidation. The system needs positive expectancy (Win% × Avg_Win > (1 - Win%) × Avg_Loss) before Phase 28 live execution is justified.

**This is NOT a bug to fix here** — it is a signal quality and tuning issue that belongs in Phase 27 (strict vetoes and filtration). However, it is documented here because the 0% dashboard stats (Gap 2) masked this problem entirely. Once Gap 2 is fixed and the dashboard shows real win rate data, the operator will be able to use this information to judge readiness.

**Action required before Phase 28:** Run `python tools/auto_tune.py` once Gaps 1–3 are fixed and the dashboard shows real performance data. Evaluate whether the macro veto (4h), flow veto, and chop zone veto are actually reducing the loss rate before enabling live execution.

---

_Phase 26 | Live-Readiness Hardening & Free API Edge Expansion | Formatted for AI Agent Implementation_
