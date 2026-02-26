# Phase 20: Real Alerts & Dashboard Trust Layer

**Status:** 🔲 NOT STARTED
**Goal:** Make alerts fire in real market conditions, show the trader proof they're accurate, and add a live countdown so you never miss a setup.

---

> [!CAUTION]
> ## ⚠️ PREREQUISITE: Run `/phase19-verify` first
>
> Phase 19 applied all 14 probe fixes but the score multiplier may need tuning.
> Run the Phase 19 verification workflow BEFORE starting this phase.
> If `/phase19-verify` hasn't been run yet, do it now — it takes 5 minutes.

---

## Architecture Quick-Reference (READ THIS FIRST)

**Dear implementing AI:** This is how data flows. Read it before touching any file.

```
collectors/ → raw API data (price, derivatives, flows, social, macro)
     ↓
intelligence/ → each .py file computes a dict with "codes" and "pts" keys
     ↓
engine.py:compute_score() → collects all codes[] and pts → creates AlertScore object
     ↓
app.py → calls should_send() → if True, logs to JSONL + sends notification
     ↓
logs/pid-129-alerts.jsonl → one JSON line per alert, includes decision_trace.codes
     ↓
scripts/pid-129/generate_dashboard.py → reads JSONL → builds dashboard.html
     ↓
scripts/pid-129/dashboard_server.py → serves HTML + WebSocket live updates
```

### Key rule: If alerts don't appear in the JSONL, the dashboard has NO data to show.

---

## ⚡ IMPLEMENTATION ORDER

> [!IMPORTANT]
> Do fixes in this exact order. Each one is independent — if one fails, skip it and continue. Run tests after each fix.

| Priority | Fix # | What | Risk | Lines Changed |
|----------|-------|------|------|---------------|
| 🔴 1 | **FIX 1** | Score calibration — alerts actually fire | Medium | ~10 |
| 🟢 2 | **FIX 2** | Recent Alerts panel — see last 10 signals | Low | ~40 |
| 🟢 3 | **FIX 3** | Signal accuracy badge — proof it works | Low | ~30 |

---

## 🔴 FIX 1 — Score Calibration: Make Alerts Fire in Real Markets

**The Problem:** `engine.py` computes scores, but `_tier_and_action()` returns `action="SKIP"` because the normalized scores don't reach the `trade_long` or `watch_long` thresholds in `config.py`. No alerts reach the JSONL. The dashboard shows stale or no data.

**Why it matters:** If alerts never fire, nothing else in the system matters. This is the #1 blocker.

### Step 1: Diagnose the current score range

Run this command to see what scores the engine actually produces:

```powershell
# Step 1a: Check current thresholds
python -c "from config import TIMEFRAME_RULES; [print(f'{k}: trade_long={v[\"trade_long\"]}, watch_long={v[\"watch_long\"]}') for k,v in TIMEFRAME_RULES.items()]"
```

### Step 2: Add temporary debug logging

**File:** `engine.py` — find line 292 (the `total_score = total_score * SCORE_MULTIPLIER` line)

Add this line IMMEDIATELY AFTER it:

```python
    logger.info(f"SCORE_DEBUG {symbol} {timeframe}: raw={sum(breakdown.values())/SCORE_MULTIPLIER:.1f} x{SCORE_MULTIPLIER}={total_score:.1f} breakdown={dict((k,round(v,1)) for k,v in breakdown.items() if v != 0)}")
```

> [!NOTE]
> You need to add `import logging` and `logger = logging.getLogger(__name__)` at the top of `engine.py` if they don't exist. Check first.

### Step 3: Run one cycle and read the debug output

```powershell
python app.py --once 2>&1 | Select-String "SCORE_DEBUG"
```

You will see lines like:
```
SCORE_DEBUG BTC 5m: raw=4.2 x3.0=12.6 breakdown={momentum: 3.0, volatility: 1.2}
SCORE_DEBUG BTC 15m: raw=8.1 x3.0=24.3 breakdown={momentum: 5.0, htf: 3.1}
SCORE_DEBUG BTC 1h: raw=11.0 x3.0=33.0 breakdown={momentum: 6.0, htf: 5.0}
```

### Step 4: Calibrate the multiplier

Look at the debug output. The goal is:

| Timeframe | Target normalized score for WATCH | Target for TRADE |
|-----------|-----------------------------------|------------------|
| 5m | 25+ (watch_long threshold) | 45+ (trade_long threshold) |
| 15m | 20+ | 40+ |
| 1h | 15+ | 35+ |

Check `config.py` for the exact `TIMEFRAME_RULES` values. Then:

**If most scores are between 10-30 after 3x multiplier:**
→ Change `SCORE_MULTIPLIER` from `3.0` to `5.0` in `engine.py` line 291.

**If most scores are between 5-15 after 3x multiplier:**
→ Change `SCORE_MULTIPLIER` from `3.0` to `7.0`.

**If scores are already 30+ but still SKIP:**
→ The problem is in `config.py` thresholds, not the multiplier. Lower `trade_long` and `watch_long` values by 10 each.

**File:** `engine.py` — line 291

```python
    # BEFORE (Phase 19):
    SCORE_MULTIPLIER = 3.0
    
    # AFTER (Phase 20 — calibrated for real market conditions):
    SCORE_MULTIPLIER = 5.0  # Adjust based on Step 3 diagnosis
```

### Step 5: Verify alerts now fire

```powershell
# Clear state so alerts aren't filtered by cooldown
python -c "open('.mvp_alert_state.json', 'w').write('{}')"

# Run one cycle
python app.py --once

# Check if alerts were logged
python -c "lines = [l for l in open('logs/pid-129-alerts.jsonl').read().splitlines() if l.strip()]; print(f'Alerts logged: {len(lines)}'); [print(f'  {__import__(\"json\").loads(l)[\"timeframe\"]} {__import__(\"json\").loads(l)[\"direction\"]} conf={__import__(\"json\").loads(l)[\"confidence\"]} tier={__import__(\"json\").loads(l)[\"tier\"]}') for l in lines[-6:]]"
```

**Expected output:**
```
Alerts logged: 3
  5m SHORT conf=45 tier=A+
  15m SHORT conf=38 tier=B
  1h SHORT conf=52 tier=A+
```

If you see `Alerts logged: 0`, go back to Step 3 and increase the multiplier further.

### Step 6: Remove debug logging

Delete the `logger.info(f"SCORE_DEBUG ...")` line you added in Step 2.

### Step 7: Regenerate dashboard and verify

```powershell
python scripts/pid-129/generate_dashboard.py
```

Open `http://localhost:8000` and verify probes are now lighting up (not all gray).

**Result:** Alerts fire in real market conditions. Dashboard shows live data.

---

## 🟢 FIX 2 — Recent Alerts Panel: See Your Last 10 Signals

**The Problem:** The dashboard shows only the LATEST alert per timeframe. You can't see the history — did the system call 5 longs in a row? Was there a direction flip? Without history, you can't judge if the system is behaving rationally.

**File:** `scripts/pid-129/generate_dashboard.py`

### Step 1: Add a `render_recent_alerts()` function

Find the line `def generate_html():` (around line 479). Insert this function BEFORE it:

```python
def render_recent_alerts(alerts):
    """Show the last 10 BTC alerts with direction, confidence, and age."""
    now = datetime.now(timezone.utc)
    btc_alerts = [a for a in alerts if a.get("symbol") == "BTC"][-10:]
    if not btc_alerts:
        return """
        <section class="panel">
            <h2>Recent Signals</h2>
            <p class="mini">No BTC alerts logged yet. Run <code>python app.py --once</code> to generate.</p>
        </section>
        """
    rows = []
    for a in reversed(btc_alerts):
        tf = a.get("timeframe", "-")
        direction = str(a.get("direction", "NEUTRAL")).upper()
        conf = int(a.get("confidence_score") or a.get("confidence") or 0)
        tier = str(a.get("tier", "-"))
        ts = parse_dt(a.get("timestamp"))
        age_str = "-"
        if ts:
            age_s = max(0, (now - ts.astimezone(timezone.utc)).total_seconds())
            age_str = f"{age_s/60:.0f}m" if age_s < 3600 else f"{age_s/3600:.1f}h"
        outcome = a.get("outcome") or "PENDING"
        resolved = a.get("resolved", False)
        
        dir_class = "badge-good" if direction == "LONG" else ("badge-bad" if direction == "SHORT" else "badge-neutral")
        tier_class = "badge-good" if tier == "A+" else ("badge-warn" if tier == "B" else "badge-neutral")
        outcome_class = "badge-good" if "WIN" in str(outcome) else ("badge-bad" if outcome == "LOSS" else "badge-neutral")
        
        # Count active codes for this alert
        dt_codes = (a.get("decision_trace") or {}).get("codes", [])
        code_count = len([c for c in dt_codes if "REGIME" not in c and "SESSION" not in c])
        
        rows.append(f"""
        <tr>
            <td>{tf}</td>
            <td><span class="pill {dir_class}">{direction}</span></td>
            <td>{conf}/100</td>
            <td><span class="pill {tier_class}">{tier}</span></td>
            <td>{code_count} codes</td>
            <td>{age_str}</td>
            <td><span class="pill {outcome_class}">{outcome}</span></td>
        </tr>
        """)
    return f"""
    <section class="panel">
        <h2>Recent Signals (Last 10)</h2>
        <table class="matrix-table">
            <thead>
                <tr><th>TF</th><th>Direction</th><th>Confidence</th><th>Tier</th><th>Confluence</th><th>Age</th><th>Outcome</th></tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </section>
    """
```

### Step 2: Wire it into the HTML output

Find this line in `generate_html()` (around line 683):

```python
    {lifecycle_html}
```

Add IMMEDIATELY AFTER it:

```python
    {render_recent_alerts(alerts)}
```

And add this line near the other variable assignments (around line 597, after `lifecycle_html`):

```python
    recent_html = render_recent_alerts(alerts)
```

Then replace `{render_recent_alerts(alerts)}` with `{recent_html}`.

### Step 3: Regenerate and verify

```powershell
python scripts/pid-129/generate_dashboard.py
```

Open `http://localhost:8000` and scroll to see the "Recent Signals" panel.

**Result:** You can see the last 10 alerts with direction, confidence, tier, confluence code count, age, and outcome. This tells you if the system is generating real, diverse signals.

---

## 🟢 FIX 3 — Signal Accuracy Badge: Proof the System Works

**The Problem:** The dashboard shows what the system THINKS right now, but not how ACCURATE it has been. If the system's last 10 calls were 7/10 wins, you should see that front-and-center. If it was 2/10, you should know to stay flat.

**File:** `scripts/pid-129/generate_dashboard.py`

### Step 1: Add an accuracy calculator

Find the `build_verdict_context()` function (around line 440). At the END of this function, before the `return` statement, add:

```python
    # Phase 20: Calculate recent accuracy
    resolved_btc = [a for a in alerts if a.get("symbol") == "BTC" and a.get("resolved")]
    recent_resolved = resolved_btc[-20:]  # Last 20 resolved trades
    if recent_resolved:
        wins = sum(1 for a in recent_resolved if str(a.get("outcome", "")).startswith("WIN"))
        total = len(recent_resolved)
        accuracy = (wins / total) * 100
        streak = 0
        for a in reversed(recent_resolved):
            if str(a.get("outcome", "")).startswith("WIN"):
                streak += 1
            else:
                break
    else:
        accuracy = 0.0
        wins = 0
        total = 0
        streak = 0
```

Then add these keys to the return dict (the `return { ... }` at the end of the function):

```python
    "accuracy": accuracy, "accuracy_wins": wins, "accuracy_total": total, "win_streak": streak,
```

### Step 2: Display the accuracy badge in the Verdict Center

Find this line in the verdict HTML (around line 559):

```python
      <div class='mini' style='margin-bottom:8px;'>Direction: <span class='pill {badge_class_for_direction(vctx['direction'])}'>{vctx['direction']}</span></div>
```

Add IMMEDIATELY AFTER it:

```python
      <div class='mini' style='margin-bottom:8px;'>System Accuracy (last 20): <span class='pill {"badge-good" if vctx.get("accuracy", 0) >= 55 else "badge-warn" if vctx.get("accuracy", 0) >= 40 else "badge-bad"}'>{vctx.get("accuracy", 0):.0f}% ({vctx.get("accuracy_wins", 0)}W/{vctx.get("accuracy_total", 0)})</span>{f" 🔥 {vctx.get('win_streak', 0)} streak" if vctx.get("win_streak", 0) >= 3 else ""}</div>
```

### Step 3: Regenerate and verify

```powershell
python scripts/pid-129/generate_dashboard.py
```

Open `http://localhost:8000`. Below the Direction badge, you should see:
- `System Accuracy (last 20): 65% (13W/20)` — or whatever the real numbers are
- If there's a 3+ win streak, you'll see a 🔥 emoji

**Result:** The trader can see at a glance whether the system's recent calls have been profitable. This builds trust and helps you decide whether to follow the signal.

---

## Verification Plan

After EACH fix, run:

```powershell
# Step 1: Run tests (MUST pass before you continue)
pytest tests/ -q --basetemp="c:\Users\lovel\trading\btc-alerts-mvp\tmp_pytest_base"

# Step 2: Regenerate dashboard
python scripts/pid-129/generate_dashboard.py

# Step 3: Check dashboard at http://localhost:8000/
```

### Visual Checks After ALL Fixes
- [ ] Alerts are logged to `logs/pid-129-alerts.jsonl` (not empty)
- [ ] Confidence scores are realistic (30-80 range, not 1-13)
- [ ] Confluence Radar shows ≥ 8/15 active probes (not gray)
- [ ] "Recent Signals" panel shows last 10 alerts with direction + outcome
- [ ] "System Accuracy" badge shows win rate in Verdict Center
- [ ] Dashboard server runs without errors on `http://localhost:8000`

---

## What NOT To Change (Safety Rails)

- ❌ Do NOT add new API calls or collectors
- ❌ Do NOT change the dashboard layout/CSS (only ADD new panels)
- ❌ Do NOT modify `dashboard_server.py` WebSocket protocol
- ❌ Do NOT change the 15 probe definitions list
- ❌ Do NOT rename any existing code variables or function signatures
- ❌ Do NOT delete or modify existing tests

---

## Test Command (run after ANY change)

```powershell
pytest tests/ -q --basetemp="c:\Users\lovel\trading\btc-alerts-mvp\tmp_pytest_base"
```

Must show 34+ passed, 0 failures.

---
_Phase 20 Blueprint | EMBER PID-129 | 2026-02-26_
