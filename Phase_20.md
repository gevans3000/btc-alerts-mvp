# Phase 20: Real Alerts, Probe Diagnostics & Trader Edge

**Status:** ✅ DONE  
**Goal:** Make alerts fire in real market conditions, show WHY each probe is on/off, display recent signal history with accuracy, and give the trader a clear edge score.

---

> [!CAUTION]
> ## ⚠️ PREREQUISITE: Run `/phase19-verify` workflow first
>
> Phase 19 applied all 14 probe fixes. The score multiplier may need tuning.
> **Run `/phase19-verify` before touching anything in this doc.** It takes 5 minutes.

---

## How This Codebase Works (READ BEFORE CODING)

```
collectors/         → Fetches raw data from APIs (price, derivatives, flows, news)
intelligence/       → Each .py produces a dict with "codes" (list) and "pts" (float)
engine.py           → Combines all codes + pts → AlertScore object with .confidence, .tier, .action
config.py           → TIMEFRAME_RULES has thresholds: trade_long, watch_long, trade_short, watch_short
app.py              → Runs engine → calls should_send() → logs to JSONL if not SKIP
logs/pid-129-alerts.jsonl  → One JSON line per alert. Has decision_trace.codes list
generate_dashboard.py      → Reads JSONL → builds static dashboard.html
dashboard_server.py        → Serves HTML + WebSocket pushes live data
```

### Critical path: engine.py `_tier_and_action()` (line 37-64) decides TRADE / WATCH / SKIP
- If `abs(total_score) >= trade_long` → action = "TRADE", tier = "A+"
- If `abs(total_score) >= watch_long` → action = "WATCH", tier = "B"  
- Otherwise → action = "SKIP", tier = "NO-TRADE" → **alert NOT saved to JSONL**
- Thresholds are in `config.py` line 25-29 (`TIMEFRAME_RULES`)

### Current values (verify these haven't changed):
```python
TIMEFRAME_RULES = {
    "5m":  {"trade_long": 45, "watch_long": 25},   # score >= 45 → TRADE, >= 25 → WATCH
    "15m": {"trade_long": 40, "watch_long": 22},
    "1h":  {"trade_long": 35, "watch_long": 20},
}
```

### Score multiplier (engine.py line 291):
```python
SCORE_MULTIPLIER = 3.0   # raw_score * 3.0 = normalized_score
```

---

## ⚡ IMPLEMENTATION ORDER (4 FIXES)

| Priority | Fix | What it does | Files touched |
|----------|-----|-------------|---------------|
| 🔴 P0 | **FIX 1** | Score calibration — make alerts actually fire | `engine.py` |
| 🟡 P1 | **FIX 2** | Probe diagnostic tooltips — show WHY each probe is gray | `generate_dashboard.py` |
| 🟡 P1 | **FIX 3** | Recent signals panel — last 10 alerts with outcomes | `generate_dashboard.py` |
| 🟢 P2 | **FIX 4** | System accuracy badge — win rate proof in Verdict | `generate_dashboard.py` |

**Rule:** After EACH fix, run tests. If tests fail, undo and move to the next fix.

```powershell
pytest tests/ -q --basetemp="c:\Users\lovel\trading\btc-alerts-mvp\tmp_pytest_base"
```
Must show **34+ passed, 0 failures**.

---

## 🔴 FIX 1 — Score Calibration (MUST DO FIRST)

### Why
The engine computes scores but they are too low to cross the TIMEFRAME_RULES thresholds. `action="SKIP"` → no JSONL entry → dashboard shows stale/no data → all other fixes are useless.

### Diagnosis

**Step 1:** Open `engine.py`. Find line 291-292:

```python
    SCORE_MULTIPLIER = 3.0
    total_score = total_score * SCORE_MULTIPLIER
```

**Step 2:** Add a debug print IMMEDIATELY after line 292. The new line 293 should be:

```python
    print(f"SCORE_DEBUG | {symbol} {timeframe} | raw={total_score/SCORE_MULTIPLIER:.1f} x{SCORE_MULTIPLIER}={total_score:.1f} | breakdown={dict((k,round(v,1)) for k,v in breakdown.items() if v != 0)}")
```

**Step 3:** Clear stale state and run:

```powershell
python -c "open('.mvp_alert_state.json', 'w').write('{}')"
python app.py --once
```

**Step 4:** Look at the SCORE_DEBUG output. You will see something like:

```
SCORE_DEBUG | BTC 5m | raw=8.2 x3.0=24.6 | breakdown={momentum: 5.0, ...}
SCORE_DEBUG | BTC 15m | raw=12.1 x3.0=36.3 | breakdown={...}
SCORE_DEBUG | BTC 1h | raw=14.0 x3.0=42.0 | breakdown={...}
```

### Calibration Decision

Read the normalized scores (after the `=` sign) and compare to `TIMEFRAME_RULES`:

| If 5m normalized score is... | Then set SCORE_MULTIPLIER to... |
|------------------------------|-------------------------------|
| 10-20 range (need 25 for WATCH) | **5.0** |
| 5-12 range | **7.0** |
| 20-30 range (close but not hitting 45 for TRADE) | **4.0** |
| 30+ but still SKIP | Don't change multiplier. Lower `config.py` thresholds instead (see below) |

### Apply the fix

**File:** `engine.py`, line 291. Change the number:

```python
    SCORE_MULTIPLIER = 5.0  # Phase 20: calibrated for live market (was 3.0)
```

### If multiplier alone isn't enough

**File:** `config.py`, lines 26-28. Lower thresholds:

```python
TIMEFRAME_RULES = {
    "5m":  {"min_rr": 1.35, "trade_long": 35, "trade_short": 18, "watch_long": 15, "watch_short": 34},
    "15m": {"min_rr": 1.25, "trade_long": 30, "trade_short": 24, "watch_long": 12, "watch_short": 40},
    "1h":  {"min_rr": 1.15, "trade_long": 25, "trade_short": 28, "watch_long": 10, "watch_short": 42},
}
```

> [!WARNING]
> Only lower thresholds if the multiplier alone doesn't work. Try multiplier first.

### Verify

```powershell
python -c "open('.mvp_alert_state.json', 'w').write('{}')"
python app.py --once
```

Then check alerts were saved:

```powershell
python -c "lines=[l for l in open('logs/pid-129-alerts.jsonl').read().splitlines() if l.strip()]; print(f'Alerts: {len(lines)}')"
```

**If `Alerts: 0`** → increase multiplier more or lower thresholds more.  
**If `Alerts: 3+`** → SUCCESS. Remove the debug print line and continue.

### Cleanup

Delete the `print(f"SCORE_DEBUG ...")` line you added. It was only for diagnosis.

---

## 🟡 FIX 2 — Probe Diagnostic Tooltips: See WHY Each Probe is Gray

### Why
The Confluence Radar shows 15 probes as 🟢/🔴/⚫. When a probe is ⚫ (gray), the trader has NO IDEA why. Was the data missing? Was the threshold not met? What value was it at?

A world-class trader needs to see: **"Squeeze: ⚫ OFF — BB width 2.3% > KC width 1.8% (need BB < KC)"**

### What to change

**File:** `scripts/pid-129/generate_dashboard.py`

**Step 1:** Find the `build_verdict_context()` function (starts at line 440).

Inside it, find line 470-475 where probes are processed:

```python
    rows = []
    for label, bulls, bears in probes:
        has_bull, has_bear = any(c in active_codes for c in bulls), any(c in active_codes for c in bears)
        aligned = (direction == "LONG" and has_bull) or (direction == "SHORT" and has_bear)
        against = (direction == "LONG" and has_bear) or (direction == "SHORT" and has_bull)
        rows.append((label, "🟢" if aligned else "🔴" if against else "⚫", "var(--accent)" if aligned else "#ff4d4d" if against else "var(--text-muted)"))
```

**REPLACE** that entire block (lines 470-475) with this:

```python
    rows = []
    # Build diagnostic info from decision_trace context
    dt_context = (alert.get("decision_trace") or {}).get("context", {})
    for label, bulls, bears in probes:
        has_bull, has_bear = any(c in active_codes for c in bulls), any(c in active_codes for c in bears)
        aligned = (direction == "LONG" and has_bull) or (direction == "SHORT" and has_bear)
        against = (direction == "LONG" and has_bear) or (direction == "SHORT" and has_bull)
        icon = "🟢" if aligned else "🔴" if against else "⚫"
        color = "var(--accent)" if aligned else "#ff4d4d" if against else "var(--text-muted)"
        
        # Generate diagnostic tooltip showing WHY the probe is in its current state
        diag = ""
        if icon == "⚫":
            # Show what codes WOULD activate this probe
            all_codes = bulls + bears
            diag = f"Needs: {' or '.join(all_codes[:3])}"
        elif icon == "🟢":
            matched = [c for c in (bulls + bears) if c in active_codes]
            diag = f"Active: {', '.join(matched[:2])}"
        elif icon == "🔴":
            matched = [c for c in (bulls + bears) if c in active_codes]
            diag = f"Against: {', '.join(matched[:2])}"
        
        # Add context-specific diagnostics for key probes
        if label == "Squeeze" and icon == "⚫":
            sq = dt_context.get("squeeze", {})
            if isinstance(sq, dict):
                diag = f"Squeeze={sq.get('state', 'off')}"
            elif isinstance(sq, str):
                diag = f"Squeeze={sq}"
            else:
                diag = "No squeeze data"
        elif label == "VP Status" and icon == "⚫":
            vp = dt_context.get("volume_profile", {})
            if isinstance(vp, dict) and vp.get("poc"):
                diag = f"POC=${vp['poc']:,.0f}, price near value area"
            else:
                diag = "No VP data in trace"
        elif label == "Structure" and icon == "⚫":
            st = dt_context.get("structure", {})
            if isinstance(st, dict):
                diag = f"Trend={st.get('trend', 'neutral')}, no BOS/CHoCH"
            else:
                diag = "No structure data"
        elif label == "Levels" and icon == "⚫":
            sl = dt_context.get("session_levels", {})
            if isinstance(sl, dict) and sl.get("pdh"):
                diag = f"PDH=${sl.get('pdh',0):,.0f} PDL=${sl.get('pdl',0):,.0f} — not near"
            else:
                diag = "No level data"
        elif label == "AVWAP" and icon == "⚫":
            av = dt_context.get("avwap", {})
            if isinstance(av, dict) and av.get("avwap"):
                diag = f"AVWAP=${av['avwap']:,.0f}, pos={av.get('price_vs_avwap','?')}"
            else:
                diag = "No AVWAP data"
        elif label == "Auto R:R" and icon == "⚫":
            rr = dt_context.get("auto_rr", {})
            if isinstance(rr, dict) and rr.get("rr"):
                diag = f"R:R={rr['rr']:.2f} (needs EXCELLENT=2.0+ or POOR<1.2)"
            else:
                diag = "No auto R:R computed"
        
        rows.append((label, icon, color, diag))
```

**Step 2:** Now the `rows` tuples have 4 elements instead of 3. Update the code that USES `rows`.

Find line 476-477:

```python
    aligned_count = sum(1 for _, icon, _ in rows if icon == "🟢")
    against_count = sum(1 for _, icon, _ in rows if icon == "🔴")
```

**REPLACE** with:

```python
    aligned_count = sum(1 for _, icon, _, _ in rows if icon == "🟢")
    against_count = sum(1 for _, icon, _, _ in rows if icon == "🔴")
```

**Step 3:** Find line 478 (return statement):

```python
    return {"direction": direction, "entry": entry, "tp1": tp1, "stop": stop, "checks": checks, "gate": gate, "rows": rows, "aligned": aligned_count, "against": against_count, "total": len(rows)}
```

This doesn't need changing — `rows` is still passed through.

**Step 4:** Find where the radar HTML renders the probes. Search for `vctx['rows']` or the loop that builds probe dots. It will be in the HTML string around lines 540-580. Find the line that looks like:

```python
for label, icon, color in vctx['rows']:
```

**REPLACE** with:

```python
for label, icon, color, diag in vctx['rows']:
```

Then find the HTML that renders each probe row. It will look something like:

```python
<span style='color:{color}'>{icon}</span> {label}
```

**REPLACE** with:

```python
<span style='color:{color}' title='{diag}'>{icon}</span> {label} <span class='mini' style='opacity:0.5; font-size:0.7em;'>({diag})</span>
```

### Verify

```powershell
python scripts/pid-129/generate_dashboard.py
```

Open `http://localhost:8000`. The Confluence Radar should now show diagnostic text next to EACH probe:
- 🟢 Squeeze `(Active: SQUEEZE_FIRE)`
- ⚫ DXY Macro `(Needs: DXY_FALLING_BULLISH or DXY_RISING_BEARISH)`
- 🔴 Structure `(Against: STRUCTURE_BOS_BEAR)`

---

## 🟡 FIX 3 — Recent Signals Panel: Last 10 BTC Alerts

### Why
The dashboard only shows the LATEST alert per timeframe. A trader needs to see: did the system flip from LONG to SHORT? How many signals fired today? Are they consistent?

### What to change

**File:** `scripts/pid-129/generate_dashboard.py`

**Step 1:** Add this ENTIRE function. Paste it BEFORE `def generate_html():` (which is at line 479):

```python
def render_recent_alerts(alerts):
    """Show the last 10 BTC alerts with direction, confidence, and age."""
    now = datetime.now(timezone.utc)
    btc_alerts = [a for a in alerts if a.get("symbol") == "BTC"][-10:]
    if not btc_alerts:
        return """
        <section class="panel">
            <h2>📡 Recent Signals</h2>
            <p class="mini" style="padding:16px;">No BTC alerts logged yet. Waiting for first engine cycle to complete.</p>
        </section>
        """
    rows_html = []
    for a in reversed(btc_alerts):
        tf = a.get("timeframe", "-")
        direction = str(a.get("direction", "NEUTRAL")).upper()
        conf = int(a.get("confidence_score") or a.get("confidence") or 0)
        tier = str(a.get("tier", "-"))
        ts = parse_dt(a.get("timestamp"))
        age_str = "-"
        if ts:
            age_s = max(0, (now - ts.astimezone(timezone.utc)).total_seconds())
            if age_s < 60:
                age_str = f"{age_s:.0f}s"
            elif age_s < 3600:
                age_str = f"{age_s/60:.0f}m"
            else:
                age_str = f"{age_s/3600:.1f}h"
        outcome = a.get("outcome") or ("RESOLVED" if a.get("resolved") else "OPEN")
        
        dir_cls = "badge-good" if direction == "LONG" else ("badge-bad" if direction == "SHORT" else "badge-neutral")
        tier_cls = "badge-good" if tier == "A+" else ("badge-warn" if tier == "B" else "badge-neutral")
        
        # Color outcome
        if "WIN" in str(outcome).upper():
            out_cls = "badge-good"
        elif "LOSS" in str(outcome).upper():
            out_cls = "badge-bad"
        elif outcome == "OPEN":
            out_cls = "badge-warn"
        else:
            out_cls = "badge-neutral"
        
        # Count active codes
        dt_codes = (a.get("decision_trace") or {}).get("codes", [])
        code_count = len([c for c in dt_codes if not c.startswith("REGIME_") and not c.startswith("SESSION_")])
        
        rows_html.append(f"""
        <tr>
            <td>{tf}</td>
            <td><span class="pill {dir_cls}">{direction}</span></td>
            <td>{conf}</td>
            <td><span class="pill {tier_cls}">{tier}</span></td>
            <td>{code_count}</td>
            <td>{age_str}</td>
            <td><span class="pill {out_cls}">{outcome}</span></td>
        </tr>""")
    return f"""
    <section class="panel">
        <h2>📡 Recent Signals (Last 10)</h2>
        <table class="matrix-table">
            <thead>
                <tr><th>TF</th><th>Dir</th><th>Conf</th><th>Tier</th><th>Codes</th><th>Age</th><th>Status</th></tr>
            </thead>
            <tbody>{''.join(rows_html)}</tbody>
        </table>
    </section>
    """
```

**Step 2:** Wire it into the HTML. Find `def generate_html():` (line 479). Inside it, find the line where `lifecycle_html` is assigned. It will look like:

```python
    lifecycle_html = render_lifecycle_panel(alerts)
```

Add this line IMMEDIATELY AFTER it:

```python
    recent_alerts_html = render_recent_alerts(alerts)
```

**Step 3:** Find where `{lifecycle_html}` is placed in the big HTML f-string (around line 680-690). Add `{recent_alerts_html}` on the line immediately after `{lifecycle_html}`:

Example — find:
```python
    {lifecycle_html}
```

Change to:
```python
    {lifecycle_html}
    {recent_alerts_html}
```

### Verify

```powershell
python scripts/pid-129/generate_dashboard.py
```

Open `http://localhost:8000`. Scroll down. You should see a "📡 Recent Signals (Last 10)" table.

---

## 🟢 FIX 4 — System Accuracy Badge: Win Rate in Verdict Center

### Why
Seeing "A+ tier, 78 confidence" means nothing if the system's last 20 calls were 40% accuracy. A world-class trader always checks: "Is this system ACTUALLY winning?"

### What to change

**File:** `scripts/pid-129/generate_dashboard.py`

**Step 1:** Inside `build_verdict_context()` (starts at line 440), find the final `return` statement (line 478). It looks like:

```python
    return {"direction": direction, "entry": entry, "tp1": tp1, "stop": stop, "checks": checks, "gate": gate, "rows": rows, "aligned": aligned_count, "against": against_count, "total": len(rows)}
```

ADD this block BEFORE that return line:

```python
    # Phase 20 FIX 4: Calculate system accuracy from resolved trades
    resolved_btc = [a for a in alerts if a.get("symbol") == "BTC" and a.get("resolved")]
    recent_resolved = resolved_btc[-20:]
    if recent_resolved:
        wins = sum(1 for a in recent_resolved if str(a.get("outcome", "")).upper().startswith("WIN"))
        total_resolved = len(recent_resolved)
        accuracy_pct = (wins / total_resolved) * 100 if total_resolved > 0 else 0.0
        win_streak = 0
        for a in reversed(recent_resolved):
            if str(a.get("outcome", "")).upper().startswith("WIN"):
                win_streak += 1
            else:
                break
    else:
        wins, total_resolved, accuracy_pct, win_streak = 0, 0, 0.0, 0
```

Then modify the return to include the new keys. **REPLACE** the return line with:

```python
    return {"direction": direction, "entry": entry, "tp1": tp1, "stop": stop, "checks": checks, "gate": gate, "rows": rows, "aligned": aligned_count, "against": against_count, "total": len(rows), "accuracy_pct": accuracy_pct, "accuracy_wins": wins, "accuracy_total": total_resolved, "win_streak": win_streak}
```

**Step 2:** Add the accuracy badge HTML. Find the line in the verdict HTML section that shows the Direction pill. Search for this text:

```
Direction:
```

It will be inside an HTML string, something like:

```python
      <div class='mini' style='margin-bottom:8px;'>Direction: <span class='pill {badge_class_for_direction(vctx['direction'])}'>{vctx['direction']}</span></div>
```

ADD this line IMMEDIATELY AFTER that line:

```python
      <div class='mini' style='margin-bottom:8px;'>Edge (last {vctx.get('accuracy_total', 0)}): <span class='pill {"badge-good" if vctx.get("accuracy_pct", 0) >= 55 else "badge-warn" if vctx.get("accuracy_pct", 0) >= 40 else "badge-bad"}'>{vctx.get("accuracy_pct", 0):.0f}% ({vctx.get("accuracy_wins", 0)}W)</span>{" 🔥" + str(vctx.get("win_streak", 0)) if vctx.get("win_streak", 0) >= 3 else ""}</div>
```

### Verify

```powershell
python scripts/pid-129/generate_dashboard.py
```

Open `http://localhost:8000`. The Verdict Center should now show:
- `Direction: SHORT`
- `Edge (last 20): 65% (13W) 🔥5` — or if no resolved trades: `Edge (last 0): 0% (0W)`

---

## Final Verification Checklist

After ALL fixes, run this full check:

```powershell
# 1. Tests must pass
pytest tests/ -q --basetemp="c:\Users\lovel\trading\btc-alerts-mvp\tmp_pytest_base"

# 2. Clear state and run fresh cycle
python -c "open('.mvp_alert_state.json', 'w').write('{}')"
python app.py --once

# 3. Verify alerts were logged
python -c "lines=[l for l in open('logs/pid-129-alerts.jsonl').read().splitlines() if l.strip()]; print(f'Alerts: {len(lines)}')"

# 4. Regenerate dashboard
python scripts/pid-129/generate_dashboard.py

# 5. Start dashboard server
Start-Process -NoNewWindow -FilePath python -ArgumentList "scripts/pid-129/dashboard_server.py"
```

Then open `http://localhost:8000` and confirm:

- [x] **FIX 1:** `Alerts: 3+` (not 0) — alerts are actually firing
- [x] **FIX 1:** Confidence scores are in 30-80 range (not 1-13)
- [x] **FIX 2:** Each probe shows diagnostic text — gray probes say WHY they're gray
- [x] **FIX 3:** "📡 Recent Signals" panel visible with last 10 alerts
- [x] **FIX 4:** "Edge (last N)" badge visible in Verdict Center
- [x] No Python errors in the terminal

---

## Safety Rails — DO NOT CHANGE

- ❌ No new API calls or collectors
- ❌ No changes to `dashboard_server.py` WebSocket protocol
- ❌ No changes to the 15 probe definitions (only ADD diagnostic info)
- ❌ No renaming existing functions or variables
- ❌ No deleting existing tests
- ❌ No changing dashboard CSS class names (only ADD new HTML)

## Test Command (after EVERY change)

```powershell
pytest tests/ -q --basetemp="c:\Users\lovel\trading\btc-alerts-mvp\tmp_pytest_base"
```

Must show **34+ passed, 0 failures.**

## Commit When Done

```powershell
git add . ; git commit -m "feat(phase20): score calibration, probe diagnostics, recent signals, accuracy badge"
```

---
_Phase 20 | EMBER PID-129 | v20.0_
