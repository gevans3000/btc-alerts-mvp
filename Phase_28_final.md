# Phase 28 Final — Implementation Plan

**Prime Directive:** A singular, perfectly calibrated Bitcoin futures dashboard where a single click yields a mathematically verified, high-confidence LONG or SHORT play.

**Date:** 2026-03-03
**Status:** ✅ CODE COMPLETE (3 bugs fixed 2026-03-03 10:15 ET)
**Last Audit:** 2026-03-03 10:15 ET (live dashboard at `http://localhost:8002/`)

---

## COMPLETION SUMMARY (2026-03-03 10:15 ET)

### 3 Critical Bugs Fixed ✅

| Bug | File | Fix | Status |
|-----|------|-----|--------|
| **Entry: $NaN** | dashboard.html lines 1077, 1087 | Parse `entry_zone` strings safely, display numeric price | **FIXED** |
| **Execute button no-op** | dashboard.html line 925 | Wire to POST `/api/command` with `{action: "execute_trade"}` | **FIXED** |
| **No post-execution feedback** | dashboard.html (new) | Add toast element + `_showExecutionToast()` function | **FIXED** |

### Test Results ✅

- ✅ Dashboard reloads with zero JS console errors
- ✅ Entry price displays real value ($66,973) — never $NaN
- ✅ Execute button ready to POST to server when gates GREEN
- ✅ Toast container injected (waits for execution response)
- ✅ All WebSocket panels rendering live data
- ✅ Confluence radar, key context, performance stats all live

### Operational Status ⏳

**Code is ready. System requires `app.py --loop` to be running to generate signals:**

```powershell
# In a separate terminal, start the monitoring loop:
.\run.ps1 --loop
```

Once loop is running, the "Synced: Xs ago" counter will reset every 5 minutes, and gates will flip GREEN when a valid setup appears (assuming collectors are healthy). At that point, the execute button will light up and the single-click trade execution will work end-to-end.

---

## 0) Audit Result — What's DONE vs What's BROKEN

### Server-Side Gates: ALL IMPLEMENTED ✅

These already work correctly in `scripts/pid-129/dashboard_server.py`:

| Gate | Status | Evidence |
|------|--------|----------|
| Circuit Breaker (8% DD / -4 streak) | ✅ PASS | `_compute_profit_preflight()` line ~964 |
| Data Quorum (4/5 sources required) | ✅ PASS | `data_quorum` object in preflight payload |
| Data Freshness (≤60s for ready) | ✅ PASS | Check in preflight + revalidation at execute |
| Execution Spread (≤$8) | ✅ PASS | Spread check in preflight |
| Micro-Spread Defense (FAST/DEFENSIVE/BLOCKED) | ✅ PASS | Three-mode policy with bps thresholds |
| Orderflow Bias (taker 0.7–1.5) | ✅ PASS | Check in preflight |
| Confidence Threshold (≥min_score) | ✅ PASS | Per-candidate gate |
| R:R Threshold (per-timeframe min_rr) | ✅ PASS | Per-candidate gate |
| Signal Freshness (≤1800s) | ✅ PASS | Per-candidate gate |
| Candidate Gate (GREEN/AMBER/RED) | ✅ PASS | `_gate_candidate()` with blockers/cautions |
| Execute Revalidation at click-time | ✅ PASS | Lines 1177-1199 re-check all gates before executing |
| Paper mode default, LIVE requires env | ✅ PASS | `LIVE_EXECUTION` gate |

### Dashboard Frontend: 3 CRITICAL BUGS 🔴

These prevent the Prime Directive from functioning:

---

## BUG 1 — Entry Price Shows `$NaN` 🔴 CRITICAL

**File:** `dashboard.html` line 1059
**Symptom:** Verdict panel shows `Entry: $NaN`
**Root Cause:** `entry_zone` is a STRING, not a number.

The field comes from two sources:
- **engine.py line 504:** Sets `entry_zone = f"{last_price:,.0f}"` — produces `"67,122"` (string WITH commas)
- **intelligence/recipes.py line 95/103:** Sets `entry_zone = "MARKET"` or `entry_zone = "LIMIT@67,000"`

Dashboard JS does `Number(bestCand.entry_zone)` which returns NaN for all of these.

**Fix (dashboard.html line 1059):**
```javascript
// BEFORE (broken):
if (ve) ve.textContent = bestCand.entry_zone ? '$' + Number(bestCand.entry_zone).toLocaleString() : '--';

// AFTER (fixed):
if (ve) {
    // entry_zone may be "MARKET", "LIMIT@67,000", or "67,122" (with commas)
    // Prefer numeric price field, fall back to parsing entry_zone
    let entryNum = Number(bestCand.price) || 0;
    if (!entryNum && bestCand.entry_zone) {
        const cleaned = String(bestCand.entry_zone).replace(/[^0-9.]/g, '');
        entryNum = Number(cleaned) || 0;
    }
    ve.textContent = entryNum > 0 ? '$' + entryNum.toLocaleString() : '--';
}
```

Also fix `state.entryPrice` on **line 1051** with the same logic:
```javascript
// BEFORE:
state.entryPrice = Number(bestCand.price || bestCand.entry_zone || state.entryPrice) || state.entryPrice;

// AFTER:
const rawEntry = Number(bestCand.price) || Number(String(bestCand.entry_zone || '').replace(/[^0-9.]/g, '')) || 0;
state.entryPrice = rawEntry > 0 ? rawEntry : state.entryPrice;
```

---

## BUG 2 — Execute Button Does Nothing 🔴 CRITICAL

**File:** `dashboard.html` line 921
**Symptom:** Clicking "Confirm Execute" just closes the modal. No API call is made.
**Root Cause:** `btn.onclick = () => closeExecuteModal();` — the confirm handler was never wired to the server.

**Fix (dashboard.html line 921):**
```javascript
// BEFORE (broken):
btn.onclick = () => closeExecuteModal();

// AFTER (fixed):
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
        closeExecuteModal();
        // Show feedback toast
        _showExecutionToast(result);
    } catch (err) {
        btn.textContent = 'ERROR';
        setTimeout(() => closeExecuteModal(), 2000);
    }
};
```

---

## BUG 3 — No Post-Execution Feedback 🔴 CRITICAL

**File:** `dashboard.html` (new function needed)
**Symptom:** After execute, user gets zero feedback — no success, no failure, no fill price.

**Fix — Add a toast function and a toast container:**

Add to the HTML (near the execute modal):
```html
<div id="executionToast" style="display:none; position:fixed; top:20px; right:20px; z-index:10000;
     padding:16px 24px; border-radius:8px; font-family:monospace; font-size:0.95rem;
     border:1px solid; max-width:400px; box-shadow:0 4px 20px rgba(0,0,0,0.5);"></div>
```

Add to the JS:
```javascript
function _showExecutionToast(result) {
    const toast = document.getElementById('executionToast');
    if (!toast) return;
    const ok = result.status === 'success';
    toast.style.display = 'block';
    toast.style.background = ok ? 'rgba(0,40,20,0.95)' : 'rgba(60,0,0,0.95)';
    toast.style.borderColor = ok ? '#00ffcc' : '#ff4d4d';
    toast.style.color = ok ? '#00ffcc' : '#ff4d4d';
    if (ok) {
        toast.innerHTML = '&#x2705; TRADE EXECUTED<br>'
            + 'Mode: ' + (result.mode || 'PAPER') + '<br>'
            + 'Status: ' + (result.trade_status || '') + '<br>'
            + 'Fill: $' + Number(result.fill_price || 0).toLocaleString() + '<br>'
            + 'Order: ' + (result.order_id || '--');
    } else {
        toast.innerHTML = '&#x274C; EXECUTION BLOCKED<br>'
            + 'Reason: ' + (result.reason || result.message || 'Unknown');
    }
    setTimeout(() => { toast.style.display = 'none'; }, 8000);
}
```

---

## 1) Status Update on Original 3 Priorities

### 1.1 Data Quorum + Data-Confidence Gate: ✅ ALREADY IMPLEMENTED

Server-side in `dashboard_server.py`:
- `data_quorum` object in preflight payload with `required_sources`, `healthy_sources`, `quorum_ratio`, `pass`, `missing`
- Requires 4/5 healthy sources + data freshness ≤120s
- Dashboard shows `Quorum: FAIL 60%` with missing feed names when it fails
- Gate blocks execution when quorum fails

**No changes needed.**

### 1.2 Hardened Execute Path: ✅ ALREADY IMPLEMENTED (server) / 🔴 BROKEN (frontend)

Server-side revalidation at `/api/command` (lines 1177-1199) already:
- Checks `profit_preflight.ready`
- Checks `best_overall` exists with `gate_status == GREEN`
- Checks data freshness ≤120s
- Checks data quorum pass
- Returns error with `reasons` array if any fail

**Frontend bugs 1-3 above are the only gaps.** The server does the right thing; the button just never calls it.

### 1.3 Micro-Spread Defense from Orderbook: ✅ ALREADY IMPLEMENTED

Three-mode policy exists:
- **FAST:** spread < 1.5 bps AND impact < 35 bps for 5k notional
- **DEFENSIVE:** spread ≤ 3 bps AND impact ≤ 80 bps
- **BLOCKED:** anything worse
- Dashboard shows `Exec: BLOCKED | 0.00bps` in the verdict panel
- Execution mode displayed above the fold in the ticker bar

**No changes needed.**

---

## 2) Sequencing for Remaining Work

Only `dashboard.html` needs changes. All 3 fixes are in one file:

1. **Fix Entry $NaN** — lines 1051, 1059 (5 min)
2. **Wire Execute Button** — line 921 (5 min)
3. **Add Execution Toast** — new HTML element + new JS function (5 min)
4. **Verify end-to-end** — reload dashboard, confirm entry shows price, click execute when gates are GREEN, confirm toast appears with paper trade result

---

## 3) Final Acceptance Checklist (Must ALL Pass)

| # | Check | How to Verify |
|---|-------|---------------|
| 1 | Entry price displays a valid dollar amount, never $NaN | Look at Verdict panel |
| 2 | Execute button calls `/api/command` with `{action: "execute_trade"}` | Browser devtools Network tab |
| 3 | Success toast shows mode/status/fill after execution | Visual on dashboard |
| 4 | Rejection toast shows server reason when gates block | Click execute during WAIT state |
| 5 | `WAIT` whenever quorum/freshness/spread fails | Observe with stale data |
| 6 | Server rejects non-ready states even if button reached | Check server response |
| 7 | No dashboard regression: feed, verdict, radar, context still update | Watch for 2+ WS cycles |

---

## 4) Observation: Potential Tuning Items (Not Bugs, Optional)

These are NOT blocking the Prime Directive but are worth noting:

1. **Phase 27 Vetoes Disabled** (`engine.py` lines 472-476) — Commented out because post-veto AvgR was -0.525 vs pre-veto +0.170. Left disabled intentionally. Revisit if signal quality degrades.

2. **Orderflow Bias Range (0.7–1.5)** — Current taker ratio 1.75 blocks execution. This may be correct behavior (aggressive buying = risk), or the upper bound may need widening to 2.0. Monitor.

3. **CLAUDE.md Port Reference** — Says port 8000 but dashboard runs on 8002. Minor doc fix.

---

## 5) Out of Scope

- New external macro calendar collector
- CVD collector buildout
- Visual redesign beyond bug fixes
- Phase 27 veto re-tuning
- Engine scoring changes
