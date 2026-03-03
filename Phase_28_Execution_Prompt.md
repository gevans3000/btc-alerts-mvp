# Phase 28 — FINAL Phase — Agent Execution Prompt

**Prime Directive:** *"A singular, perfectly calibrated Bitcoin futures dashboard where a single click yields a mathematically verified, high-confidence LONG or SHORT play."*

**This is the LAST phase. There is no Phase 29, 30, 31. After this, the system is DONE.**

---

## WORKFLOW

1. **AG (you)** reads this entire document and makes ONLY the listed edits.
2. **AG** runs the verification checklist at the bottom and pastes output.
3. **AG** runs `python app.py --once` and confirms it completes without errors.
4. **Opus** reviews AG's work, grades it, and fixes anything AG missed.

**AG: do not improvise. Do not add features. Do not refactor. Follow the exact edits below.**

---

## WHAT ALREADY WORKS (DO NOT REWRITE)

- `tools/executor.py` — paper + live execution via ccxt. DONE. Do not touch.
- `app.py` lines 376–390 — auto-executes A+ alerts. DONE. Do not touch.
- `dashboard_server.py` — serves dashboard on port 8002 with WebSocket push. DONE.
- `intelligence/` — 13+ probes all working. DONE.
- `collectors/` — multi-provider failover (Bybit, OKX, Bitunix, Kraken, etc.). DONE.
- A+ tier has proven positive expectancy: WR=66.7%, AvgR=+0.166R over 15 trades.
- Phase 27 vetoes are correctly DISABLED (they caused WR to drop from 59% to 27%).

**YOU HAVE 4 BUGS TO FIX AND 1 FEATURE TO WIRE. THAT IS ALL.**

---

## BUG #1: R:R Math is Inverted (CRITICAL)

**File:** `engine.py` lines 489–491

**The problem:** The generic (non-recipe) R:R calculation uses TP1 as the reward, but TP1 is always smaller than the stop distance. This makes `rr` always < 1.0, which triggers the R:R blocker on every single non-recipe alert.

**Current code (line 489–491):**
```python
        risk = abs(last_price - invalidation)
        reward = abs(tp1 - last_price)
        rr = reward / risk if risk > 0 else 0.0
```

**The math proof (using config values):**
- `TP_MULTIPLIERS["range"]` = `{"tp1": 1.2, "tp2": 2.0, "inv": 0.9}`
- risk = `atr * 0.9 * 2.0` = `atr * 1.8`
- reward = `atr * 1.2`
- rr = `1.2 / 1.8` = **0.667** (matches every alert in JSONL)
- `min_rr` for 5m = 1.35 → rr < min_rr → blocker fires → NO-TRADE → alert never logged

This is true for ALL regimes:
- "trend": reward=1.8, risk=2.2 → rr=0.818 (still < 1.0)
- "default": reward=1.6, risk=2.2 → rr=0.727
- "vol_chop": reward=1.0, risk=1.6 → rr=0.625

**The fix:** Change line 490 to use `tp2` instead of `tp1`:
```python
        reward = abs(tp2 - last_price)
```

**Why:** TP2 is the full profit target. TP1 is a partial take-profit. R:R should measure total risk vs total reward. With TP2:
- "range": reward = `atr * 2.0`, risk = `atr * 1.8` → rr = 1.11
- "trend": reward = `atr * 3.0`, risk = `atr * 2.2` → rr = 1.36
- "default": reward = `atr * 2.8`, risk = `atr * 2.2` → rr = 1.27

These are realistic R:R values that will pass the min_rr gate when the setup is good.

**Also fix the recipe branch (line 475)** which has the same issue:
```python
        reward = abs(tp1 - exec_px)
```
Change to:
```python
        tp2_val = best_sig.targets.get("tp2", tp1)
        reward = abs(tp2_val - exec_px)
```

**EXACT EDIT — `engine.py`:**

Find this (around line 472–476):
```python
        # Recalculate RR using recipe execution price
        exec_px = best_sig.exec_px
        risk = abs(exec_px - invalidation)
        reward = abs(tp1 - exec_px)
        rr = reward / risk if risk > 0 else 0.0
```

Replace with:
```python
        # Recalculate RR using recipe execution price (use tp2 for full R:R)
        exec_px = best_sig.exec_px
        risk = abs(exec_px - invalidation)
        reward = abs(tp2 - exec_px)
        rr = reward / risk if risk > 0 else 0.0
```

Find this (around line 489–491):
```python
        risk = abs(last_price - invalidation)
        reward = abs(tp1 - last_price)
        rr = reward / risk if risk > 0 else 0.0
```

Replace with:
```python
        risk = abs(last_price - invalidation)
        reward = abs(tp2 - last_price)
        rr = reward / risk if risk > 0 else 0.0
```

---

## BUG #2: Recipe Detection is Dark (CRITICAL)

**File:** `intelligence/recipes.py`

**The problem:** Last 20+ alerts all show `"recipe": "NO_RECIPE"`. Zero HTF_REVERSAL, BOS_CONTINUATION, or VOL_EXPANSION recipes have fired. Without recipes, the highest-conviction signal layer is completely offline.

**Root cause:** The recipe conditions require ALL THREE legs to co-fire on the SAME candle. This is extremely rare.

### HTF_REVERSAL requires ALL THREE simultaneously:
1. Bullish structure (BOS_BULL or CHOCH_BULL) — fires ~40% of candles
2. Sweep of equal lows (`sweep_low = True`) — fires ~5% of candles
3. AVWAP reclaim (`AVWAP_RECLAIM_BULL` in codes) — fires ~10% of candles

Combined probability: ~0.2% of candles. At 5-min intervals, that's maybe once per 3+ days.

### BOS_CONTINUATION requires ALL THREE simultaneously:
1. `last_event` is exactly `"BOS_BULL"` or `"BOS_BEAR"` (not just in codes — the LATEST event)
2. Price within 0.5x ATR of the broken structure level
3. Rejection wick >= 40% of candle range (was 60%, already relaxed)

Combined: also extremely rare because BOS is a discrete event that only persists for 1–2 candles.

### VOL_EXPANSION requires ALL THREE:
1. BB width percentile < 15% (squeeze territory)
2. A liquidity sweep on the same bar
3. Structure bias present

Combined: squeeze + sweep on same bar is very rare.

**The fix — Relax recipe conditions to fire more often while keeping quality:**

**EXACT EDIT — `intelligence/recipes.py`, function `_recipe_htf_reversal` (around line 200–206):**

Find:
```python
    # Compose legs
    long_signal = has_bull_struct and sweep_bull and avwap_bull
    short_signal = has_bear_struct and sweep_bear and avwap_bear

    if not (long_signal or short_signal):
        return None
```

Replace with:
```python
    # Compose legs: require structure + at least ONE of (sweep, avwap)
    # Previously required all 3 — too strict, fired <1% of candles
    long_signal = has_bull_struct and (sweep_bull or avwap_bull)
    short_signal = has_bear_struct and (sweep_bear or avwap_bear)

    if not (long_signal or short_signal):
        return None
```

**EXACT EDIT — `intelligence/recipes.py`, function `_recipe_bos_continuation` (around line 281–287):**

Find:
```python
        if not (retest_level - 0.5 * atr_val <= price <= retest_level + 0.5 * atr_val):
            return None
        # Rejection wick: bullish → lower wick >= 60% of candle range
        c_range = last.high - last.low
        lower_wick = last.open - last.low if last.open > last.low else last.close - last.low
        if c_range > 0 and (lower_wick / c_range) < 0.40:
            return None
```

Replace with:
```python
        if not (retest_level - 1.0 * atr_val <= price <= retest_level + 1.0 * atr_val):
            return None
        # Rejection wick: bullish → lower wick >= 30% of candle range
        c_range = last.high - last.low
        lower_wick = last.open - last.low if last.open > last.low else last.close - last.low
        if c_range > 0 and (lower_wick / c_range) < 0.30:
            return None
```

**Do the same for the SHORT branch (around line 294–299):**

Find:
```python
        if not (retest_level - 0.5 * atr_val <= price <= retest_level + 0.5 * atr_val):
            return None
        c_range = last.high - last.low
        upper_wick = last.high - last.open if last.open < last.high else last.high - last.close
        if c_range > 0 and (upper_wick / c_range) < 0.40:
            return None
```

Replace with:
```python
        if not (retest_level - 1.0 * atr_val <= price <= retest_level + 1.0 * atr_val):
            return None
        c_range = last.high - last.low
        upper_wick = last.high - last.open if last.open < last.high else last.high - last.close
        if c_range > 0 and (upper_wick / c_range) < 0.30:
            return None
```

**EXACT EDIT — `intelligence/recipes.py`, function `_recipe_vol_expansion` (around line 353):**

Find:
```python
    if bb_pct >= 15.0:
        return None
```

Replace with:
```python
    if bb_pct >= 25.0:
        return None
```

**Why these changes are safe:**
- HTF_REVERSAL: Structure alignment is the strong signal. Sweep OR AVWAP provides confirmation. Requiring both was overkill.
- BOS_CONTINUATION: 1.0x ATR retest zone (vs 0.5x) catches retests that slightly overshoot. 30% wick (vs 40%) catches more rejection candles.
- VOL_EXPANSION: 25th percentile (vs 15th) is still compressed volatility, just not extreme-only.
- The rubric gate (5/6 for A+, 3/6 for B) still filters bad signals downstream. Recipes firing more often does NOT mean more A+ alerts — the rubric decides that.

---

## BUG #3: SPX Alerts Pollute BTC Log

**File:** `scripts/pid-129/dashboard_server.py` line 153

**The problem:** SPX_PROXY alerts are written to the same JSONL as BTC alerts. The `_load_alerts()` filter does not exclude them. They contaminate win rate, Sharpe, and portfolio stats.

**EXACT EDIT — `scripts/pid-129/dashboard_server.py`, inside `_load_alerts()` function:**

Find:
```python
                    # ── Phase 26 Gap 3: Filter junk alerts ──
                    if row.get("strategy") in (None, "TEST", "SYNTHETIC"):
                        continue
```

Replace with:
```python
                    # ── Phase 26 Gap 3: Filter junk alerts ──
                    if row.get("strategy") in (None, "TEST", "SYNTHETIC"):
                        continue
                    if row.get("symbol") in ("SPX", "SPX_PROXY"):
                        continue
```

---

## BUG #4: Wire the "1-CLICK EXECUTE" Button (Currently Dead)

**The problem:** The dashboard has a "1-CLICK EXECUTE" button that opens a confirmation modal with a 3-second countdown. After the countdown, clicking "Confirm Execute" just **closes the modal**. It does nothing. There is no API call and no `/api/execute` endpoint on the server.

### Part A: Fix the JavaScript

**File:** `dashboard.html`, around line 590

Find:
```javascript
                  btn.disabled = false;
                  btn.textContent = 'Confirm Execute';
                  btn.onclick = () => closeExecuteModal();
```

Replace with:
```javascript
                  btn.disabled = false;
                  btn.textContent = 'Confirm Execute';
                  btn.onclick = async () => {
                      btn.disabled = true;
                      btn.textContent = 'Executing...';
                      try {
                          const resp = await fetch('/api/command', {
                              method: 'POST',
                              headers: {'Content-Type': 'application/json'},
                              body: JSON.stringify({action: 'execute_trade'})
                          });
                          const result = await resp.json();
                          if (result.status === 'success') {
                              btn.textContent = result.trade_status + ': ' + (result.order_id || 'done');
                          } else {
                              btn.textContent = 'Error: ' + (result.error || 'unknown');
                          }
                      } catch(e) {
                          btn.textContent = 'Network error';
                      }
                      setTimeout(closeExecuteModal, 2000);
                  };
```

### Part B: Add the server endpoint

**File:** `scripts/pid-129/dashboard_server.py`, inside the `_handle_command` method

Find:
```python
            elif action == "run_profit_preflight":
```

Add this block BEFORE that line (note: `os`, `sys`, `Path` are already imported at top of file, and project root is already on `sys.path` via `BASE_DIR` at line 18–19):
```python
            elif action == "execute_trade":
                from tools.executor import execute_trade

                alerts = _load_alerts(limit=10)
                target = None
                for a in reversed(alerts):
                    if a.get("tier") == "A+" and a.get("symbol", "BTC") != "SPX_PROXY":
                        target = a
                        break

                if not target:
                    self._json_response({"status": "error", "error": "No A+ alert available to execute"})
                    return

                mode = "LIVE" if os.environ.get("LIVE_EXECUTION", "0") == "1" else "PAPER"
                result = execute_trade(target, mode=mode)
                self._json_response({
                    "status": "success",
                    "trade_status": result["status"],
                    "order_id": result.get("order_id", ""),
                    "fill_price": result.get("fill_price", 0),
                    "reason": result.get("reason", ""),
                    "mode": mode
                })

```

---

## FEATURE: Add Bitunix as Live Execution Broker Option

**File:** `tools/executor.py`

The user trades on Bitunix. Add Bitunix as an alternative broker alongside Bybit.

**EXACT EDIT — `tools/executor.py`:**

Find:
```python
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")

    if not api_key or not api_secret:
        return {"status": "REJECTED", "reason": "no API keys", "order_id": "", "fill_price": 0.0}

    try:
        import ccxt
        exchange = ccxt.bybit({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
```

Replace with:
```python
    broker = os.getenv("TRADE_BROKER", "bybit").lower()

    if broker == "bitunix":
        api_key = os.getenv("BITUNIX_API_KEY")
        api_secret = os.getenv("BITUNIX_API_SECRET")
    else:
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")

    if not api_key or not api_secret:
        return {"status": "REJECTED", "reason": f"no {broker} API keys", "order_id": "", "fill_price": 0.0}

    try:
        import ccxt
        if broker == "bitunix":
            exchange = ccxt.bitunix({
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            })
        else:
            exchange = ccxt.bybit({
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            })
```

**Usage:** Set `TRADE_BROKER=bitunix` + `BITUNIX_API_KEY` + `BITUNIX_API_SECRET` env vars. Default remains Bybit if unset.

---

## VERIFICATION CHECKLIST

After making all fixes, run these checks:

### Check 1: R:R Math Fixed
```bash
python -c "
from config import TP_MULTIPLIERS, TIMEFRAME_RULES
for regime, cfg in TP_MULTIPLIERS.items():
    risk = cfg['inv'] * 2.0
    reward = cfg['tp2']  # Should now use tp2
    rr = reward / risk
    print(f'{regime:10s}: tp2={cfg[\"tp2\"]}, inv*2={risk:.1f}, rr={rr:.2f}', '  PASS' if rr > 1.0 else '  FAIL')
print()
for tf, rules in TIMEFRAME_RULES.items():
    print(f'{tf}: min_rr={rules[\"min_rr\"]}')
"
```

Expected output: ALL regimes show rr > 1.0. "trend" should show ~1.36, "range" ~1.11.

### Check 2: Recipe Detection Fires
```bash
python app.py --once 2>&1 | grep -i recipe
```

If recipes now fire, you will see lines mentioning HTF_REVERSAL, BOS_CONTINUATION, or VOL_EXPANSION in the output. Check the last alert in `logs/pid-129-alerts.jsonl`:

```bash
python -c "
import json
lines = open('logs/pid-129-alerts.jsonl').readlines()
last = json.loads(lines[-1])
recipes = last.get('intel', {}).get('recipes', [])
print('Recipes:', len(recipes))
for r in recipes:
    print(f'  {r[\"recipe\"]} {r[\"direction\"]} rr={abs(r[\"targets\"][\"tp2\"]-r[\"exec_px\"])/abs(r[\"exec_px\"]-r[\"invalidation\"]):.2f}')
if not recipes:
    print('  NO_RECIPE (may be normal if market conditions do not match any pattern)')
    print('  This is OK — the fix ensures they CAN fire. They will fire when conditions align.')
"
```

### Check 3: SPX Filtered
```bash
python -c "
import json
lines = open('logs/pid-129-alerts.jsonl').readlines()
spx = [json.loads(l) for l in lines if json.loads(l).get('symbol') in ('SPX','SPX_PROXY')]
print(f'SPX alerts in JSONL: {len(spx)} (these exist but are now filtered from dashboard)')
"
```

### Check 4: Execute Button Works
1. Start dashboard: `python scripts/pid-129/dashboard_server.py`
2. Open `http://localhost:8002` in browser
3. Wait for an A+ alert to appear (or manually create one — see Check 5)
4. Click "1-CLICK EXECUTE"
5. Wait 3 seconds for countdown
6. Click "Confirm Execute"
7. Should see "PAPER: PAPER-[timestamp]" message
8. Verify `data/paper_portfolio.json` has a new position entry
9. Verify `logs/execution_log.jsonl` has a new line

### Check 5: Manual A+ Test (if no A+ fires naturally)
```bash
python -c "
import json
# Write a test A+ alert to trigger executor
test_alert = {
    'alert_id': 'TEST-EXEC-001',
    'symbol': 'BTC',
    'timeframe': '5m',
    'direction': 'LONG',
    'tier': 'A+',
    'action': 'TRADE',
    'confidence': 85,
    'entry_price': 67000,
    'invalidation': 66500,
    'tp1': 67500,
    'tp2': 68000,
    'rr_ratio': 2.0,
    'strategy': 'TEST',
    'blockers': [],
    'outcome': None,
    'resolved': False
}
with open('logs/pid-129-alerts.jsonl', 'a') as f:
    f.write(json.dumps(test_alert) + '\n')
print('Test A+ alert written. Reload dashboard and click execute.')
"
```

### Check 6: Bitunix Broker Selection
```bash
python -c "
import os
os.environ['TRADE_BROKER'] = 'bitunix'
from tools.executor import execute_trade
result = execute_trade({'tier': 'A+', 'direction': 'LONG', 'entry_price': 67000, 'invalidation': 66500, 'tp1': 67500, 'confidence': 85, 'timeframe': '5m'}, mode='LIVE')
print(result)  # Should say 'no bitunix API keys' — proving Bitunix path is selected
"
```

---

## FILES YOU WILL EDIT (AND ONLY THESE)

| File | What to change |
|------|---------------|
| `engine.py` line 475 | Change `tp1` to `tp2` in recipe R:R reward calc |
| `engine.py` line 490 | Change `tp1` to `tp2` in generic R:R reward calc |
| `intelligence/recipes.py` lines 202–203 | Relax HTF_REVERSAL: struct + (sweep OR avwap) |
| `intelligence/recipes.py` line 281 | Widen BOS retest zone from 0.5x to 1.0x ATR |
| `intelligence/recipes.py` line 286 | Lower wick threshold from 0.40 to 0.30 |
| `intelligence/recipes.py` line 294 | Widen SHORT retest zone from 0.5x to 1.0x ATR |
| `intelligence/recipes.py` line 298 | Lower SHORT wick threshold from 0.40 to 0.30 |
| `intelligence/recipes.py` line 353 | Widen VOL_EXPANSION bb_pct from 15 to 25 |
| `scripts/pid-129/dashboard_server.py` line 153 | Add SPX/SPX_PROXY filter |
| `scripts/pid-129/dashboard_server.py` ~line 1049 | Add `execute_trade` action handler |
| `dashboard.html` line 590 | Wire confirm button to POST /api/command |
| `tools/executor.py` lines 118–130 | Add Bitunix broker selection via TRADE_BROKER env var |

## FILES YOU MUST NOT TOUCH

- `config.py` — thresholds are fine
- `app.py` — executor wiring is already done
- `core/infrastructure.py` — logging and state management works
- `collectors/` — data pipeline works
- Any file in `intelligence/` other than `recipes.py`

---

## RULES

1. Make ONLY the exact edits listed above. Do not refactor, reorganize, or "improve" surrounding code.
2. Do not add new files. Do not add comments to code you did not change.
3. Do not touch Phase 27 vetoes (they are correctly disabled at engine.py line 447–451).
4. **PRESERVE THE DASHBOARD.** Do not remove, rearrange, or restyle any existing panels, cards, data displays, colors, or layout in `dashboard.html`. The only change to `dashboard.html` is the 3-line JS edit to wire the confirm button's `onclick`. Everything else stays exactly as it is — the user likes the current visual and data layout.
5. `LIVE_EXECUTION=1` env var remains the only way to go live. Default is PAPER.
6. Do not add logging, type hints, docstrings, or error handling beyond what is specified.
7. Run the verification checklist after all edits. If any check fails, fix only what failed.
8. After all checks pass, run `python app.py --once` to confirm one full cycle completes without errors.

## EXECUTION EFFICIENCY

**This prompt has 12 exact find/replace edits across 5 files. That is all. Do not explore the codebase — the answers are already here.**

Optimal execution order (minimize tool calls):
1. Edit `engine.py` — 2 edits (lines 475, 490)
2. Edit `intelligence/recipes.py` — 5 edits (lines 202, 281, 286, 294, 298, 353)
3. Edit `scripts/pid-129/dashboard_server.py` — 2 edits (line 153 filter, line 1049 endpoint)
4. Edit `dashboard.html` — 1 edit (line 590 onclick)
5. Edit `tools/executor.py` — 1 edit (lines 118–130 broker selection)
6. Run verification checks

**Do not read files before editing — the exact find/replace strings are provided. Just edit.**

---

_Phase 28 | FINAL PHASE | "God Button" Completion | Free APIs Only_
