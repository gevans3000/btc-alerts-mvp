# Phase 10: The Operator's Edge Trading Intelligence Hardening

> **INSTRUCTIONS FOR AI AGENT:** Execute every step below IN ORDER. After each step, run the verification command. If it passes, mark the checkbox `[ ]` ΓåÆ `[x]`. If it fails, fix the issue before moving to the next step. Do NOT skip steps. Do NOT commit until ALL checkboxes are marked `[x]`.

---

## CRITICAL RULES (Read Before Starting)

1. **You are editing exactly 2 files:** `scripts/pid-129/generate_dashboard.py` and `scripts/pid-129/dashboard_server.py`. The output file `dashboard.html` is auto-generated ΓÇö never edit it directly.
2. **Python f-string + JavaScript conflict:** The generated HTML uses Python f-strings. JavaScript `{}` braces MUST be doubled `{{}}`. JavaScript template literals (`${var}`) MUST use helper variables:
   ```python
   JS_OPEN = "${"
   JS_CLOSE = "}"
   ```
3. **All paths are relative to project root:** `c:\Users\lovel\trading\btc-alerts-mvp\`
4. **Do NOT install new packages.** Only use: `json`, `pathlib`, `datetime` (Python); `Chart.js` v4.4.1 (CDN already loaded); TradingView widget (CDN already loaded).
5. **Verification command after every step:** `python scripts/pid-129/generate_dashboard.py` ΓÇö it must print `Dashboard updated:` with no errors.
6. **After ALL steps complete:** Run `python -m pytest tests/ -x -q` to ensure nothing is broken.

---

## ≡ƒºá Why This Phase Exists

The Phase 9 dashboard looks premium but has **critical gaps for actual trading decisions:**

1. **No live BTC price** ΓÇö the operator cannot see where price is relative to their entry/TP/SL without scanning the TradingView chart manually.
2. **No risk gate** ΓÇö the system recommends LONG with 98% ML confidence while on a -1 streak and conflicting timeframes. The operator has no warning.
3. **No equity curve** ΓÇö the operator can't tell if the system is in a drawdown phase or on a heater.
4. **Empty confluence heatmap** ΓÇö the `score_breakdown` data sometimes isn't available, leaving the heatmap blank.
5. **"UNKNOWN REGIME"** ΓÇö the regime detection falls through when alerts don't contain that field.
6. **No confirmation before executing** ΓÇö 1-Click Execute fires immediately with no "Are you sure?" gate.

This phase fixes all of these problems.

---

## ≡ƒôÉ Architecture Reference

**Existing data already available in WebSocket payload (`dashboard_server.py` ΓåÆ `get_dashboard_data()`):**
```json
{
  "orderbook": {"bid": 64300, "ask": 64310, "mid": 64305, "spread": 10},
  "portfolio": {"balance": 9279, "positions": [...], "max_drawdown": 0.069},
  "alerts": [...],
  "stats": {"win_rate": 60, "profit_factor": 4.8, "avg_r": 1.2, "streak": -1},
  "logs": "..."
}
```

**Key insight:** The `orderbook.mid` field already gives us the **live BTC price** every 2 seconds via WebSocket. We just need to render it.

---

## ≡ƒôï EXECUTION STEPS

---

### STEP 1: Add Live BTC Price to the Verdict Card
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** Add a real-time BTC price display to the Verdict card that updates via WebSocket. Show the price, the distance to TP1 and invalidation, and the unrealized PnL if in a position.

**Action 1:** Add an HTML element inside the Verdict card, AFTER the direction text and BEFORE the price levels grid. Place this inside the `<div class="glass-card card-verdict ...">` block:

```html
<!-- Live Price Ticker insert AFTER the direction div, BEFORE the price grid -->
<div style="background: rgba(255,255,255,0.03); border-radius: 12px; padding: 1rem; margin-bottom: 1.5rem; border: 1px solid var(--border);">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <div class="metric-label">Live BTC Price</div>
            <div id="livePrice" style="font-size: 1.8rem; font-weight: 900; font-family: var(--font-mono); color: var(--text-primary);">Loading...</div>
        </div>
        <div style="text-align: right;">
            <div class="metric-label">Unrealized PnL</div>
            <div id="livePnL" style="font-size: 1.2rem; font-weight: 800; font-family: var(--font-mono); color: var(--text-secondary);">ΓÇö</div>
        </div>
    </div>
    <div style="display: flex; gap: 1.5rem; margin-top: 0.8rem; font-size: 0.75rem; font-family: var(--font-mono);">
        <div>
            <span style="color: var(--text-secondary);">ΓåÆ TP1: </span>
            <span id="distTP1" style="color: var(--accent);">ΓÇö</span>
        </div>
        <div>
            <span style="color: var(--text-secondary);">ΓåÆ STOP: </span>
            <span id="distStop" style="color: var(--danger);">ΓÇö</span>
        </div>
        <div>
            <span style="color: var(--text-secondary);">SPREAD: </span>
            <span id="liveSpread" style="color: var(--text-secondary);">ΓÇö</span>
        </div>
    </div>
</div>
```

**Important f-string note:** This HTML block contains NO Python variables, so no `{ctx[...]}` or `{{}}` escaping is needed. Drop it in as-is inside the f-string.

**Action 2:** Add these properties to the JS `state` object (inside `generate_html()`, in the `let state = {{ ... }}` block):

```javascript
// Add to the state object:
livePrice: 0,
spread: 0,
entryPrice: {ctx["verdict"]["entry"]},
tp1Price: {ctx["verdict"]["tp1"]},
stopPrice: {ctx["verdict"]["invalidation"]},
direction: "{ctx["verdict"]["direction"]}"
```

**Action 3:** Add a new JS function `updateLivePrice()` and call it from `updateUI()`. Put this function BEFORE the `updateUI()` function:

```javascript
function updateLivePrice() {{
    const el = document.getElementById('livePrice');
    if (!el || !state.livePrice) return;
    
    el.innerText = '$' + state.livePrice.toLocaleString(undefined, {{minimumFractionDigits: 0, maximumFractionDigits: 0}});
    
    // Distance to targets
    if (state.entryPrice > 0 && state.tp1Price > 0) {{
        const toTP1 = state.tp1Price - state.livePrice;
        const toStop = state.stopPrice - state.livePrice;
        const toTP1Pct = ((toTP1 / state.livePrice) * 100).toFixed(2);
        const toStopPct = ((toStop / state.livePrice) * 100).toFixed(2);
        
        document.getElementById('distTP1').innerText = (toTP1 >= 0 ? '+' : '') + '$' + Math.abs(toTP1).toFixed(0) + ' (' + toTP1Pct + '%)';
        document.getElementById('distStop').innerText = (toStop >= 0 ? '+' : '') + '$' + Math.abs(toStop).toFixed(0) + ' (' + toStopPct + '%)';
    }}
    
    // Spread
    document.getElementById('liveSpread').innerText = '$' + state.spread.toFixed(1);
    
    // Unrealized PnL (if in position)
    if (state.inTrade && state.entryPrice > 0) {{
        const multiplier = state.direction === 'LONG' ? 1 : -1;
        const pnlDollar = (state.livePrice - state.entryPrice) * multiplier;
        const pnlPct = ((pnlDollar / state.entryPrice) * 100);
        const pnlEl = document.getElementById('livePnL');
        pnlEl.innerText = (pnlDollar >= 0 ? '+' : '') + '$' + pnlDollar.toFixed(0) + ' (' + pnlPct.toFixed(2) + '%)';
        pnlEl.style.color = pnlDollar >= 0 ? 'var(--accent)' : 'var(--danger)';
    }}
    
    // Color the price based on position relative to entry
    if (state.entryPrice > 0) {{
        const isAboveEntry = state.livePrice >= state.entryPrice;
        const favourable = (state.direction === 'LONG' && isAboveEntry) || (state.direction === 'SHORT' && !isAboveEntry);
        el.style.color = favourable ? 'var(--accent)' : 'var(--danger)';
    }}
}}
```

**Action 4:** In the `updateUI()` function, add this call at the END (after all existing updates):
```javascript
updateLivePrice();
```

**Action 5:** In the `connectWS()` `ws.onmessage` handler, add this AFTER the existing `if (data.portfolio)` block:
```javascript
if (data.orderbook && data.orderbook.mid) {{
    state.livePrice = data.orderbook.mid;
    state.spread = data.orderbook.spread || 0;
}}
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` ΓÇö no errors. Start the server (`python scripts/pid-129/dashboard_server.py`), open `http://localhost:8000`, confirm the live price ticks every 2 seconds.

---

### STEP 2: Add the Risk Gate (Trade Safety Checklist)
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** Add a colored "TRADE SAFETY" checklist between the conviction signals and the execute button. This checklist evaluates 5 conditions and shows a RED/AMBER/GREEN overall verdict. If RED, the execute button should be styled as a warning.

**Action 1:** In the `build_context()` function, add a `risk_gate` dict to the returned context. Add this BEFORE the `return` statement:

```python
    # Risk Gate checks
    tf_directions = [v["direction"] for v in tf_bias.values()]
    tf_aligned = len(set(tf_directions)) == 1 and len(tf_directions) > 1
    
    gate_checks = {
        "tf_aligned": {"pass": tf_aligned, "label": "Timeframes Aligned", "icon_pass": "Γ£à", "icon_fail": "ΓÜá∩╕Å"},
        "ml_confident": {"pass": ml_pct >= 60 if best_idea else False, "label": "ML Confidence ΓëÑ 60%", "icon_pass": "Γ£à", "icon_fail": "Γ¥î"},
        "streak_ok": {"pass": streak >= -2, "label": "Streak ΓëÑ -2", "icon_pass": "Γ£à", "icon_fail": "≡ƒºè"},
        "dd_ok": {"pass": max_dd < 10, "label": "Drawdown < 10%", "icon_pass": "Γ£à", "icon_fail": "≡ƒö┤"},
        "rr_ok": {"pass": verdict["rr_ratio"] >= 1.5, "label": "R:R ΓëÑ 1.5x", "icon_pass": "Γ£à", "icon_fail": "ΓÜá∩╕Å"},
    }
    
    gate_pass_count = sum(1 for g in gate_checks.values() if g["pass"])
    gate_total = len(gate_checks)
    if gate_pass_count >= 4:
        gate_verdict = "GREEN"
    elif gate_pass_count >= 3:
        gate_verdict = "AMBER"
    else:
        gate_verdict = "RED"
```

Note: `ml_pct` is calculated later so we need to handle this. Instead, compute the ML check inline:
```python
    _ml_pct = verdict["ml_prob"] * 100
    gate_checks = {
        "tf_aligned": {"pass": tf_aligned, "label": "Timeframes Aligned", "icon_pass": "Γ£à", "icon_fail": "ΓÜá∩╕Å"},
        "ml_confident": {"pass": _ml_pct >= 60, "label": "ML Confidence ΓëÑ 60%", "icon_pass": "Γ£à", "icon_fail": "Γ¥î"},
        "streak_ok": {"pass": streak >= -2, "label": "Streak ΓëÑ -2", "icon_pass": "Γ£à", "icon_fail": "≡ƒºè"},
        "dd_ok": {"pass": max_dd < 10, "label": "Drawdown < 10%", "icon_pass": "Γ£à", "icon_fail": "≡ƒö┤"},
        "rr_ok": {"pass": verdict["rr_ratio"] >= 1.5, "label": "R:R ΓëÑ 1.5x", "icon_pass": "Γ£à", "icon_fail": "ΓÜá∩╕Å"},
    }
```

Add to the return dict:
```python
        "gate_checks": gate_checks,
        "gate_pass_count": gate_pass_count,
        "gate_total": gate_total,
        "gate_verdict": gate_verdict,
```

**Action 2:** In `generate_html()`, pre-render the risk gate HTML in Python. Add this AFTER the `signals_html` block:

```python
    # Risk Gate HTML
    gate_color = "var(--accent)" if ctx["gate_verdict"] == "GREEN" else "var(--warning)" if ctx["gate_verdict"] == "AMBER" else "var(--danger)"
    gate_bg = "rgba(0,255,204,0.05)" if ctx["gate_verdict"] == "GREEN" else "rgba(255,170,0,0.05)" if ctx["gate_verdict"] == "AMBER" else "rgba(255,77,109,0.05)"
    
    gate_html = f'''
    <div style="background: {gate_bg}; border: 1px solid {gate_color}; border-radius: 12px; padding: 1rem; margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem;">
            <span class="metric-label" style="margin-bottom: 0;">Trade Safety</span>
            <span style="font-weight: 900; color: {gate_color}; font-size: 0.8rem;">{ctx["gate_verdict"]} ({ctx["gate_pass_count"]}/{ctx["gate_total"]})</span>
        </div>'''
    
    for key, check in ctx["gate_checks"].items():
        icon = check["icon_pass"] if check["pass"] else check["icon_fail"]
        text_color = "var(--text-primary)" if check["pass"] else "var(--danger)"
        gate_html += f'''
        <div style="display: flex; align-items: center; gap: 8px; font-size: 0.75rem; margin-bottom: 4px; color: {text_color};">
            <span>{icon}</span>
            <span>{check["label"]}</span>
        </div>'''
    
    gate_html += '</div>'
```

**Action 3:** In the HTML body, insert `{gate_html}` inside the Verdict card, AFTER the `{signals_html}` div and BEFORE the execute button. Find this line:
```python
                {f'<button class="action-btn" onclick="executeTrade(
```
And add `{gate_html}` on the line directly before it.

**Action 4:** If gate_verdict is RED, change the execute button styling. Replace the existing execute button line with:
```python
                {f'<button class="action-btn" style="{"background: var(--danger);" if ctx["gate_verdict"] == "RED" else ""}" onclick="executeTrade(\'{ctx["verdict"]["alert_id"]}\')">{"ΓÜá∩╕Å EXECUTE (HIGH RISK)" if ctx["gate_verdict"] == "RED" else "1-CLICK EXECUTE"}</button>' if ctx["verdict"]["direction"] != "WAIT" else ""}
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` ΓÇö no errors. Open dashboard, confirm the safety checklist renders with pass/fail icons.

---

### STEP 3: Add Equity Curve Sparkline (Chart.js)
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** Replace the "Recent Performance" section in Zone D with a small equity curve chart using Chart.js (already loaded via CDN). Plot balance after each resolved trade.

**Action 1:** In the `build_context()` function, build an equity history array. Add this AFTER the streak calculation block and BEFORE the `# Portfolio` comment:

```python
    # Equity curve data points
    equity_curve = [10000]  # starting balance
    for a in resolved:
        r = a.get("r_multiple", 0)
        if r is not None:
            # Each trade risks ~1% of current balance, result = r * risk
            last_bal = equity_curve[-1]
            pnl_trade = last_bal * 0.01 * r  # 1% risk per trade
            equity_curve.append(round(last_bal + pnl_trade, 2))
    equity_labels = list(range(len(equity_curve)))
```

Add to return dict:
```python
        "equity_curve": equity_curve,
        "equity_labels": equity_labels,
```

**Action 2:** In the HTML body, find the "Recent Performance" `glass-card` in Zone D. Replace the stats grid + trades list with a chart canvas and the trades below it. Find this block:
```html
                <!-- ZONE D: PERFORMANCE -->
                <div class="glass-card">
                    <h3 style="...">Recent Performance</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; ...">
```

Replace the ENTIRE performance `glass-card` div with:
```html
                <div class="glass-card">
                    <h3 style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.8rem; color: var(--text-secondary);">Equity Curve</h3>
                    <div style="height: 150px; margin-bottom: 1rem;">
                        <canvas id="equityChart"></canvas>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 1rem; font-size: 0.75rem;">
                        <div class="metric">
                            <div class="metric-label">Avg R</div>
                            <div class="metric-value" style="font-size: 0.9rem;">{ctx["avg_r"]:.2f}x</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">PF</div>
                            <div class="metric-value" style="font-size: 0.9rem;">{ctx["profit_factor"]:.1f}x</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Streak</div>
                            <div class="metric-value" style="font-size: 0.9rem; color: {"var(--accent)" if ctx["streak"] > 0 else "var(--danger)"}">{ctx["streak"]:+d}</div>
                        </div>
                    </div>
                    <div id="recentTradesList">
                        {trades_html}
                    </div>
                </div>
```

**Action 3:** In the `<script>` block, AFTER the TradingView widget initialization and BEFORE the `let state` line, add the Chart.js initialization:

```javascript
    // --- Equity Curve Chart ---
    const eqCtx = document.getElementById('equityChart');
    if (eqCtx) {{
        new Chart(eqCtx, {{
            type: 'line',
            data: {{
                labels: {ctx["equity_labels"]},
                datasets: [{{
                    data: {ctx["equity_curve"]},
                    borderColor: '#00ffcc',
                    backgroundColor: 'rgba(0, 255, 204, 0.05)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#00ffcc'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: (ctx) => '$' + ctx.parsed.y.toLocaleString()
                        }}
                    }}
                }},
                scales: {{
                    x: {{ display: false }},
                    y: {{
                        display: true,
                        grid: {{ color: 'rgba(255,255,255,0.03)' }},
                        ticks: {{
                            color: '#94a3b8',
                            font: {{ size: 10, family: "'JetBrains Mono'" }},
                            callback: (val) => '$' + val.toLocaleString()
                        }}
                    }}
                }}
            }}
        }});
    }}
```

**IMPORTANT f-string note:** The `{ctx["equity_labels"]}` and `{ctx["equity_curve"]}` will render as Python lists which are valid JSON arrays. The `(ctx)` in the tooltip callback is a JavaScript variable ΓÇö it does NOT conflict with the Python `ctx` because it's inside doubled braces `{{}}`. However, the `(ctx)` will be eaten by the f-string parser. **Rename the JS callback parameter** to avoid this:

```javascript
                            label: (c) => '$' + c.parsed.y.toLocaleString()
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` ΓÇö no errors. Open `dashboard.html`, confirm the sparkline chart shows the equity curve.

---

### STEP 4: Fix Empty Confluence Heatmap
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** The confluence heatmap is empty because `score_breakdown` sometimes isn't in the alert's top-level or decision_trace. Fix the data extraction to be more resilient.

**Action:** In `build_context()`, find the `# Confluence layers from verdict` section. Replace it with:

```python
    # Confluence layers from verdict ΓÇö with fallbacks
    confluence_layers = {}
    if best_idea:
        trace = best_idea.get("decision_trace", {})
        # Try multiple sources for score breakdown
        sb = best_idea.get("score_breakdown", {})
        if not sb:
            sb = trace.get("score_breakdown", {})
        if not sb:
            # Fallback: use confluence layers from context
            sb = trace.get("context", {}).get("confluence", {}).get("layers", {})
        if not sb:
            # Final fallback: construct from known keys
            ctx_data = trace.get("context", {})
            if ctx_data:
                sb = {}
                # Build synthetic scores from available context
                confluence = ctx_data.get("confluence", {})
                if confluence.get("bullish_count", 0) > 0 or confluence.get("bearish_count", 0) > 0:
                    sb["bullish"] = confluence.get("bullish_count", 0)
                    sb["bearish"] = -confluence.get("bearish_count", 0)
                if ctx_data.get("squeeze", "OFF") == "SQUEEZE_FIRE":
                    sb["squeeze"] = 5.0
                elif ctx_data.get("squeeze", "OFF") == "SQUEEZE_ON":
                    sb["squeeze"] = 2.0
                fg = ctx_data.get("fear_greed", {}).get("value", 50)
                if fg < 25:
                    sb["fear_greed"] = 3.0  # contrarian bullish
                elif fg > 75:
                    sb["fear_greed"] = -3.0  # contrarian bearish
                ml_prob = trace.get("models", {}).get("ml_prob", 0.5)
                sb["ml_confidence"] = round((ml_prob - 0.5) * 20, 1)  # scale to ┬▒10

        confluence_layers = {k: v for k, v in sb.items() if k != "penalty" and v != 0}
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` ΓÇö no errors. Open dashboard, confluence heatmap should now show bars.

---

### STEP 5: Fix "UNKNOWN REGIME" Badge
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** The regime detection falls through too easily. Add a price-action-based fallback that checks recent alert directions to infer the regime.

**Action:** In `build_context()`, find the `# Regime from latest alert` section. Replace it with:

```python
    # Regime from latest alert ΓÇö with smart fallback
    regime = "unknown"
    if best_idea:
        regime = best_idea.get("decision_trace", {}).get("context", {}).get("regime", "unknown")
    if regime == "unknown" and all_alerts:
        for a in reversed(all_alerts[-10:]):
            r = a.get("decision_trace", {}).get("context", {}).get("regime")
            if r and r != "unknown":
                regime = r
                break
    # Price-action fallback: infer from recent directions
    if regime == "unknown" and len(all_alerts) >= 3:
        recent_dirs = [a.get("direction") for a in all_alerts[-5:] if a.get("direction") in ("LONG", "SHORT")]
        if recent_dirs:
            long_count = recent_dirs.count("LONG")
            short_count = recent_dirs.count("SHORT")
            if long_count > short_count * 2:
                regime = "trending_up"
            elif short_count > long_count * 2:
                regime = "trending_down"
            elif abs(long_count - short_count) <= 1:
                regime = "ranging"
            else:
                regime = "choppy"
    if regime == "unknown":
        regime = "indeterminate"
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` ΓÇö no errors. Badge should no longer show "UNKNOWN".

---

### STEP 6: Add Confirmation Modal to Execute Button
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** Prevent accidental trades. When the operator clicks "1-CLICK EXECUTE", show a 3-second confirmation overlay with trade details before actually firing.

**Action 1:** Add a hidden modal overlay to the HTML body. Put this at the END of the `<div class="container">`, just BEFORE the closing `</div>`:

```html
<!-- Execution Confirmation Modal -->
<div id="execModal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.85); z-index:9999; display:none; align-items:center; justify-content:center;">
    <div class="glass-card" style="max-width: 400px; text-align: center; border: 2px solid var(--accent);">
        <h2 style="font-size: 1.5rem; font-weight: 900; margin-bottom: 1rem;">CONFIRM EXECUTION</h2>
        <div id="execModalBody" style="margin-bottom: 1.5rem; font-family: var(--font-mono); font-size: 0.9rem; color: var(--text-secondary);"></div>
        <div style="display: flex; gap: 1rem;">
            <button class="action-btn" style="background: var(--danger); flex: 1;" onclick="closeExecModal()">CANCEL</button>
            <button class="action-btn" id="execConfirmBtn" style="flex: 1;" disabled>CONFIRM (<span id="execCountdown">3</span>s)</button>
        </div>
    </div>
</div>
```

**Action 2:** Replace the JS `executeTrade()` function with a two-step flow. Replace the ENTIRE existing `executeTrade` function with:

```javascript
    let execPendingId = null;
    let execTimer = null;

    function requestExecute(alertId) {{
        execPendingId = alertId;
        const modal = document.getElementById('execModal');
        modal.style.display = 'flex';
        
        // Populate modal body
        const body = document.getElementById('execModalBody');
        body.innerHTML = '<div style="font-size: 1.5rem; font-weight: 900; color: ' + 
            (state.direction === 'LONG' ? 'var(--accent)' : 'var(--danger)') + 
            ';">' + state.direction + '</div>' +
            '<div style="margin-top: 8px;">Entry: $' + state.entryPrice.toLocaleString() + '</div>' +
            '<div>TP1: $' + state.tp1Price.toLocaleString() + '</div>' +
            '<div>Stop: $' + state.stopPrice.toLocaleString() + '</div>' +
            '<div style="margin-top: 8px; color: var(--warning);">Live: $' + (state.livePrice || 0).toLocaleString() + '</div>';
        
        // 3-second countdown
        let count = 3;
        const confirmBtn = document.getElementById('execConfirmBtn');
        confirmBtn.disabled = true;
        document.getElementById('execCountdown').innerText = count;
        
        execTimer = setInterval(() => {{
            count--;
            document.getElementById('execCountdown').innerText = count;
            if (count <= 0) {{
                clearInterval(execTimer);
                confirmBtn.disabled = false;
                confirmBtn.innerText = 'CONFIRM NOW';
                confirmBtn.onclick = () => confirmExecute();
            }}
        }}, 1000);
    }}

    function closeExecModal() {{
        document.getElementById('execModal').style.display = 'none';
        execPendingId = null;
        if (execTimer) clearInterval(execTimer);
    }}

    async function confirmExecute() {{
        if (!execPendingId) return;
        closeExecModal();
        
        try {{
            const response = await fetch('/execute', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ alert_id: execPendingId }})
            }});
            const result = await response.json();
            const statusBar = document.getElementById('opState');
            if (result.status === "SUCCESS") {{
                statusBar.innerText = "Γ£à TRADE EXECUTED SUCCESSFULLY";
                statusBar.style.background = "rgba(34, 197, 94, 0.1)";
                statusBar.style.color = "var(--win)";
                statusBar.style.borderColor = "var(--win)";
            }} else {{
                statusBar.innerText = "Γ¥î EXECUTION FAILED: " + (result.message || "Unknown error");
                statusBar.style.background = "rgba(255, 77, 109, 0.1)";
                statusBar.style.color = "var(--danger)";
                statusBar.style.borderColor = "var(--danger)";
            }}
        }} catch (e) {{
            console.error(e);
        }}
    }}
```

**Action 3:** Update the execute button `onclick` to call `requestExecute` instead of `executeTrade`. Find:
```python
onclick="executeTrade(
```
Replace with:
```python
onclick="requestExecute(
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` ΓÇö no errors. Click execute button in browser, confirm modal appears with 3-second countdown.

---

### STEP 7: Final Integration Test
- [x] **DONE**

**Run these commands in order:**

```
python scripts/pid-129/generate_dashboard.py
python -m pytest tests/ -x -q
```

**Manual browser check (open `http://localhost:8000` with the server running):**
- [x] Live BTC price updates every 2 seconds on the Verdict card
- [x] Distance to TP1 and Stop displayed in $ and %
- [x] Unrealized PnL shows when in a position
- [x] Risk Gate checklist shows 5 items with pass/fail icons
- [x] Execute button shows "ΓÜá∩╕Å EXECUTE (HIGH RISK)" when gate is RED
- [x] Equity curve sparkline renders with Chart.js
- [x] Confluence heatmap is no longer empty
- [x] Regime badge no longer shows "UNKNOWN"
- [x] Execute modal appears with 3-second countdown before confirming
- [x] No JavaScript console errors

---

## ≡ƒÜ½ Out of Scope (Do NOT Implement)

- No external JS frameworks (React, Vue, etc.)
- No new Python dependencies
- No new API endpoints ΓÇö use existing WebSocket payload
- No audio/sound features
- No position management buttons (FLATTEN, SCALE OUT)
- No mobile app ΓÇö responsive web only
- No multi-exchange funding rate comparison (Phase 11)
- No pattern recognition / ghost patterns

---

## ≡ƒôü Files Modified

| File | Change |
|:--|:--|
| `scripts/pid-129/generate_dashboard.py` | Live price ticker, risk gate, equity curve, confluence fix, regime fix, exec modal |
| `scripts/pid-129/dashboard_server.py` | No changes ΓÇö existing `orderbook.mid` and `stats` payload already provides needed data |
| `dashboard.html` | Auto-generated output (never edit directly) |

---

## Γ£à COMPLETION CRITERIA

All 7 checkboxes above must be `[x]`. Then:
1. Run `python scripts/pid-129/generate_dashboard.py` one final time
2. Start the server: `python scripts/pid-129/dashboard_server.py`
3. Open `http://localhost:8000` in browser
4. Confirm all 10 manual checks pass
5. Take a screenshot for operator review
6. **DO NOT COMMIT** ΓÇö wait for operator approval

---
*Phase 10 The Operator's Edge | Created: 2026-02-24*
