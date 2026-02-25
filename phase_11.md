# Phase 11 (REVISED): Confluence Alignment Radar — Fix & Complete

> **AGENT INSTRUCTIONS:** You are editing ONE file only. Read every step fully before touching anything. Each step gives you the EXACT text to find and the EXACT text to replace it with. After every step run the verification command. If it fails, fix it before proceeding. Do NOT proceed to the next step until the current step's verification passes.

---

## ⚠️ MANDATORY RULES — READ FIRST

1. **Target file:** `scripts/pid-129/generate_dashboard.py` — 656 lines. Do NOT touch any other file.
2. **f-string escaping:** The entire HTML is built inside Python f-strings (`f""" ... """`). This means:
   - Every JavaScript `{` must be written as `{{`
   - Every JavaScript `}` must be written as `}}`
   - JavaScript template literals like `${var}` are **BANNED** — use string concatenation instead: `'$' + var`
   - Python variables like `{a_count}` inside the f-string are fine — they are **not** doubled
3. **Verification command after EVERY step:**
   ```
   python scripts/pid-129/generate_dashboard.py
   ```
   It must print: `Dashboard generated:` followed by a path. Any Python error = you broke something. Fix it.
4. **Do NOT add new imports.** Do NOT create new files. Do NOT modify any file except `generate_dashboard.py`.
5. **Do NOT renumber or reformat code** you are not instructed to change.

---

## 📊 CURRENT STATE — What Already Works

Before starting, confirm by running:
```
python scripts/pid-129/generate_dashboard.py
```

The following features **already exist and work**:
- ✅ Confluence Radar is rendered in the Verdict card (10 probes with 🟢/🔴/⚫ icons)
- ✅ Progress bar fills proportionally to aligned count
- ✅ Live Tape header shows radar score (the `id="live-radar"` tile)
- ✅ Trade Safety gate (Risk Gate) renders correctly
- ✅ Live price, PnL, TP1/STOP distances update via WebSocket

**What is BROKEN or MISSING:**
- ❌ Dead duplicate function `build_verdict_context` at lines 117–170 (never called, causes confusion)
- ❌ `against_count` is not tracked in the active function (only aligned is counted)
- ❌ The radar HTML elements have no DOM `id` attributes — the WebSocket cannot update them
- ❌ The WebSocket radar update is **hardcoded** (baked-in Python values, never changes on new alerts)
- ❌ No net score display (aligned − against)

---

## 📋 STEPS

---

### STEP 1: Delete the dead duplicate function (lines 117–170)

**Why:** There are two functions named `build_verdict_context`. Python uses the second one (line 408). The first one (line 117) is dead code that will never run. Delete it.

**FIND this exact text** (starts at line 117, ends at line 170):

```python
def build_verdict_context(alerts, portfolio):
    latest = latest_btc_by_timeframe(alerts)
    decision, tone, reasons = execution_decision(latest)
    a5 = latest.get("5m", {})
    ctx = get_context(a5)
    verdict = {
        "alert_id": str(a5.get("id") or a5.get("alert_id") or "latest-btc"),
        "direction": get_direction(a5 if a5 else {"direction": "WAIT"}) if decision == "EXECUTE" else "WAIT",
        "entry": float(a5.get("entry_price") or a5.get("entry") or 0.0),
        "tp1": float(a5.get("tp1") or 0.0),
        "invalidation": float(a5.get("invalidation") or 0.0),
        "rr_ratio": float(a5.get("rr_ratio") or 0.0),
        "ml_prob": float(a5.get("ml_prob") or a5.get("ml_probability") or get_confidence(a5) / 100.0),
        "reason_codes": (a5.get("decision_trace") or {}).get("codes", []) if isinstance(a5, dict) else [],
    }
    tf_bias = {tf: {"direction": get_direction(a)} for tf, a in latest.items()}
    directions = [v["direction"] for v in tf_bias.values() if v["direction"] != "NEUTRAL"]
    tf_aligned = len(set(directions)) == 1 and len(directions) >= 2
    stats = {"streak": 0, "max_dd": 0.0}
    if isinstance(portfolio, dict):
        stats["streak"] = -max_losing_streak(portfolio.get("closed_trades", []))
        stats["max_dd"] = float(portfolio.get("max_drawdown") or 0.0) * 100
    gate_checks = {
        "tf_aligned": {"pass": tf_aligned, "label": "Timeframes Aligned", "icon_pass": "✅", "icon_fail": "⚠️"},
        "ml_confident": {"pass": verdict["ml_prob"] * 100 >= 60, "label": "ML Confidence ≥ 60%", "icon_pass": "✅", "icon_fail": "❌"},
        "streak_ok": {"pass": stats["streak"] >= -2, "label": "Streak ≥ -2", "icon_pass": "✅", "icon_fail": "🧊"},
        "dd_ok": {"pass": stats["max_dd"] < 10, "label": "Drawdown < 10%", "icon_pass": "✅", "icon_fail": "🔴"},
        "rr_ok": {"pass": verdict["rr_ratio"] >= 1.5, "label": "R:R ≥ 1.5x", "icon_pass": "✅", "icon_fail": "⚠️"},
    }
    gate_pass_count = sum(1 for g in gate_checks.values() if g["pass"])
    gate_verdict = "GREEN" if gate_pass_count >= 4 else ("AMBER" if gate_pass_count >= 3 else "RED")
    active_codes = set(verdict["reason_codes"])
    probes = [
        ("squeeze", "Squeeze", ["SQUEEZE_FIRE"], []), ("trend", "Trend (HTF)", ["HTF_ALIGNED"], ["HTF_COUNTER"]),
        ("momentum", "Momentum", ["SENTIMENT_BULL"], ["SENTIMENT_BEAR"]), ("ml", "ML Model", ["ML_CONFIDENCE_BOOST"], ["ML_SKEPTICISM"]),
        ("funding", "Funding", ["FUNDING_EXTREME_LOW", "FUNDING_LOW"], ["FUNDING_EXTREME_HIGH", "FUNDING_HIGH"]),
        ("macro_dxy", "DXY Macro", ["DXY_FALLING_BULLISH"], ["DXY_RISING_BEARISH"]), ("macro_gold", "Gold Macro", ["GOLD_RISING_BULLISH"], ["GOLD_FALLING_BEARISH"]),
        ("fear_greed", "Fear & Greed", ["FG_EXTREME_FEAR", "FG_FEAR"], ["FG_EXTREME_GREED", "FG_GREED"]),
        ("orderbook", "Order Book", ["BID_WALL_SUPPORT"], ["ASK_WALL_RESISTANCE"]), ("deriv", "OI / Basis", ["OI_SURGE_MAJOR", "OI_SURGE_MINOR", "BASIS_BULLISH"], ["BASIS_BEARISH"]),
    ]
    alignment_results = []
    for probe_id, label, bulls, bears in probes:
        has_bull, has_bear = any(c in active_codes for c in bulls), any(c in active_codes for c in bears)
        if verdict["direction"] == "LONG":
            status = "aligned" if has_bull else ("against" if has_bear else "inactive")
        elif verdict["direction"] == "SHORT":
            status = "aligned" if has_bear else ("against" if has_bull else "inactive")
        else:
            status = "inactive"
        alignment_results.append({"id": probe_id, "label": label, "status": status})
    return {"decision": decision, "tone": tone, "reasons": reasons, "verdict": verdict, "tf_bias": tf_bias, "gate_checks": gate_checks,
            "gate_pass_count": gate_pass_count, "gate_total": len(gate_checks), "gate_verdict": gate_verdict, "alignment_results": alignment_results,
            "aligned_count": sum(1 for r in alignment_results if r["status"] == "aligned"), "against_count": sum(1 for r in alignment_results if r["status"] == "against"),
            "total_probes": len(alignment_results), "confluence_layers": ctx.get("score_breakdown") if isinstance(ctx.get("score_breakdown"), dict) else {}}
```

**REPLACE WITH** (nothing — delete the entire block above):

```python
```

> ⚠️ After deletion, the file should have only ONE function named `build_verdict_context`. It should be the one that starts with `def build_verdict_context(alerts, portfolio):` followed by `    alert = _latest_btc_alert(alerts)`.

**VERIFY:** `python scripts/pid-129/generate_dashboard.py` — must print `Dashboard generated:` with no errors.

---

### STEP 2: Add `against_count` to the active function's return dict

**Context:** The active `build_verdict_context` function (the only one remaining after Step 1) ends with these 2 lines:

**FIND this exact text:**
```python
    aligned_count = sum(1 for _, icon, _ in rows if icon == "🟢")
    return {"direction": direction, "entry": entry, "tp1": tp1, "stop": stop, "checks": checks, "gate": gate, "rows": rows, "aligned": aligned_count, "total": len(rows)}
```

**REPLACE WITH:**
```python
    aligned_count = sum(1 for _, icon, _ in rows if icon == "🟢")
    against_count = sum(1 for _, icon, _ in rows if icon == "🔴")
    return {"direction": direction, "entry": entry, "tp1": tp1, "stop": stop, "checks": checks, "gate": gate, "rows": rows, "aligned": aligned_count, "against": against_count, "total": len(rows)}
```

**VERIFY:** `python scripts/pid-129/generate_dashboard.py` — must print `Dashboard generated:` with no errors.

---

### STEP 3: Add helper variables in `generate_html()`

**Context:** In `generate_html()`, after `vctx` is built, the radar variables are extracted on one line. We need to split them and add `ag_count`, `net_score`, and `net_color` as separate variables.

**FIND this exact text:**
```python
    a_count, t_probes = vctx["aligned"], vctx["total"]
    radar_color = "var(--accent)" if a_count >= 7 else ("#ffd700" if a_count >= 4 else "#ff4d4d")
    radar_label = "STRONG" if a_count >= 7 else ("MODERATE" if a_count >= 4 else "WEAK")
```

**REPLACE WITH:**
```python
    a_count = vctx["aligned"]
    ag_count = vctx.get("against", 0)
    t_probes = vctx["total"]
    net_score = a_count - ag_count
    radar_color = "var(--accent)" if a_count >= 7 else ("#ffd700" if a_count >= 4 else "#ff4d4d")
    radar_label = "STRONG" if a_count >= 7 else ("MODERATE" if a_count >= 4 else "WEAK")
    net_color = "var(--accent)" if net_score >= 0 else "#ff4d4d"
    inactive_count = t_probes - a_count - ag_count
```

**VERIFY:** `python scripts/pid-129/generate_dashboard.py` — must print `Dashboard generated:` with no errors.

---

### STEP 4: Add DOM `id` attributes and net score strip to the radar HTML

**Why:** Without `id` attributes on the radar elements, JavaScript cannot find and update them. The net score strip (`Net: +3 · 🟢7 · 🔴4 · ⚫...`) gives the operator instant at-a-glance intelligence.

**FIND this exact text** (it is inside the `verdict_html = f"""` block):
```python
      <div style='background:rgba(255,255,255,.03);border:1px solid {radar_color};border-radius:12px;padding:1rem;margin-bottom:1rem;'>
        <div style='display:flex;justify-content:space-between;'><span class='mini'>Confluence Radar</span><span class='pill' style='border:1px solid {radar_color};color:{radar_color};'>{a_count}/{t_probes} {radar_label}</span></div>
        <div style='height:6px;background:rgba(255,255,255,.08);border-radius:4px;margin:.5rem 0 .8rem;'><div style='height:100%;width:{int((a_count/t_probes)*100) if t_probes else 0}%;background:{radar_color};'></div></div>
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;'>{radar_rows}</div>
      </div>
```

**REPLACE WITH:**
```python
      <div id='radarCard' style='background:rgba(255,255,255,.03);border:1px solid {radar_color};border-radius:12px;padding:1rem;margin-bottom:1rem;'>
        <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:.3rem;'><span class='mini'>Confluence Radar</span><span id='radarScore' class='pill' style='border:1px solid {radar_color};color:{radar_color};'>{a_count}/{t_probes} {radar_label}</span></div>
        <div style='height:6px;background:rgba(255,255,255,.08);border-radius:4px;margin:.5rem 0 .8rem;overflow:hidden;'><div id='radarBar' style='height:100%;width:{int((a_count/t_probes)*100) if t_probes else 0}%;background:{radar_color};transition:width 0.4s ease;'></div></div>
        <div id='radarGrid' style='display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;'>{radar_rows}</div>
        <div style='margin-top:.5rem;border-top:1px solid rgba(255,255,255,.06);padding-top:.4rem;font-size:.7rem;font-family:JetBrains Mono,monospace;color:var(--text-muted);'>Net: <span id='radarNet' style='color:{net_color};font-weight:700;'>{net_score:+d}</span> &nbsp;🟢 {a_count} &nbsp;🔴 {ag_count} &nbsp;⚫ {inactive_count}</div>
      </div>
```

> ⚠️ WARNING: This block is inside an f-string. The `id='radarScore'` etc. are plain HTML attributes — they do NOT need `{{}}` escaping. Only JavaScript braces need `{{}}`. Do not double any braces in this HTML snippet.

**VERIFY:** `python scripts/pid-129/generate_dashboard.py` — must print `Dashboard generated:`. Then open `dashboard.html` in a browser and confirm:
- The radar card shows DOM IDs (inspect element: `id="radarScore"`, `id="radarBar"`, `id="radarGrid"`, `id="radarNet"`)
- A "Net: +N" line appears at the bottom of the radar card

---

### STEP 5: Fix the WebSocket handler to dynamically update the radar

**Why this matters:** The current WS handler contains this hardcoded line:
```
els.radar.textContent='{a_count}/{t_probes} {radar_label}';
```
Those Python f-string values (`{a_count}`, etc.) are **baked in at page render time** and never change. This means the radar NEVER updates live — it just re-sets the same stale value on every WebSocket tick. This step replaces that one hardcoded line with a dynamic block that re-computes the full radar from the latest alert codes.

**FIND this exact text** (it is one unique substring inside the very long `connectWS` line):
```
els.radar.textContent='{a_count}/{t_probes} {radar_label}';
```

> ⚠️ NOTE: In the Python source file, the literal text is exactly `els.radar.textContent='{a_count}/{t_probes} {radar_label}';` — those are Python variable names that get substituted when Python renders. You are searching for this string IN the Python source file, not in the generated HTML.

**REPLACE WITH** (all on one line — do NOT add newlines inside this block, it must stay as a single statement sequence):
```
const wsLatest=(data.alerts||[]).slice(-1)[0]||{{}};const wsDir=String(wsLatest.direction||state.direction).toUpperCase();const wsCS=new Set(((wsLatest.decision_trace||{{}}).codes)||[]);const wsPD=[[['SQUEEZE_FIRE'],[],'Squeeze'],[['HTF_ALIGNED'],['HTF_COUNTER'],'Trend (HTF)'],[['SENTIMENT_BULL'],['SENTIMENT_BEAR'],'Momentum'],[['ML_CONFIDENCE_BOOST'],['ML_SKEPTICISM'],'ML Model'],[['FUNDING_EXTREME_LOW','FUNDING_LOW'],['FUNDING_EXTREME_HIGH','FUNDING_HIGH'],'Funding'],[['DXY_FALLING_BULLISH'],['DXY_RISING_BEARISH'],'DXY Macro'],[['GOLD_RISING_BULLISH'],['GOLD_FALLING_BEARISH'],'Gold Macro'],[['FG_EXTREME_FEAR','FG_FEAR'],['FG_EXTREME_GREED','FG_GREED'],'Fear & Greed'],[['BID_WALL_SUPPORT'],['ASK_WALL_RESISTANCE'],'Order Book'],[['OI_SURGE_MAJOR','OI_SURGE_MINOR','BASIS_BULLISH'],['BASIS_BEARISH'],'OI / Basis']];let wsAl=0,wsAg=0;const wsRH=wsPD.map(([b,br,lbl])=>{{const hb=b.some(c=>wsCS.has(c));const hbr=br.some(c=>wsCS.has(c));let ic='⚫',co='var(--text-muted)';if((wsDir==='LONG'&&hb)||(wsDir==='SHORT'&&hbr)){{ic='🟢';co='var(--accent)';wsAl++;}}else if((wsDir==='LONG'&&hbr)||(wsDir==='SHORT'&&hb)){{ic='🔴';co='#ff4d4d';wsAg++;}}return "<div class='mini'>"+ic+" <span style='color:"+co+"'>"+lbl+"</span></div>";}}).join('');const wsT=wsPD.length,wsPct=Math.round((wsAl/wsT)*100),wsLbl=wsAl>=7?'STRONG':wsAl>=4?'MODERATE':'WEAK',wsClr=wsAl>=7?'var(--accent)':wsAl>=4?'#ffd700':'#ff4d4d',wsNet=wsAl-wsAg;const rSc=document.getElementById('radarScore');if(rSc){{rSc.textContent=wsAl+'/'+wsT+' '+wsLbl;rSc.style.color=wsClr;rSc.style.borderColor=wsClr;}};const rBr=document.getElementById('radarBar');if(rBr){{rBr.style.width=wsPct+'%';rBr.style.background=wsClr;}};const rGr=document.getElementById('radarGrid');if(rGr)rGr.innerHTML=wsRH;const rNt=document.getElementById('radarNet');if(rNt){{rNt.textContent=(wsNet>=0?'+':'')+wsNet;rNt.style.color=wsNet>=0?'var(--accent)':'#ff4d4d';}};els.radar.textContent=wsAl+'/'+wsT+' '+wsLbl;
```

> ⚠️ ESCAPING CHECK: Every `{` and `}` in the JavaScript code above is doubled (`{{` / `}}`). The JavaScript array literals use `[[` and `]]` which are fine (they are not brace-escaped). Do NOT change any of these.

**VERIFY:** `python scripts/pid-129/generate_dashboard.py` — must print `Dashboard generated:` with no Python errors.

---

### STEP 6: Final Integration Test

**Run these two commands in order:**

```
python scripts/pid-129/generate_dashboard.py
python -m pytest tests/ -k "not test_genetic_optimization" -x -q
```

Both must succeed with no errors.

**Then start the dashboard server and check in browser:**
```
python scripts/pid-129/dashboard_server.py
```
Open `http://localhost:8000` and confirm ALL of the following:

- [x] Confluence Radar card appears between "Conviction Signals" and "Trade Safety"
- [x] Radar shows `X/10 STRONG|MODERATE|WEAK` with badge styled in green/amber/red
- [x] Progress bar fills proportionally (width = aligned/10 × 100%)
- [x] All 10 probe rows show 🟢, 🔴, or ⚫ with correct labels
- [x] Net score strip at bottom of radar shows `Net: +N` or `Net: -N`
- [x] The number breakdown shows `🟢 N 🔴 N ⚫ N`
- [x] Live Tape "Radar" tile updates when new WS data arrives
- [x] Radar card (score badge, bar, probe rows, net score) updates live when new WS data arrives
- [x] Live price ticker still updates (no regression)
- [x] Trade Safety gate still works (no regression)
- [x] No JavaScript console errors (open DevTools → Console → check for red errors)

---

## 🔍 How to Confirm Each DOM ID Exists

After running `python scripts/pid-129/generate_dashboard.py`, open `dashboard.html` in a text editor and search for:
- `id="radarScore"` — should appear once
- `id="radarBar"` — should appear once
- `id="radarGrid"` — should appear once
- `id="radarNet"` — should appear once

If any are missing, re-check Step 4.

---

## 🚫 Do NOT Do These Things

- Do NOT edit `dashboard.html` directly (it is auto-generated and will be overwritten)
- Do NOT add new Python imports
- Do NOT create new files
- Do NOT change anything in `engine.py`, `dashboard_server.py`, or any other file
- Do NOT use JavaScript template literals (`${var}`) anywhere in this file
- Do NOT add newlines into the middle of the `connectWS` line — it is intentionally minified

---

## ✅ Completion Criteria

All 6 steps complete with passing verification. Then:

1. `python scripts/pid-129/generate_dashboard.py` runs clean
2. `python -m pytest tests/ -k "not test_genetic_optimization" -x -q` passes
3. All 10 browser checks above pass
4. **DO NOT COMMIT** — wait for operator approval

---

## 📁 Files Modified

| File | Changes |
|:--|:--|
| `scripts/pid-129/generate_dashboard.py` | Removed dead function (54 lines), added `against_count` to return dict, added 3 helper variables (`ag_count`, `net_score`, `net_color`/`inactive_count`), added 4 DOM IDs + net score strip to radar HTML, replaced hardcoded WS radar value with fully dynamic per-probe update block |
| `dashboard.html` | Auto-generated — never edit directly |

---

*Phase 11 REVISED — Confluence Alignment Radar Fix & Complete | Updated: 2026-02-25*
