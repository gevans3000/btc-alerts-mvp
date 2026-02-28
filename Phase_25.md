# Phase 25 — The Execution Co-Pilot & Regime Auto-Tuner

**Status:** ✅ DONE (all 5 tasks implemented)
**Depends on:** Phase 24 (✅ DONE)
**Target files:** `scripts/pid-129/dashboard_server.py`, `dashboard.html`
**Goal:** Upgrade the Command Dashboard from a passive data monitor to a **proactive execution co-pilot** that tells the trader exactly when to hold, when to fold, and when a breakout is a trap.

---

## 📋 RULES FOR THE IMPLEMENTING AGENT

1. Read this **entire** document before writing any code.
2. **Only modify** `scripts/pid-129/dashboard_server.py` and `dashboard.html`. Do NOT touch `engine.py`, `config.py`, `app.py`, or any file under `intelligence/`.
3. Complete tasks **sequentially** (Task 1 → 2 → 3 → 4 → 5). Do NOT combine them.
4. After each task, run `python scripts/pid-129/dashboard_server.py` and verify it starts without error. Then reload `http://localhost:8000/` in a browser and confirm no JS console errors.
5. Keep changes focused. Write modular, drop-in code. Do not restructure existing functions.
6. **Data shape reference** — The WebSocket payload sent to the frontend has this shape (produced by `get_dashboard_data()` in `dashboard_server.py`):
```json
{
  "timestamp": "...",
  "orderbook": { "mid": 84500.0, "spread": 3.6, "bid": 84498.2, "ask": 84501.8 },
  "portfolio": { "balance": 10200, "peak_balance": 10500, "positions": [...], "closed_trades": [...] },
  "alerts": [ { "idx": 0, "id": "...", "direction": "LONG", "confidence": 82, "tier": "A+", "regime": "range", "recipe": "BOS_CONTINUATION", "decision_trace": { "codes": [...], "context": { "volume_impulse": { "regime": "expansion" }, ... } }, ... } ],
  "stats": { "win_rate": 63.0, "profit_factor": 1.8, "avg_r": 0.26, "kelly_pct": 0.062, "total_r": 6.92, "open_upnl": 12.5, "drawdown_pct": 2.8, "long_stats": {...}, "short_stats": {...}, "recipe_stats": {...}, "streak": 3, "total_trades": 28 },
  "overrides": { "muted_recipes": { "HTF_REVERSAL": 1740800000 }, "min_score": 50 },
  "logs": "Heartbeat 15:30:22"
}
```
7. **Existing recipe names** in the system (only these three exist):
   - `HTF_REVERSAL`
   - `BOS_CONTINUATION`
   - `VOL_EXPANSION`
8. **Existing JS variables you can use** (already defined in `dashboard.html`'s `<script>` block):
   - `state` — `{ livePrice, spread, inTrade, entryPrice, tp1Price, stopPrice, direction, overrides, positionSize }`
   - `els` — DOM element cache: `{ badge, sync, mid, spread, balance, kelly, oc, pf, dd, le, se, peak, total_r, open_pnl }`
   - `fmtMoney(n, d)` — formats number as `$xx,xxx.xx`
   - `sendCommand(cmd)` — POSTs JSON to `/api/command`
9. **Existing Python functions you can use** (already defined in `dashboard_server.py`):
   - `_load_alerts(limit=50)` → returns list of raw alert dicts from JSONL
   - `_load_overrides()` → returns `_OVERRIDES` dict (keys: `muted_recipes` (dict!), `min_score`, `direction_filter`)
   - `_save_overrides()` → writes `_OVERRIDES` to disk
   - `_safe_json(path, default)` → safe JSON file reader
   - `_latest_price(alerts)` → returns float
   - `_portfolio_stats(portfolio, current_price, alerts)` → returns stats dict
   - `_light_alerts(alerts)` → returns lightweight alert list
   - `get_dashboard_data()` → builds the full WS payload dict

> **CRITICAL:** `muted_recipes` is a **dict**, not a list. The keys are recipe names, the values are expiry timestamps. When merging auto-muted recipes, you must use the dict format: `{ "RECIPE_NAME": expiry_timestamp }`.

---

## 🛠️ IMPLEMENTATION TASKS

### Task 1: Regime-Aware Auto-Pilot (Smart Muting in Backend)
**Goal:** Automatically suppress counter-trend recipes when the volatility regime is `expansion` — prevents the trader from fighting the trend during breakouts. Automatically suppress trend-following recipes when the regime is `low` (range-bound) — prevents chasing false breakouts.

#### What to do in `dashboard_server.py`:

**Step 1.1 — Extract vol regime from the latest alert.**

The vol regime lives inside `decision_trace.context.volume_impulse.regime` of each alert. There is NO `get_live_tape()` function. You must extract it from the most recent alert in the loaded alert list.

Inside `get_dashboard_data()`, **after** line `all_recent_alerts = _load_alerts(limit=50)` and **before** the overrides filtering block, add:

```python
    # ── Phase 25: Extract vol regime from the latest alert's decision trace ──
    vol_regime = "normal"
    for a in reversed(all_recent_alerts):
        dt_ctx = (a.get("decision_trace") or {}).get("context", {})
        vi = dt_ctx.get("volume_impulse", {})
        if isinstance(vi, dict) and vi.get("regime"):
            vol_regime = vi["regime"].lower()
            break

    # ── Phase 25: Auto-pilot dynamic muting ──
    auto_muted_recipes = {}
    now = time.time()
    auto_expiry = now + 120  # Auto-mutes last 2 minutes (re-evaluated every watcher cycle)

    if vol_regime == "expansion":
        # During expansion: suppress counter-trend / mean-reversion recipes
        for name in ("HTF_REVERSAL",):
            auto_muted_recipes[name] = auto_expiry
    elif vol_regime == "low":
        # During low-vol range: suppress trend-continuation recipes
        for name in ("BOS_CONTINUATION", "VOL_EXPANSION"):
            auto_muted_recipes[name] = auto_expiry
```

**Step 1.2 — Merge auto-muted recipes with manual overrides.**

Find the existing line:
```python
    overrides = _load_overrides()
```
**Replace it with:**
```python
    overrides = _load_overrides().copy()
```
**Immediately after it**, add:
```python
    # Merge auto-pilot mutes with manual mutes (auto does NOT overwrite longer manual mutes)
    if auto_muted_recipes:
        merged_muted = overrides.get("muted_recipes", {}).copy()
        for recipe_name, auto_exp in auto_muted_recipes.items():
            existing_exp = merged_muted.get(recipe_name, 0)
            if auto_exp > existing_exp:
                merged_muted[recipe_name] = auto_exp
        overrides["muted_recipes"] = merged_muted
```

**Step 1.3 — Add `auto_pilot` to the return payload.**

Find the final `return` dict in `get_dashboard_data()` (starts with `return {`).  Add this key **inside** the dict, after the `"overrides": overrides,` line:
```python
            "auto_pilot": {
                "active": len(auto_muted_recipes) > 0,
                "regime": vol_regime,
                "auto_muted": list(auto_muted_recipes.keys()),
            },
```

#### What to do in `dashboard.html`:

**Step 1.4 — Show auto-pilot status on the filter button.**

Find the existing JS block inside `ws.onmessage` that handles overrides (search for `const fBtn = document.getElementById('filterBtn')`). **Replace** that entire `if/else` block with:

```javascript
                    // Overrides + Auto-Pilot Indicator
                    state.overrides = data.overrides || {};
                    const fBtn = document.getElementById('filterBtn');
                    const ap = data.auto_pilot || {};
                    if (fBtn) {
                        if (ap.active) {
                            fBtn.textContent = '🤖 AUTO (' + (ap.auto_muted || []).length + ' muted)';
                            fBtn.className = 'pill badge-warn';
                            fBtn.title = 'Auto-pilot muting: ' + (ap.auto_muted || []).join(', ') + ' | Regime: ' + (ap.regime || 'normal');
                        } else if (state.overrides.min_score) {
                            fBtn.textContent = 'FLOOR: ' + state.overrides.min_score;
                            fBtn.className = 'pill badge-good';
                            fBtn.title = '';
                        } else {
                            fBtn.textContent = 'ALL';
                            fBtn.className = 'pill badge-neutral';
                            fBtn.title = '';
                        }
                    }
```

---

### Task 2: Active Trade Management Copilot (Dynamic Exits in Frontend)
**Goal:** Flash glowing UI prompts when it's time to take profit or move stops to breakeven, removing human emotion from trade management decisions.

#### What to do in `dashboard.html`:

**Step 2.1 — Add the Copilot HTML container.**

Find the closing `</section>` tag right after the TradingView chart widget (`<!-- TradingView Widget END -->`). **After** `</section>` and before `</div>` (the closing of `layout-grid`), insert:

```html
        <section class="panel" style="padding: 1.2rem;">
            <h2 style="margin: 0 0 0.8rem 0;">Execution Copilot</h2>
            <div id="copilot-container" style="display:flex;align-items:center;gap:1rem;">
                <div id="copilot-action-btn" class="pill badge-neutral" style="font-size:1.1rem;padding:10px 18px;white-space:nowrap;min-width:180px;text-align:center;">STANDBY</div>
                <div>
                    <div id="copilot-msg" class="mini" style="color:var(--text-muted);">No active positions</div>
                    <div id="copilot-detail" class="mini" style="color:var(--text-muted);margin-top:4px;font-family:JetBrains Mono,monospace;font-size:0.75rem;"></div>
                </div>
            </div>
        </section>
```

**Step 2.2 — Add the Copilot logic in JS.**

Inside the `ws.onmessage` callback, **after** the existing `els.sync.textContent = ...` line (near the end of the `try` block), add:

```javascript
                    // ── Phase 25: Execution Copilot ──
                    const cpAction = document.getElementById('copilot-action-btn');
                    const cpMsg = document.getElementById('copilot-msg');
                    const cpDetail = document.getElementById('copilot-detail');
                    if (cpAction && cpMsg) {
                        let cpText = 'STANDBY';
                        let cpMessage = 'No active positions — monitoring.';
                        let cpClass = 'pill badge-neutral';
                        let cpExtra = '';

                        const positions = (po.positions || []);
                        if (positions.length > 0 && state.livePrice > 0) {
                            const pos = positions[0];
                            const entry = pos.entry_price || 0;
                            const dir = pos.direction || 'LONG';
                            const sz = pos.size_usdt || 0;
                            if (entry > 0) {
                                const pnlPct = dir === 'LONG'
                                    ? ((state.livePrice - entry) / entry) * 100
                                    : ((entry - state.livePrice) / entry) * 100;
                                const pnlDollar = (pnlPct / 100) * sz;

                                cpExtra = dir + ' @ ' + fmtMoney(entry,0) + ' | PnL: ' + (pnlDollar >= 0 ? '+' : '') + '$' + Math.abs(pnlDollar).toFixed(0) + ' (' + pnlPct.toFixed(2) + '%)';

                                if (pnlPct > 1.5) {
                                    cpText = '💰 TAKE 50% + TRAIL';
                                    cpMessage = 'Massive run detected (+' + pnlPct.toFixed(2) + '%). Take partial profit and trail stop to breakeven.';
                                    cpClass = 'pill badge-good';
                                    if (cpAction) cpAction.style.animation = 'breathePulse 1.5s infinite ease-in-out';
                                } else if (pnlPct > 0.75) {
                                    cpText = '🔒 MOVE STOP → BE';
                                    cpMessage = 'Momentum intact (+' + pnlPct.toFixed(2) + '%). Trail stop to breakeven — risk-free trade.';
                                    cpClass = 'pill badge-good';
                                    if (cpAction) cpAction.style.animation = '';
                                } else if (pnlPct > 0.0) {
                                    cpText = '✊ HOLD';
                                    cpMessage = 'Position active at ' + fmtMoney(entry,0) + '. Let edge play out.';
                                    cpClass = 'pill badge-warn';
                                    if (cpAction) cpAction.style.animation = '';
                                } else if (pnlPct > -0.75) {
                                    cpText = '⚠️ PATIENCE';
                                    cpMessage = 'Minor heat (' + pnlPct.toFixed(2) + '%). Still within normal noise range.';
                                    cpClass = 'pill badge-warn';
                                    if (cpAction) cpAction.style.animation = '';
                                } else {
                                    cpText = '🚨 CUT LOSSES';
                                    cpMessage = 'Trade invalidated (' + pnlPct.toFixed(2) + '%). Market-close to protect capital.';
                                    cpClass = 'pill badge-bad';
                                    if (cpAction) cpAction.style.animation = 'breathePulse 1s infinite ease-in-out';
                                }
                            }
                        }
                        cpAction.textContent = cpText;
                        cpAction.className = cpClass;
                        cpMsg.textContent = cpMessage;
                        if (cpDetail) cpDetail.textContent = cpExtra;
                    }
```

---

### Task 3: Order Flow X-Ray (Spread & Taker Filter)
**Goal:** Warn the trader of "Fake Breakouts" and "Flash Crash" conditions by monitoring orderbook spread and taker ratio. This prevents entering trades during thin liquidity.

#### What to do in `dashboard_server.py`:

**Step 3.1 — Compute the BS-Filter warning.**

Inside `get_dashboard_data()`, **after** the line `spread = _estimate_spread(all_recent_alerts) if mid else 0.0` and **before** `stats = _portfolio_stats(...)`, add:

```python
    # ── Phase 25: Order Flow BS-Filter ──
    # Extract taker_ratio from latest alert's flow data or decision_trace
    taker_ratio = 1.0
    for a in reversed(all_recent_alerts):
        dt_ctx = (a.get("decision_trace") or {}).get("context", {})
        # Check for flow codes that indicate taker direction
        codes = (a.get("decision_trace") or {}).get("codes", [])
        if "FLOW_TAKER_BULLISH" in codes:
            taker_ratio = 1.4
            break
        elif "FLOW_TAKER_BEARISH" in codes:
            taker_ratio = 0.6
            break

    bs_filter = "CLEAR"
    bs_severity = 0  # 0=clear, 1=caution, 2=danger
    if spread > 10.0:
        bs_filter = "⚠️ THIN LIQUIDITY (Spread > $10)"
        bs_severity = 2
    elif spread > 5.0:
        bs_filter = "⚠️ WIDE SPREAD ($" + f"{spread:.1f}" + ") — Slippage risk"
        bs_severity = 1
    elif taker_ratio < 0.75:
        bs_filter = "⚠️ HEAVY SELLS — Bearish pressure"
        bs_severity = 1
    elif taker_ratio > 1.35:
        bs_filter = "⚡ HEAVY BUYS — Bullish pressure"
        bs_severity = 0
```

**Step 3.2 — Add bs_filter to the return payload.**

In the same `return` dict in `get_dashboard_data()`, add:
```python
            "bs_filter": bs_filter,
            "bs_severity": bs_severity,
```

#### What to do in `dashboard.html`:

**Step 3.3 — Add the BS-Filter display element.**

Find the Verdict Center panel — specifically the `<div>` containing `id='livePrice'`. Find the line reading:
```html
                <div class='mini'>SPREAD <span id='liveSpread'>—</span></div>
```
**After** that `</div>` (the parent flex container holding TP1/STOP/SPREAD), add:
```html
            <div id="bs-filter-display" class="mini" style="margin-top:8px;padding:6px 10px;border-radius:8px;font-weight:700;font-size:0.78rem;text-align:center;transition:all 0.3s ease;"></div>
```

**Step 3.4 — Update the BS-Filter element via JS.**

Inside `ws.onmessage`, after the line `els.sync.textContent = 'Synced: ' + new Date().toLocaleString();`, add:

```javascript
                    // ── Phase 25: BS-Filter Warning ──
                    const bsEl = document.getElementById('bs-filter-display');
                    if (bsEl) {
                        const bsText = data.bs_filter || 'CLEAR';
                        const bsSev = data.bs_severity || 0;
                        bsEl.textContent = bsText;
                        if (bsSev >= 2) {
                            bsEl.style.background = 'rgba(255,77,77,0.15)';
                            bsEl.style.color = '#ff4d4d';
                            bsEl.style.border = '1px solid rgba(255,77,77,0.4)';
                        } else if (bsSev >= 1) {
                            bsEl.style.background = 'rgba(255,165,0,0.1)';
                            bsEl.style.color = '#ffa500';
                            bsEl.style.border = '1px solid rgba(255,165,0,0.3)';
                        } else {
                            bsEl.style.background = 'transparent';
                            bsEl.style.color = 'var(--text-muted)';
                            bsEl.style.border = '1px solid transparent';
                        }
                    }
```

---

### Task 4: Kelly Sizing Enforcer in Execute Modal
**Goal:** Never let the trader over-leverage a trade. Inject the mathematically calculated maximum dollar risk into the execution confirmation modal.

#### What to do in `dashboard.html`:

**Step 4.1 — Find the `requestExecute` function.**

There is a function generated by `generate_dashboard.py` embedded in the static HTML. Search for `onclick="requestExecute('latest-btc')"` on the Execute button. The `requestExecute` function is defined in the `<script>` block at the bottom. If it does NOT exist in `dashboard.html` yet, add it. If it already exists, **modify** it.

Add/replace the `requestExecute` function with:

```javascript
        function requestExecute(alertId) {
            const modal = document.getElementById('executeModal');
            if (!modal) return;
            modal.style.display = 'flex';

            // Kelly sizing calculation — uses cached stats set in ws.onmessage (Step 4.2)
            const cachedStats = window._lastStats || {};
            const kelly = cachedStats.kelly_pct || 0.05;
            const bal = window._lastBalance || 10000;
            const maxRisk = kelly * bal;

            const metaEl = document.getElementById('executeMeta');
            metaEl.innerHTML = 'Alert: ' + alertId
                + '<br>Direction: ' + state.direction
                + '<br>Live: ' + fmtMoney(state.livePrice, 0)
                + '<br><br><div style="padding:10px;border:1px solid #ff4d4d;border-radius:8px;background:rgba(255,0,0,0.08);">'
                + '<span style="color:#ff4d4d;font-weight:bold;font-size:1rem;">MAX RISK: ' + fmtMoney(maxRisk, 2) + '</span><br>'
                + '<span class="mini" style="color:var(--text-muted);">Kelly: ' + (kelly * 100).toFixed(1) + '% · Balance: ' + fmtMoney(bal, 0) + '</span><br>'
                + '<span class="mini" style="color:#ff4d4d;">Exceeding this violates your mathematical edge.</span></div>';

            const btn = document.getElementById('confirmExecuteBtn');
            let n = 3;
            btn.disabled = true;
            btn.textContent = 'Confirm (' + n + ')';
            const t = setInterval(() => {
                n -= 1;
                if (n <= 0) {
                    clearInterval(t);
                    btn.disabled = false;
                    btn.textContent = 'Confirm Execute';
                    btn.onclick = () => closeExecuteModal();
                } else {
                    btn.textContent = 'Confirm (' + n + ')';
                }
            }, 1000);
        }

        function closeExecuteModal() {
            const modal = document.getElementById('executeModal');
            if (modal) modal.style.display = 'none';
        }
```

**Step 4.2 — Cache stats data for the modal.**

> ⚠️ **DO NOT SKIP THIS STEP.** Without it, `requestExecute()` will always show the fallback Kelly (5%) and $10,000 balance because `window._lastStats` is never populated.

Inside `ws.onmessage`, find the existing line:
```javascript
                    const st = data.stats || {};
```
**Immediately after** it (before any line that uses `st`), add these two lines:
```javascript
                    window._lastStats = st;
                    window._lastBalance = Number(po.balance || 0);
```
These globals make live Kelly % and balance available to the `requestExecute()` function (which runs outside the WS callback). Without them, the execute modal will show incorrect risk limits.

---

### Task 5: Drawdown Circuit Breaker (Account Protector)
**Goal:** When the portfolio is in a significant drawdown, visually warn the trader and auto-suppress ALL trade execution. This prevents emotional revenge-trading after a losing streak.

#### What to do in `dashboard_server.py`:

**Step 5.1 — Add drawdown guard to the return payload.**

Inside `get_dashboard_data()`, **after** `stats = _portfolio_stats(portfolio, current_price=mid, alerts=all_recent_alerts)`, add:

```python
    # ── Phase 25: Drawdown Circuit Breaker ──
    dd_pct = stats.get("drawdown_pct", 0.0)
    streak = stats.get("streak", 0)
    circuit_breaker = {
        "active": dd_pct > 8.0 or streak <= -4,
        "reason": "",
        "dd_pct": dd_pct,
        "streak": streak,
    }
    if dd_pct > 8.0:
        circuit_breaker["reason"] = f"Drawdown {dd_pct:.1f}% exceeds 8% threshold"
    elif streak <= -4:
        circuit_breaker["reason"] = f"Losing streak of {abs(streak)} — stop and reassess"
```

Add to the return dict:
```python
            "circuit_breaker": circuit_breaker,
```

#### What to do in `dashboard.html`:

**Step 5.2 — Disable execution button and show warning during circuit break.**

Inside `ws.onmessage`, **after** the Copilot block, add:

```javascript
                    // ── Phase 25: Drawdown Circuit Breaker ──
                    const cb = data.circuit_breaker || {};
                    const execBtn = document.getElementById('executeBtn');
                    if (execBtn) {
                        if (cb.active) {
                            execBtn.disabled = true;
                            execBtn.textContent = '⛔ CIRCUIT BREAKER (' + (cb.reason || 'high risk') + ')';
                            execBtn.style.opacity = '0.5';
                            execBtn.style.cursor = 'not-allowed';
                        } else {
                            execBtn.disabled = false;
                            execBtn.style.opacity = '1';
                            execBtn.style.cursor = 'pointer';
                        }
                    }
```

---

## ✅ VERIFICATION CHECKLIST FOR THE IMPLEMENTING AGENT

After all 5 tasks are complete, verify each of the following:

1. **Syntax Check**: Run `python scripts/pid-129/dashboard_server.py`. It must start with zero errors.

2. **Task 1 — Auto-Pilot**: Open `http://localhost:8000/`. Check the filter button in the Verdict Center:
   - If the latest alert's vol regime is `expansion`, the button should show `🤖 AUTO (1 muted)` and its tooltip should mention `HTF_REVERSAL`.
   - If the vol regime is `low`, the button should show `🤖 AUTO (2 muted)` and mention `BOS_CONTINUATION, VOL_EXPANSION`.
   - If the vol regime is `normal`, the button should show `ALL` (or `FLOOR: N` if a manual floor is set).

3. **Task 2 — Copilot**: If `portfolio.positions` has an open trade:
   - The Copilot section should show the correct PnL percentage calculation.
   - With > 1.5% profit it should pulse green with "TAKE 50% + TRAIL".
   - With losing trade < -0.75% it should pulse red with "CUT LOSSES".
   - With no positions open it should show "STANDBY".

4. **Task 3 — BS Filter**: Check the new element appears below the SPREAD indicator.
   - With spread = $3 it should be invisible/CLEAR.
   - The logic is: spread > $10 → red, spread > $5 → orange, else check taker codes.

5. **Task 4 — Kelly Enforcer**: Click the Execute button.
   - The modal should show `MAX RISK: $xxx.xx` calculated as `kelly_pct × balance`.
   - The 3-second countdown timer should still work.

6. **Task 5 — Circuit Breaker**: If `drawdown_pct > 8.0` or `streak <= -4`:
   - The Execute button should be disabled with a `⛔ CIRCUIT BREAKER` message.
   - Under normal conditions, the button should be enabled as before.

7. **No JS Console Errors**: Open the browser developer console. There should be zero errors related to Phase 25 changes.

---

## 🔍 COMMON PITFALLS TO AVOID

| # | Mistake | Correct Approach |
|---|---------|-----------------|
| 1 | Using `get_live_tape()` | This function does NOT exist. Extract regime from `all_recent_alerts` via `decision_trace.context.volume_impulse.regime`. |
| 2 | Treating `muted_recipes` as a list | It is a **dict** `{ recipe_name: expiry_timestamp }`. |
| 3 | Using `dataCache` in JS | This variable does not exist. Use the `state` object or `window._lastStats`. |
| 4 | Referencing `tape_data` or `tape` | No such variable in `dashboard_server.py`. Alert data comes from `_load_alerts()`. |
| 5 | Using `VAH_FADE` or `VAL_FADE` as recipe names | Only three recipes exist: `HTF_REVERSAL`, `BOS_CONTINUATION`, `VOL_EXPANSION`. |
| 6 | Adding `taker_ratio` to the return dict without a source | The dashboard server does NOT have direct access to flow data. Extract taker direction from alert codes. |
| 7 | Forgetting to add `closeExecuteModal` function | If it doesn't exist, you must add it alongside `requestExecute`. |
| 8 | Skipping Step 4.2 (`window._lastStats` caching) | `requestExecute()` reads `window._lastStats` — if you don't set it in `ws.onmessage`, the modal will always show the 5% fallback Kelly and $10,000 default. |

---

_Phase 25 | The Execution Co-Pilot & Regime Auto-Tuner | Formatted for AI Agent Implementation_
