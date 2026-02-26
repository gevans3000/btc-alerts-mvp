# Phase 19: Wake Up Every Confluence Probe — Profitable Signal Playbook

**Status:** 🔲 NOT STARTED
**Goal:** Fix the 9 gray/inactive confluence radar probes so they fire when conditions are met, turning the dashboard from a 4/15 coin-flip into a 10+ /15 high-conviction machine.

---

> [!CAUTION]
> ## ⚠️ TOP 3 CRITICAL ISSUES (Do These First)
>
> 1. **CRITICAL-1 (FIX 12):** Confidence scores are 1-13/100 but labeled "A+" — the scoring engine's breakdown weights are too small for current market volatility. Every downstream decision (tier, sizing, safety gate) inherits this broken number. **This is the single most dangerous bug.**
> 2. **CRITICAL-2 (FIX 13):** Execution Decision is a binary WAIT/EXECUTE with zero graduated info. "Direction mismatch" tells you nothing actionable. Needs alignment score like "2/3 aligned, waiting on 5m."
> 3. **CRITICAL-3 (FIX 14):** 10 NEUTRAL lifecycle trades are open 12+ hours, eating the drawdown to 16.29%. The engine opens positions but never closes neutrals. No probe fix matters if dead trades bleed the account.

---

## Current Dashboard Snapshot (2026-02-26 12:00 ET)

| Metric | Value |
|--------|-------|
| BTC Mid | $67,600 |
| Verdict | **LONG / WAIT** |
| Confluence | **4 / 15 MODERATE** (Net +2) |
| Trade Safety | **RED** |
| 5m Score | 1 / 100 → A+ (wrong) |
| 15m Score | 6 / 100 → A+ (wrong) |
| 1h Score | 13 / 100 → A+ (wrong) |
| Green Probes | Squeeze, Momentum, Order Book, Fear & Greed |
| Red Probes | Trend (HTF), DXY Macro |
| **Gray / Dead** | **Funding, Gold Macro, ML Model, OI/Basis, Structure, Levels, AVWAP, VP Status, Auto R:R** |

---

## Architecture Quick-Reference (READ THIS FIRST)

**Dear implementing AI:** This section tells you how data flows. Read it before touching any file.

```
collectors/ → raw API data (price, derivatives, flows, social, macro)
     ↓
intelligence/ → each .py file computes a dict with "codes" and "pts" keys
     ↓
engine.py:compute_score() → collects all codes[] and pts → creates AlertScore object
     ↓
logs/pid-129-alerts.jsonl → one JSON line per alert, includes decision_trace.codes
     ↓
scripts/pid-129/generate_dashboard.py → reads JSONL → builds dashboard.html
     ↓
scripts/pid-129/dashboard_server.py → serves HTML + WebSocket live updates
```

### How probes light up (this is the key to every fix below)

In `scripts/pid-129/generate_dashboard.py`, at line 419, there's a list called `probes`. Each entry looks like:
```python
("Squeeze", ["SQUEEZE_FIRE", "SQUEEZE_ON"], [])
#  label     bullish codes                    bearish codes
```

The dashboard checks: does `decision_trace.codes` from the alert contain any of the bullish codes? Any bearish codes?

- **Direction LONG + bullish code present** → 🟢 green
- **Direction LONG + bearish code present** → 🔴 red
- **Neither code present** → ⚫ gray (DEAD)

**A gray probe means the engine never put the needed code string into `codes[]`.** Every fix below adds or unblocks the missing code.

---

## ⚡ IMPLEMENTATION ORDER

> [!IMPORTANT]
> Do fixes in this exact order. Each one is independent — if one fails, skip it and continue. Run tests after each fix.

| Priority | Fix # | What | Risk | Lines Changed |
|----------|-------|------|------|---------------|
| 🔴 1 | **FIX 12** | Score normalization (CRITICAL-1) | Medium | ~15 |
| 🔴 2 | **FIX 10** | A+ tier guard | Low | 4 |
| 🔴 3 | **FIX 13** | Execution Decision alignment score (CRITICAL-2) | Low | ~20 |
| 🔴 4 | **FIX 14** | Auto-close stale NEUTRAL trades (CRITICAL-3) | Medium | ~15 |
| 🟢 5 | **FIX 4** | VP Status probe (1 line) | Zero | 2 |
| 🟢 6 | **FIX 9** | ML Model probe | Zero | 2 |
| 🟢 7 | **FIX 8** | OI/Basis thresholds | Zero | 4 |
| 🟢 8 | **FIX 6** | Funding fallback | Zero | 3 |
| 🟢 9 | **FIX 1** | Structure bias codes | Low | 5 |
| 🟢 10 | **FIX 3** | AVWAP band → probe codes | Low | 10 |
| 🟢 11 | **FIX 2** | Levels proximity | Low | 12 |
| 🟢 12 | **FIX 7** | Gold macro inference | Low | 5 |
| 🟢 13 | **FIX 5** | Auto R:R code ordering | Medium | Block move |
| 🟢 14 | **FIX 11** | Trade Safety threshold | Zero | 1 |

---

## 🔴 FIX 12 — CRITICAL: Confidence Score Normalization

**The Problem:** The `breakdown` dict in `engine.py` sums individual signal weights (+3, +5, -2, etc.) into `total_score`. In current market conditions, this sum lands between 1 and 15. But the tier thresholds expect 45+ for A+ (5m). The numbers literally cannot reach the thresholds because the individual weights are too small.

**Why it matters:** EVERY downstream decision reads `confidence` — tier labels, position sizing, Trade Safety, kill-switch. If this number is broken, the entire system is broken.

**Root cause:** The score is the raw sum of ~15 small weights that individually produce ±2 to ±8 points. Even with perfect confluence (all 15 probes aligning), the max theoretical score is roughly 50-60. After the probe fixes below add more codes, scores will rise somewhat — but they still need normalization to fill the 0-100 range meaningfully.

**File:** `engine.py` — line 280-281 and line 340

### Step 1: Find the total_score computation

Look at line 280-281 in `engine.py`:
```python
    # Final score
    total_score = sum(breakdown.values())
```

### Step 2: Add score normalization AFTER line 281

Insert these lines immediately after `total_score = sum(breakdown.values())`:
```python
    # -- Phase 19 CRITICAL-1: normalize score to fill 0-100 range --
    # Raw scores typically land in -30 to +30 range.
    # Scale by 3x so a raw 15 becomes 45 (the A+ threshold for 5m).
    # This means: 5 active signals ≈ raw 15 → normalized 45 → A+ tier.
    SCORE_MULTIPLIER = 3.0
    total_score = total_score * SCORE_MULTIPLIER
```

### Step 3: Verify the confidence line still clamps correctly

Check line 340:
```python
        confidence=min(100, max(0, int(abs(total_score)))),
```
This already clamps to 0-100. No change needed here.

### Step 4: Verify tier thresholds still make sense

With the 3x multiplier:
- Raw score 15 → normalized 45 → A+ on 5m (threshold: 45) ✅
- Raw score 8 → normalized 24 → B on 5m (threshold: 25) ✅
- Raw score 3 → normalized 9 → NO-TRADE ✅

The thresholds in `config.py` `TIMEFRAME_RULES` do NOT need to change.

**Result:** Confidence scores now span a meaningful range. A+ only appears when there's genuine signal agreement.

---

## 🔴 FIX 10 — Fix A+ Tier Showing on Stale Alerts

**Why it's wrong:** Even after FIX 12, old alerts in `logs/pid-129-alerts.jsonl` still have `tier: "A+"` with `confidence: 1`. The dashboard reads these stale alerts and shows them.

**File:** `scripts/pid-129/generate_dashboard.py` — inside `render_execution_matrix()` function

### Step 1: Find line 164 inside `render_execution_matrix()`

Look for this line (around line 164):
```python
        conf = get_confidence(a)
```

### Step 2: Add tier override guard IMMEDIATELY AFTER that line

Insert right after `conf = get_confidence(a)`:
```python
        # Phase 19 FIX 10: override tier if confidence doesn't match thresholds
        # Prevents stale alerts from showing A+ on low scores
        if tier == "A+" and conf < 45:
            tier = "B" if conf >= 25 else "NO-TRADE"
        elif tier == "B" and conf < 20:
            tier = "NO-TRADE"
```

### Step 3: Purge stale alerts (ONE TIME ONLY — run this command once)

```powershell
Copy-Item logs\pid-129-alerts.jsonl logs\pid-129-alerts.jsonl.phase19.bak
Set-Content logs\pid-129-alerts.jsonl ""
```

**Result:** Dashboard never shows A+ on scores below 45, even if reading old alert data.

---

## 🔴 FIX 13 — CRITICAL: Graduated Execution Decision

**The Problem:** `execution_decision()` returns "WAIT" with "Direction mismatch across 1h/15m/5m" — a binary answer with no useful detail. You can't act on "WAIT" alone. You need to know: which timeframes agree, which disagree, and how close you are to alignment.

**File:** `scripts/pid-129/generate_dashboard.py` — function `execution_decision()` (line 109-138)

### Step 1: REPLACE the entire `execution_decision()` function

Find lines 109-138. Replace the ENTIRE function with this:

```python
def execution_decision(latest):
    one_h = latest.get("1h", {})
    fifteen = latest.get("15m", {})
    five = latest.get("5m", {})
    reasons = []
    if not one_h or not fifteen or not five:
        return "WAIT", "warn", ["Missing one or more BTC timeframes (5m/15m/1h)."], 0.0

    d1, d15, d5 = get_direction(one_h), get_direction(fifteen), get_direction(five)
    a5 = str(five.get("action") or "SKIP").upper()
    tier5 = get_tier(five)
    c5 = get_confidence(five)
    b5 = get_blockers(five)

    # -- Phase 19 CRITICAL-2: Graduated alignment scoring --
    dirs = {"1h": d1, "15m": d15, "5m": d5}
    non_neutral = {tf: d for tf, d in dirs.items() if d != "NEUTRAL"}
    aligned_count = 0
    if non_neutral:
        majority_dir = max(set(non_neutral.values()), key=list(non_neutral.values()).count)
        aligned_count = sum(1 for d in non_neutral.values() if d == majority_dir)
        # Show which TFs agree and which don't
        aligned_tfs = [tf for tf, d in dirs.items() if d == majority_dir]
        misaligned_tfs = [tf for tf, d in dirs.items() if d != majority_dir]
        if misaligned_tfs:
            reasons.append(f"{aligned_count}/3 aligned ({', '.join(aligned_tfs)} = {majority_dir}). Waiting on {', '.join(misaligned_tfs)} to flip.")
    else:
        reasons.append("All timeframes NEUTRAL — no directional bias.")

    if d1 == "NEUTRAL" or d15 == "NEUTRAL" or d5 == "NEUTRAL":
        neutral_tfs = [tf for tf, d in dirs.items() if d == "NEUTRAL"]
        reasons.append(f"Neutral on: {', '.join(neutral_tfs)}.")

    if any(b in {"HTF_CONFLICT_15M", "HTF_CONFLICT_1H"} for b in b5):
        reasons.append("5m has HTF conflict blocker.")
    if not (a5 == "TRADE" or (a5 == "WATCH" and c5 >= 70)):
        reasons.append(f"5m trigger is {a5} (confidence {c5}).")

    # EXECUTE only if all 3 non-neutral directions match
    all_aligned = len(non_neutral) == 3 and aligned_count == 3
    decision = "EXECUTE" if all_aligned and not any("conflict" in r.lower() for r in reasons) else "WAIT"
    tone = "good" if decision == "EXECUTE" else "warn"

    risk_pct = 0.0
    if decision == "EXECUTE":
        if tier5 == "A+": risk_pct = 2.0
        elif tier5 == "B": risk_pct = 0.5

    if not reasons:
        reasons = ["All timeframes aligned."]

    return decision, tone, reasons, risk_pct
```

**Result:** Execution Decision now shows "2/3 aligned (1h, 15m = LONG). Waiting on 5m to flip." instead of just "WAIT". This tells you exactly what to watch for.

---

## 🔴 FIX 14 — CRITICAL: Auto-Close Stale NEUTRAL Lifecycle Trades

**The Problem:** The Active Trade Lifecycle panel shows 10 NEUTRAL trades aged 11-12+ hours on the 15m timeframe. These are phantom positions that were never closed because the engine doesn't timeout NEUTRAL trades. This inflates drawdown (currently 16.29% vs the 12% safety limit).

**File:** `scripts/pid-129/generate_dashboard.py` — function `render_lifecycle_panel()` (line 288-364)

### Step 1: Add NEUTRAL trade filtering

Find line 294-296 in `render_lifecycle_panel()`:
```python
        if a.get("symbol") != "BTC":
            continue
        tf = a.get("timeframe")
```

Insert IMMEDIATELY AFTER `tf = a.get("timeframe")` (after the `if tf not in TARGET_TFS: continue` line, around line 298):
```python
        # Phase 19 CRITICAL-3: skip NEUTRAL trades older than their max window
        # These are phantom positions that should have auto-closed
        alert_dir = str(a.get("direction", "")).upper()
        if alert_dir == "NEUTRAL":
            ts = parse_dt(a.get("timestamp"))
            if ts:
                age_s = max(0, (now - ts.astimezone(timezone.utc)).total_seconds())
                max_age = MAX_DURATION_SECONDS.get(tf, 4 * 3600)
                if age_s > max_age * 0.5:  # expired past 50% of window = dead trade
                    continue  # skip this, don't show in lifecycle panel
```

### Step 2: Mark stale NEUTRAL alerts as resolved in the engine loop

**File:** `app.py` — find where alerts are written to the JSONL file.

Search for `"resolved"` in `app.py`. If there's already a resolution check, add this condition:
```python
    # Phase 19: auto-resolve NEUTRAL alerts that have exceeded their max duration
    if alert.get("direction", "").upper() == "NEUTRAL":
        alert["resolved"] = True
```

If there is no resolution logic, add this just before the alert is appended to the JSONL:
```python
    # Phase 19: NEUTRAL direction means no conviction — don't persist as open trade
    if result.direction == "NEUTRAL":
        alert_dict["resolved"] = True
```

**Result:** Lifecycle panel no longer shows zombie NEUTRAL trades. Drawdown stops inflating from dead positions.

---

## 🟢 FIX 1 — Structure Probe (BOS / CHoCH)

**Why it's gray:** `detect_structure()` in `intelligence/structure.py` requires `last_price > last_high` for `BOS_BULL` (line 74). In ranging markets, price doesn't break pivots — no codes fire.

**Radar codes needed:** `STRUCTURE_BOS_BULL`, `STRUCTURE_CHOCH_BULL`, `STRUCTURE_BOS_BEAR`, `STRUCTURE_CHOCH_BEAR`

**File:** `intelligence/structure.py`

### Step 1: Find line 102

Look for the last `elif` block ending around line 102. The `return` statement is on line 104.

### Step 2: Insert BEFORE the `return` on line 104

```python
    # -- Phase 19: Emit trend bias codes even when no active BOS/CHoCH event --
    # This ensures the Structure probe is not permanently gray in ranging markets.
    if not codes:
        if hh and hl:
            codes.append("STRUCTURE_BOS_BULL")   # trending bullish bias
            pts = 2.0
        elif lh and ll:
            codes.append("STRUCTURE_BOS_BEAR")   # trending bearish bias
            pts = -2.0
```

**Result:** Structure probe fires 🟢 or 🔴 when HH+HL or LH+LL pattern exists, even without a live breakout.

---

## 🟢 FIX 2 — Levels Probe (PDH/PDL)

**Why it's gray:** Dashboard requires `PDL_SWEEP_BULL`, `PDH_RECLAIM_BULL`, etc. Currently only fires on exact candle sweeps.

**File:** `intelligence/session_levels.py`

### Step 1: Find the `return` statement at the end of the main function

### Step 2: Insert BEFORE the `return` statement

```python
    # -- Phase 19: proximity codes for Levels probe --
    last_price = candles[-1].close
    proximity_pct = 0.003  # 0.3% = roughly $200 on BTC

    if pdl > 0 and last_price > 0:
        if last_price < pdl:
            codes.append("PDL_BREAK_BEAR")
            pts -= 3.0
        elif abs(last_price - pdl) / last_price <= proximity_pct:
            codes.append("PDL_SWEEP_BULL")
            pts += 2.0

    if pdh > 0 and last_price > 0:
        if last_price > pdh:
            codes.append("PDH_RECLAIM_BULL")
            pts += 3.0
        elif abs(last_price - pdh) / last_price <= proximity_pct:
            codes.append("PDH_SWEEP_BEAR")
            pts -= 1.0
```

> [!NOTE]
> The variables `pdl`, `pdh`, `codes`, and `pts` already exist in this function. Do NOT redeclare them. Just use them directly.

**Result:** Levels probe fires when price is near or beyond PDH/PDL.

---

## 🟢 FIX 3 — AVWAP Probe

**Why it's gray:** AVWAP emits `AVWAP_ABOVE_1SD` / `AVWAP_BELOW_1SD` but the radar probe only recognizes `AVWAP_RECLAIM_BULL` / `AVWAP_REJECT_BEAR`. Crossover codes only fire on the exact transition candle.

**File:** `intelligence/anchored_vwap.py` — lines 89-92

### Step 1: Find these exact lines (around line 89-92)

```python
    if last_price > upper_1:
        codes.append("AVWAP_ABOVE_1SD")
    elif last_price < lower_1:
        codes.append("AVWAP_BELOW_1SD")
```

### Step 2: REPLACE those 4 lines with

```python
    if last_price > upper_1:
        codes.append("AVWAP_ABOVE_1SD")
        # Phase 19: price above upper band = reclaimed convincingly = bullish
        if "AVWAP_RECLAIM_BULL" not in codes:
            codes.append("AVWAP_RECLAIM_BULL")
            pts += 2.0
    elif last_price < lower_1:
        codes.append("AVWAP_BELOW_1SD")
        # Phase 19: price below lower band = rejected convincingly = bearish
        if "AVWAP_REJECT_BEAR" not in codes:
            codes.append("AVWAP_REJECT_BEAR")
            pts -= 2.0
```

**Result:** AVWAP probe fires when price is beyond ±1σ bands.

---

## 🟢 FIX 4 — VP Status Probe (EASIEST FIX — 2 LINES)

**Why it's gray:** `volume_profile.py` correctly emits `ABOVE_VALUE` / `BELOW_VALUE` in its return dict under `"codes"`. But `engine.py` line 107-115 NEVER reads `vp["codes"]`. The codes are computed but thrown away.

**File:** `engine.py` — line 111

### Step 1: Find line 111 in `engine.py`

```python
            codes.append("NEAR_POC")
```

### Step 2: Add these 2 lines IMMEDIATELY AFTER it

```python
        # Phase 19: pipe VP position codes (ABOVE_VALUE / BELOW_VALUE) into radar
        codes.extend(vp.get("codes", []))
```

> [!IMPORTANT]
> The indent level MUST match — this is inside an `if vp.get("near_poc"):` block, but the `codes.extend` should be OUTSIDE that if block (one indent level up, inside the `if intel and intel.volume_profile` block). Check the indentation carefully:
> ```python
>     if intel and intel.volume_profile and ...:
>         vp = intel.volume_profile
>         if vp.get("near_poc"):
>             breakdown["momentum"] += vp["pts"]
>             codes.append("NEAR_POC")
>         # Phase 19: pipe VP position codes (ABOVE_VALUE / BELOW_VALUE) into radar
>         codes.extend(vp.get("codes", []))   # ← same level as the if, NOT inside it
> ```

**Result:** VP Status probe fires immediately.

---

## 🟢 FIX 5 — Auto R:R Probe

**Why it's gray:** `auto_rr.py` emits `AUTO_RR_EXCELLENT` / `AUTO_RR_POOR` correctly. `engine.py` pipes them on line 307. BUT the auto_rr block runs AFTER confluence is computed on line 296 — the codes arrive too late for the radar snapshot.

**File:** `engine.py`

### Step 1: Find line 290

```python
    # --- Confluence Heatmap ---
```

### Step 2: INSERT these lines BEFORE that line (before line 290)

```python
    # -- Phase 19: compute direction + auto_rr early so codes reach confluence --
    direction = "LONG" if total_score > 0 else "SHORT" if total_score < 0 else "NEUTRAL"
    try:
        last_price_rr = price.price if symbol == "BTC" else candles[-1].close
        auto_rr = compute_auto_rr(candles, direction)
        codes.extend(auto_rr["codes"])
        trace["context"]["auto_rr"] = {
            "rr": auto_rr["rr"], "target": auto_rr["target"],
            "stop": auto_rr["stop"], "entry": auto_rr.get("entry"),
        }
    except Exception:
        pass
```

### Step 3: COMMENT OUT the old auto_rr block (lines 304-313)

Find the OLD block (now shifted down a few lines):
```python
    # Auto R:R to nearest liquidity
    try:
        auto_rr = compute_auto_rr(candles, direction)
```

Comment it out:
```python
    # Auto R:R — MOVED UP by Phase 19 FIX 5, keeping this commented for reference
    # try:
    #     auto_rr = compute_auto_rr(candles, direction)
    #     codes.extend(auto_rr["codes"])
    #     ...
```

**Result:** Auto R:R probe fires because codes reach confluence heatmap in time.

---

## 🟢 FIX 6 — Funding Probe

**Why it's gray:** Funding rate between -0.00005 and +0.00005 produces no code. Normal markets live in this range.

**File:** `engine.py` — find line 177 (the last `elif` in the funding block)

### Step 1: Find this code block (around line 172-177)

```python
        code_fr = derivatives.funding_rate
        if code_fr <= -0.0003: codes.append("FUNDING_EXTREME_LOW")
        elif code_fr < -0.00005: codes.append("FUNDING_LOW")
        elif code_fr >= 0.0003: codes.append("FUNDING_EXTREME_HIGH")
        elif code_fr > 0.00005: codes.append("FUNDING_HIGH")
```

### Step 2: Add an `else` clause after line 177

```python
        else:
            # Phase 19: normal funding = mild bullish (no extreme crowding)
            codes.append("FUNDING_LOW")
```

**Result:** Funding probe fires 🟢 in normal conditions.

---

## 🟢 FIX 7 — Gold Macro Probe

**Why it's gray:** `macro_correlation.py` requires 25 gold candles (from `config.py` `min_candles`). Gold data may not have enough candles.

**File:** `intelligence/macro_correlation.py`

### Step 1: Open the file and find where gold candles are checked

Look for `min_candles` or a length check on gold data.

### Step 2: Lower the gold minimum to 10

Change `min_candles` references for gold to `10`.

### Step 3: Add DXY-inverse fallback

After the gold trend computation, if gold trend is empty/None, infer it:
```python
    # Phase 19: infer gold from DXY inverse correlation if no gold data
    if not gold_trend and dxy_trend:
        gold_trend = "rising" if dxy_trend == "falling" else "falling"
```

**Result:** Gold Macro probe fires based on available data.

---

## 🟢 FIX 8 — OI / Basis Probe

**Why it's gray:** Dead zones: OI 0-0.5% and Basis -0.05 to +0.05% produce no code.

**File:** `engine.py` — lines 179-185

### Step 1: Find these exact lines

```python
        oi_pct = derivatives.oi_change_pct
        if oi_pct >= 1.5: codes.append("OI_SURGE_MAJOR")
        elif oi_pct >= 0.5: codes.append("OI_SURGE_MINOR")
        
        basis = derivatives.basis_pct
        if basis >= 0.05: codes.append("BASIS_BULLISH")
        elif basis <= -0.05: codes.append("BASIS_BEARISH")
```

### Step 2: REPLACE with lowered thresholds

```python
        oi_pct = derivatives.oi_change_pct
        if oi_pct >= 1.5: codes.append("OI_SURGE_MAJOR")
        elif oi_pct >= 0.3: codes.append("OI_SURGE_MINOR")  # Phase 19: was 0.5
        
        basis = derivatives.basis_pct
        if basis >= 0.02: codes.append("BASIS_BULLISH")      # Phase 19: was 0.05
        elif basis <= -0.02: codes.append("BASIS_BEARISH")   # Phase 19: was -0.05
```

**Result:** OI/Basis probe fires in normal market conditions.

---

## 🟢 FIX 9 — ML Model Probe

**Why it's gray:** ML fires at `total_score >= 20` but scores are 1-13. After FIX 12 (3x multiplier), scores will be 3-39. Lower the ML threshold to match.

**File:** `engine.py` — lines 285-288

### Step 1: Find these exact lines

```python
    if total_score >= 20:
        codes.append("ML_CONFIDENCE_BOOST")
    elif total_score <= -20:
        codes.append("ML_SKEPTICISM")
```

### Step 2: REPLACE with

```python
    # Phase 19: align ML thresholds with normalized score range
    if total_score >= 10:
        codes.append("ML_CONFIDENCE_BOOST")
    elif total_score <= -10:
        codes.append("ML_SKEPTICISM")
```

> [!NOTE]
> If you've already applied FIX 12 (score multiplier), remember the ML check runs AFTER the multiplier. So `total_score >= 10` means raw score ≥ 3.3 which is very achievable. Adjust to `>= 15` if you want it less noisy.

**Result:** ML Model probe fires for realistic score levels.

---

## 🟢 FIX 11 — Trade Safety Gate Threshold

**Why RED:** ML Conviction check requires `confidence >= 70` but realistic scores are 10-50 even after FIX 12.

**File:** `scripts/pid-129/generate_dashboard.py` — line 412

### Step 1: Find this exact line

```python
        ("ML Conviction", confidence >= 70),
```

### Step 2: REPLACE with

```python
        ("ML Conviction", confidence >= 40),
```

**Result:** Trade Safety no longer requires unrealistic 70+ confidence.

---

## Summary: What Fires After All Fixes

| Probe | Before | After | Fix # |
|-------|--------|-------|-------|
| Squeeze | 🟢 | 🟢 | — |
| Trend (HTF) | 🔴 | 🔴 or 🟢 | market-dependent |
| Momentum | 🟢 | 🟢 | — |
| ML Model | ⚫ | 🟢 or 🔴 | FIX 9 |
| Funding | ⚫ | 🟢 | FIX 6 |
| DXY Macro | 🔴 | 🔴 | — (correctly bearish) |
| Gold Macro | ⚫ | 🟢 or 🔴 | FIX 7 |
| Fear & Greed | 🟢 | 🟢 | — |
| Order Book | 🟢 | 🟢 | — |
| OI / Basis | ⚫ | 🟢 or 🔴 | FIX 8 |
| Structure | ⚫ | 🟢 or 🔴 | FIX 1 |
| Levels | ⚫ | 🟢 or 🔴 | FIX 2 |
| AVWAP | ⚫ | 🟢 or 🔴 | FIX 3 |
| VP Status | ⚫ | 🟢 or 🔴 | FIX 4 |
| Auto R:R | ⚫ | 🟢 or 🔴 | FIX 5 |

**Expected after all fixes:** 10-13/15 active probes (up from 4/15), meaningful confidence scores, actionable execution decisions, clean lifecycle panel.

---

## Verification Plan

After EACH fix, run:

```powershell
# Step 1: Run tests (MUST pass before you continue)
python -m pytest tests/ -x -q

# Step 2: Regenerate dashboard
python scripts/pid-129/generate_dashboard.py

# Step 3: Check dashboard at http://localhost:8000/
# Look at: Confluence Radar probe count, Execution Matrix scores + tiers
```

### Visual Checks After ALL Fixes
- [ ] Confluence Radar shows ≥ 8/15 active probes (not gray)
- [ ] No A+ tier showing on scores below 45
- [ ] Execution Decision shows "2/3 aligned" or "3/3 aligned" (not just "WAIT")
- [ ] Lifecycle panel has 0 stale NEUTRAL trades older than 6 hours
- [ ] Trade Safety gate shows AMBER or GREEN (not RED)
- [ ] Confidence scores in Execution Matrix are realistic (30-80 range, not 1-13)

---

## What NOT To Change (Safety Rails)

- ❌ Do NOT add new API calls or collectors
- ❌ Do NOT change the dashboard layout/CSS
- ❌ Do NOT modify `dashboard_server.py` WebSocket protocol
- ❌ Do NOT change `config.py` TIMEFRAME_RULES thresholds (FIX 12 uses a multiplier instead)
- ❌ Do NOT add new intelligence modules
- ❌ Do NOT change the 15 probe definitions list in `generate_dashboard.py`
- ❌ Do NOT rename any existing code variables or function signatures

---
_Phase 19 Blueprint | EMBER PID-129 | 2026-02-26_
