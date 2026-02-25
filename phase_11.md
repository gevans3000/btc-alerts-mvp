# Phase 11: Confluence Alignment Radar — Unified Signal Intelligence

> **INSTRUCTIONS FOR AI AGENT:** Execute every step below IN ORDER. After each step, run the verification command. If it passes, mark the checkbox `[ ]` → `[x]`. If it fails, fix the issue before moving to the next step. Do NOT skip steps. Do NOT commit until ALL checkboxes are marked `[x]`.

---

## ⚠️ CRITICAL RULES (Read Before Starting)

1. **You are editing exactly 1 file:** `scripts/pid-129/generate_dashboard.py`. The output file `dashboard.html` is auto-generated — never edit it directly.
2. **Python f-string + JavaScript conflict:** The generated HTML uses Python f-strings. JavaScript `{}` braces MUST be doubled `{{}}`. JavaScript template literals (`${var}`) MUST use helper variables:
   ```python
   JS_OPEN = "${"
   JS_CLOSE = "}"
   ```
3. **All paths are relative to project root:** `c:\Users\lovel\trading\btc-alerts-mvp\`
4. **Do NOT install new packages.** Only use: `json`, `pathlib`, `datetime` (Python); `Chart.js` v4.4.1 (CDN already loaded); TradingView widget (CDN already loaded).
5. **Verification command after every step:** `python scripts/pid-129/generate_dashboard.py` — it must print `Dashboard updated:` with no errors.
6. **After ALL steps complete:** Run `python -m pytest tests/ -k "not test_genetic_optimization" -x -q` to ensure nothing is broken.

---

## 🧠 Why This Phase Exists

The dashboard currently shows confluence data in **three disconnected places:**

1. **Conviction Signals**: A text list of fired codes like "✅ Squeeze Firing", "✅ ML Conviction High" — but it only shows the active ones with no sense of total coverage.
2. **Confluence Heatmap**: A bar chart of score breakdown categories (Trend, Momentum, Volatility, Volume, HTF) — great for score magnitude, but doesn't tell the operator "how many independent signals are actually confirming this trade."
3. **Risk Gate**: A safety checklist (TF Alignment, ML, Streak, DD, R:R) — but this checks risk, not directional confluence.

**The operator needs ONE unified answer:** *"Out of the 10 things I track, how many support THIS direction right now?"*

This phase adds a **Confluence Alignment Radar** to the Verdict card — a compact, visually rich component that:
- Lists **every trackable confluence variable** (10 total).
- Shows which are **active/aligned** vs **inactive/against** the proposed direction.
- Displays a bold summary: `7 / 10 ALIGNED` with a color-coded progress bar.
- Updates via WebSocket when new data arrives.

---

## 📐 Architecture Reference

### Available Signal Codes (from `engine.py`)

The engine emits `reason_codes` in each alert's `decision_trace.codes`. Here are ALL possible codes that indicate directional confluence:

**Bullish Signals:**
| Code | Meaning | Data Source |
|:--|:--|:--|
| `SQUEEZE_FIRE` | Bollinger squeeze just fired | `intel.squeeze` |
| `SENTIMENT_BULL` | Composite sentiment > 0.3 | `intel.sentiment` |
| `NEAR_POC` | Price near Volume Profile POC | `intel.volume_profile` |
| `BID_WALL_SUPPORT` | Large bid wall detected | `intel.liquidity` |
| `DXY_FALLING_BULLISH` | Dollar weakening (BTC bullish) | `intel.macro_correlation` |
| `GOLD_RISING_BULLISH` | Gold rising (BTC bullish) | `intel.macro_correlation` |
| `FG_EXTREME_FEAR` / `FG_FEAR` | Fear & Greed contrarian buy | `fg` |
| `ML_CONFIDENCE_BOOST` | ML model > 70% win prob | `ml_predictor` |
| `HTF_ALIGNED` | Higher timeframe agrees | `_trend_bias` |
| `FUNDING_EXTREME_LOW` / `FUNDING_LOW` | Funding rate favors longs | `derivatives` |
| `OI_SURGE_MAJOR` / `OI_SURGE_MINOR` | Open interest surging | `derivatives` |
| `BASIS_BULLISH` | Futures premium positive | `derivatives` |

**Bearish Signals:**
| Code | Meaning |
|:--|:--|
| `SENTIMENT_BEAR` | Composite sentiment < -0.3 |
| `ASK_WALL_RESISTANCE` | Large ask wall detected |
| `DXY_RISING_BEARISH` | Dollar strengthening |
| `GOLD_FALLING_BEARISH` | Gold falling |
| `FG_EXTREME_GREED` / `FG_GREED` | Greed = contrarian sell |
| `ML_SKEPTICISM` | ML model < 40% win prob |
| `HTF_COUNTER` | Against higher timeframe |
| `FUNDING_EXTREME_HIGH` / `FUNDING_HIGH` | Funding rate favors shorts |
| `BASIS_BEARISH` | Futures discount negative |

### Existing data in `build_context()` return dict:
```python
{
    "verdict": {
        "direction": "LONG",         # Current proposed direction
        "reason_codes": [...],       # List of active signal codes
        "squeeze": "SQUEEZE_FIRE",   # Current squeeze state
        "fear_greed": {"value": 25}, # Current F&G reading
        "funding_rate": 0.0012,      # Current funding rate
        "dxy_trend": "falling",      # DXY direction
        "gold_trend": "rising",      # Gold direction
        "sentiment_score": 0.4,      # Composite sentiment
        "liquidity": {"bid_walls": 3, "ask_walls": 1},
        "volume_profile": {"poc": 64200, "near_poc": True},
        "ml_prob": 0.94,             # ML probability
        "confluence_strength": "STRONG",
    },
    "tf_bias": {"5m": {...}, "15m": {...}, "1h": {...}},
    "confluence_layers": {"trend": 6.0, "momentum": 4.0, ...},
}
```

### How to determine "aligned with direction"

For a `LONG` trade:
- A **bullish** signal is **aligned** ✅
- A **bearish** signal is **against** ❌
- Absence of a signal is **inactive** ⚪

For a `SHORT` trade:
- A **bearish** signal is **aligned** ✅
- A **bullish** signal is **against** ❌

---

## 📋 EXECUTION STEPS

---

### STEP 1: Build the Confluence Alignment Data in `build_context()`
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** Compute a list of 10 confluence "probes" — each representing one trackable signal — and determine whether it's aligned, against, or inactive relative to the proposed direction.

**Action 1:** In the `build_context()` function, find the `# Risk Gate checks` comment (around line 261). Add the following code BEFORE that line (after the `regime` fallback block, before Risk Gate):

```python
    # ──────────────────────────────────────────────
    # CONFLUENCE ALIGNMENT RADAR (Phase 11)
    # ──────────────────────────────────────────────
    direction = verdict["direction"]
    active_codes = set(verdict["reason_codes"])

    # Define 10 confluence probes
    # Each probe: (id, label, bullish_codes, bearish_codes)
    # If a bullish code fires → aligned with LONG, against SHORT (and vice versa)
    confluence_probes = [
        ("squeeze",   "Squeeze",     ["SQUEEZE_FIRE"],                     []),
        ("trend",     "Trend (HTF)", ["HTF_ALIGNED"],                      ["HTF_COUNTER"]),
        ("momentum",  "Momentum",    ["SENTIMENT_BULL"],                   ["SENTIMENT_BEAR"]),
        ("ml",        "ML Model",    ["ML_CONFIDENCE_BOOST"],              ["ML_SKEPTICISM"]),
        ("funding",   "Funding",     ["FUNDING_EXTREME_LOW", "FUNDING_LOW"], ["FUNDING_EXTREME_HIGH", "FUNDING_HIGH"]),
        ("macro_dxy", "DXY Macro",   ["DXY_FALLING_BULLISH"],              ["DXY_RISING_BEARISH"]),
        ("macro_gold","Gold Macro",  ["GOLD_RISING_BULLISH"],              ["GOLD_FALLING_BEARISH"]),
        ("fear_greed","Fear & Greed",["FG_EXTREME_FEAR", "FG_FEAR"],       ["FG_EXTREME_GREED", "FG_GREED"]),
        ("orderbook", "Order Book",  ["BID_WALL_SUPPORT"],                 ["ASK_WALL_RESISTANCE"]),
        ("deriv",     "OI / Basis",  ["OI_SURGE_MAJOR", "OI_SURGE_MINOR", "BASIS_BULLISH"], ["BASIS_BEARISH"]),
    ]

    alignment_results = []
    for probe_id, label, bull_codes, bear_codes in confluence_probes:
        has_bull = any(c in active_codes for c in bull_codes)
        has_bear = any(c in active_codes for c in bear_codes)

        if direction == "LONG":
            if has_bull:
                status = "aligned"
            elif has_bear:
                status = "against"
            else:
                status = "inactive"
        elif direction == "SHORT":
            if has_bear:
                status = "aligned"
            elif has_bull:
                status = "against"
            else:
                status = "inactive"
        else:
            status = "inactive"

        alignment_results.append({"id": probe_id, "label": label, "status": status})

    aligned_count = sum(1 for r in alignment_results if r["status"] == "aligned")
    against_count = sum(1 for r in alignment_results if r["status"] == "against")
    total_probes = len(alignment_results)
```

**Action 2:** Add these new keys to the `return` dict (inside the `return {` block, after the `"gate_verdict"` line):

```python
        "alignment_results": alignment_results,
        "aligned_count": aligned_count,
        "against_count": against_count,
        "total_probes": total_probes,
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` — no errors.

---

### STEP 2: Pre-render the Alignment Radar HTML in `generate_html()`
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** In the `generate_html()` function, build the HTML string for the Confluence Alignment Radar panel. This will be a compact component showing a header with the score, a horizontal progress bar, and a 2-column grid of the 10 probes.

**Action 1:** In `generate_html()`, find the line `gate_html += '</div>'` (the end of the Risk Gate HTML block, around line 376). Add the following code AFTER that line:

```python
    # ──────────────────────────────────────────────
    # CONFLUENCE ALIGNMENT RADAR HTML (Phase 11)
    # ──────────────────────────────────────────────
    a_count = ctx["aligned_count"]
    ag_count = ctx["against_count"]
    t_probes = ctx["total_probes"]
    
    # Color based on alignment ratio
    if a_count >= 7:
        radar_color = "var(--accent)"         # green — strong alignment
        radar_bg = "rgba(0,255,204,0.06)"
        radar_label = "STRONG"
    elif a_count >= 4:
        radar_color = "var(--warning)"        # amber — moderate
        radar_bg = "rgba(255,170,0,0.06)"
        radar_label = "MODERATE"
    else:
        radar_color = "var(--danger)"         # red — weak/conflicting
        radar_bg = "rgba(255,77,109,0.06)"
        radar_label = "WEAK"
    
    bar_pct = int((a_count / t_probes) * 100) if t_probes > 0 else 0
    
    radar_html = f'''
    <div style="background: {radar_bg}; border: 1px solid {radar_color}; border-radius: 12px; padding: 1rem; margin-bottom: 1.5rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
            <span style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 2px; color: var(--text-secondary);">Confluence Radar</span>
            <span style="font-weight: 900; color: {radar_color}; font-size: 0.85rem; font-family: var(--font-mono);">{a_count} / {t_probes} {radar_label}</span>
        </div>
        <div style="height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; margin-bottom: 1rem; overflow: hidden;">
            <div style="height: 100%; width: {bar_pct}%; background: {radar_color}; border-radius: 3px; transition: width 0.5s ease;"></div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 16px;">'''
    
    for probe in ctx["alignment_results"]:
        if probe["status"] == "aligned":
            icon = "🟢"
            p_color = "var(--accent)"
        elif probe["status"] == "against":
            icon = "🔴"
            p_color = "var(--danger)"
        else:
            icon = "⚫"
            p_color = "var(--text-secondary)"
        
        radar_html += f'''
            <div style="display: flex; align-items: center; gap: 6px; font-size: 0.72rem; padding: 3px 0;">
                <span style="font-size: 0.6rem;">{icon}</span>
                <span style="color: {p_color};">{probe["label"]}</span>
            </div>'''
    
    radar_html += '''
        </div>
    </div>'''
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` — no errors.

---

### STEP 3: Insert the Radar into the Verdict Card HTML
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** Place the `{radar_html}` inside the Verdict card, between the Conviction Signals section and the Risk Gate section. This creates a visual funnel:
  1. Conviction Signals (what's firing)
  2. **Confluence Radar** (how many agree — NEW)
  3. Risk Gate (safety checks)
  4. Execute button

**Action:** In the HTML body, find the line that contains `{gate_html}` (around line 882). Add `{radar_html}` on the line DIRECTLY BEFORE `{gate_html}`, like this:

```python
                {radar_html}

                {gate_html}
```

So the final sequence in the Verdict card should be:
```
{signals_html}
</div>
</div>

{radar_html}

{gate_html}

<button ...>1-CLICK EXECUTE</button>
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` — no errors. Open `dashboard.html` locally in a browser. Confirm the Confluence Radar appears between the signals and the safety gate.

---

### STEP 4: Add the Confluence Summary to the Heatmap Section  
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** Enhance the existing Confluence Heatmap card in Zone C (Intelligence Layers, side panel) by adding a small summary header that shows the aligned vs against count. This gives a second glance at confluence when the operator is reviewing the heatmap bars.

**Action:** Find the Confluence Heatmap card HTML in the `generate_html()` function. Look for this block (around line 889-892):

```python
                <div class="glass-card" style="grid-column: span 2;">
                    <div class="metric-label" style="text-align: left; margin-bottom: 1rem;">Confluence Heatmap</div>
                    {heatmap_html}
                </div>
```

Replace it with:

```python
                <div class="glass-card" style="grid-column: span 2;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                        <div class="metric-label" style="margin-bottom: 0;">Confluence Heatmap</div>
                        <div style="font-size: 0.75rem; font-family: var(--font-mono);">
                            <span style="color: var(--accent);">🟢 {ctx["aligned_count"]}</span>
                            <span style="margin: 0 4px; color: var(--text-secondary);">·</span>
                            <span style="color: var(--danger);">🔴 {ctx["against_count"]}</span>
                            <span style="margin: 0 4px; color: var(--text-secondary);">·</span>
                            <span style="color: var(--text-secondary);">⚫ {ctx["total_probes"] - ctx["aligned_count"] - ctx["against_count"]}</span>
                        </div>
                    </div>
                    {heatmap_html}
                    <div style="margin-top: 0.8rem; padding-top: 0.8rem; border-top: 1px solid var(--border); font-size: 0.7rem; color: var(--text-secondary); text-align: center;">
                        Net Score: <span style="font-weight: 900; color: {"var(--accent)" if net_score >= 0 else "var(--danger)"}; font-family: var(--font-mono);">{net_score:+.1f}</span>
                    </div>
                </div>
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` — no errors. Open dashboard, confirm the heatmap header now shows the green/red/grey counts and a net score at the bottom.

---

### STEP 5: Make the Radar Update via WebSocket (Real-Time)
- [x] **DONE**

**File:** `scripts/pid-129/generate_dashboard.py`

**What:** The Confluence Radar is currently static (rendered once at page load by Python). To make it update when new alerts arrive via WebSocket, add alignment data to the JavaScript state and update the radar DOM when new alert data comes in.

**Action 1:** Add alignment data to the JS `state` object initialization. Find the `let state = {{` block inside `generate_html()` and add these properties:

```javascript
        alignedCount: {ctx["aligned_count"]},
        againstCount: {ctx["against_count"]},
        totalProbes: {ctx["total_probes"]},
```

**Action 2:** Add an `id` attribute to the radar score label so we can update it. In the radar HTML you built in Step 2, the score line is:

```python
            <span style="font-weight: 900; color: {radar_color}; font-size: 0.85rem; font-family: var(--font-mono);">{a_count} / {t_probes} {radar_label}</span>
```

Change it to include an `id`:

```python
            <span id="radarScore" style="font-weight: 900; color: {radar_color}; font-size: 0.85rem; font-family: var(--font-mono);">{a_count} / {t_probes} {radar_label}</span>
```

Also add an `id` to the progress bar fill div:

```python
            <div id="radarBar" style="height: 100%; width: {bar_pct}%; background: {radar_color}; border-radius: 3px; transition: width 0.5s ease;"></div>
```

**Action 3:** In the `connectWS()` `ws.onmessage` handler, add logic to update alignment counts when new alert data arrives. Find the block `if (data.stats) {{` and add this AFTER it:

```javascript
            // Update confluence radar from latest alert
            if (data.alerts && data.alerts.length > 0) {{
                const latest = data.alerts[data.alerts.length - 1];
                const codes = (latest.decision_trace && latest.decision_trace.codes) || latest.reason_codes || [];
                const dir = latest.direction || state.direction;
                const codeSet = new Set(codes);
                
                const probes = [
                    [['SQUEEZE_FIRE'], []],
                    [['HTF_ALIGNED'], ['HTF_COUNTER']],
                    [['SENTIMENT_BULL'], ['SENTIMENT_BEAR']],
                    [['ML_CONFIDENCE_BOOST'], ['ML_SKEPTICISM']],
                    [['FUNDING_EXTREME_LOW', 'FUNDING_LOW'], ['FUNDING_EXTREME_HIGH', 'FUNDING_HIGH']],
                    [['DXY_FALLING_BULLISH'], ['DXY_RISING_BEARISH']],
                    [['GOLD_RISING_BULLISH'], ['GOLD_FALLING_BEARISH']],
                    [['FG_EXTREME_FEAR', 'FG_FEAR'], ['FG_EXTREME_GREED', 'FG_GREED']],
                    [['BID_WALL_SUPPORT'], ['ASK_WALL_RESISTANCE']],
                    [['OI_SURGE_MAJOR', 'OI_SURGE_MINOR', 'BASIS_BULLISH'], ['BASIS_BEARISH']]
                ];
                
                let aligned = 0;
                probes.forEach(([bull, bear]) => {{
                    const hasBull = bull.some(c => codeSet.has(c));
                    const hasBear = bear.some(c => codeSet.has(c));
                    if (dir === 'LONG' && hasBull) aligned++;
                    else if (dir === 'SHORT' && hasBear) aligned++;
                }});
                
                state.alignedCount = aligned;
                const total = probes.length;
                const pct = Math.round((aligned / total) * 100);
                const label = aligned >= 7 ? 'STRONG' : aligned >= 4 ? 'MODERATE' : 'WEAK';
                const color = aligned >= 7 ? 'var(--accent)' : aligned >= 4 ? 'var(--warning)' : 'var(--danger)';
                
                const scoreEl = document.getElementById('radarScore');
                if (scoreEl) {{
                    scoreEl.innerText = aligned + ' / ' + total + ' ' + label;
                    scoreEl.style.color = color;
                }}
                const barEl = document.getElementById('radarBar');
                if (barEl) {{
                    barEl.style.width = pct + '%';
                    barEl.style.background = color;
                }}
            }}
```

**Verify:** `python scripts/pid-129/generate_dashboard.py` — no errors.

---

### STEP 6: Final Integration Test
- [x] **DONE**

**Run these commands in order:**

```
python scripts/pid-129/generate_dashboard.py
python -m pytest tests/ -k "not test_genetic_optimization" -x -q
```

**Manual browser check (open `http://localhost:8000` with the server running):**
- [x] Confluence Radar appears between Conviction Signals and Risk Gate
- [x] Radar shows `X / 10 STRONG|MODERATE|WEAK` with color coding
- [x] Progress bar fills proportionally to aligned count
- [x] Each of the 10 probes shows 🟢 (aligned), 🔴 (against), or ⚫ (inactive)
- [x] Confluence Heatmap header shows green/red/grey counts
- [x] Heatmap footer shows net score
- [x] Live price ticker still works (no regression)
- [x] Risk Gate still works (no regression)
- [x] Equity curve still renders (no regression)
- [x] No JavaScript console errors

---

## 🚫 Out of Scope (Do NOT Implement)

- No new Python files — all changes are in `generate_dashboard.py`
- No new API endpoints — use existing WebSocket payload
- No external JS libraries beyond Chart.js (already loaded)
- No database or persistent storage changes
- No changes to `engine.py` or `intelligence/confluence.py`
- No TradingView custom indicators
- No alerts/notifications/sound
- No mobile-specific layout changes

---

## 📁 Files Modified

| File | Change |
|:--|:--|
| `scripts/pid-129/generate_dashboard.py` | Confluence Alignment Radar: data computation, HTML rendering, Verdict card integration, Heatmap enhancement, WebSocket real-time updates |
| `dashboard.html` | Auto-generated output (never edit directly) |

---

## ✅ COMPLETION CRITERIA

All 6 checkboxes above must be `[x]`. Then:
1. Run `python scripts/pid-129/generate_dashboard.py` one final time
2. Start the server: `python scripts/pid-129/dashboard_server.py`
3. Open `http://localhost:8000` in browser
4. Confirm all 10 manual checks pass
5. Take a screenshot for operator review
6. **DO NOT COMMIT** — wait for operator approval

---
*Phase 11 — Confluence Alignment Radar | Created: 2026-02-24*
