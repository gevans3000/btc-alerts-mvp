---
description: Verify and finalize Phase 19 probe fixes — handoff from previous agent session
---

# Phase 19 Verification & Finalization

## Current State (2026-02-26 16:58 ET)

**All 14 code fixes from `Phase_19.md` are applied and committed.** Git checkpoint: `34db5f8` on `main`.

### What's DONE ✅
- All 14 source code changes applied (verified line-by-line)
- `pytest tests/ -q --basetemp="c:\Users\lovel\trading\btc-alerts-mvp\tmp_pytest_base"` → **34 passed, 0 failures**
- `python -c "from config import validate_config; validate_config(); print('Config OK')"` → OK
- `Phase_19.md` status set to ✅ DONE
- `PHASE_ROADMAP.md` updated to v19.0 with Phase 19 completion block
- Stale alerts purged (backup at `logs/pid-129-alerts.jsonl.phase19.bak`)
- `.mvp_alert_state.json` cleared
- NEUTRAL trades auto-resolve in `core/infrastructure.py` line 53-55
- NEUTRAL trades skipped in `app.py` portfolio.on_alert at line 362-367
- Dashboard server runs on `http://localhost:8000`

### What NEEDS VERIFICATION 🔲

**Problem:** `python app.py --once` runs successfully but alerts are not being written to `logs/pid-129-alerts.jsonl`. The alerts compute correctly (state file shows tiers), but `should_send()` in `core/infrastructure.py` filters them because `score.action == "SKIP"`.

**Root cause to investigate:** The `_tier_and_action()` function in `engine.py` (line 37-64) returns `action="SKIP"` when the absolute total_score doesn't meet the `trade_long` or `watch_long` thresholds from `config.py TIMEFRAME_RULES`. Even with the 3x multiplier, real market conditions may produce scores that don't cross the thresholds.

**Diagnosis steps:**

// turbo-all

1. Run a diagnostic to see actual computed scores:
```powershell
python -c "from engine import compute_score; from config import TIMEFRAME_RULES; print('Current thresholds:'); [print(f'  {k}: trade_long={v[\"trade_long\"]}, watch_long={v[\"watch_long\"]}') for k,v in TIMEFRAME_RULES.items()]"
```

2. Add temporary debug logging to see what scores the engine actually produces. In `engine.py`, after line 292 (`total_score = total_score * SCORE_MULTIPLIER`), temporarily add:
```python
    import logging; logging.getLogger(__name__).info(f"PHASE19_DEBUG: {symbol} {timeframe} raw={sum(breakdown.values())/SCORE_MULTIPLIER:.1f} normalized={total_score:.1f} breakdown={breakdown}")
```

3. Run `python app.py --once` and check the log output for `PHASE19_DEBUG` lines.

4. If scores are below thresholds:
   - Option A: Increase `SCORE_MULTIPLIER` from 3.0 to 4.0 or 5.0 in `engine.py` line 291
   - Option B: Lower `trade_long` / `watch_long` thresholds in `config.py`
   - Option C: Both — but be conservative; the multiplier should map "5 agreeing signals" to A+ tier

5. After fixing, run `python app.py --once` again and verify:
   - `logs/pid-129-alerts.jsonl` has lines with non-SKIP actions
   - Confidence scores are in 30-80 range (not 1-13)
   - Tiers show realistic values (A+ only on strong confluence)

6. Start the dashboard server: `Start-Process -NoNewWindow -FilePath python -ArgumentList "scripts/pid-129/dashboard_server.py"`

7. Open `http://localhost:8000` in browser and verify:
   - [ ] Confluence Radar shows ≥ 8/15 active probes (not gray)
   - [ ] No A+ tier showing on scores below 45
   - [ ] Execution Decision shows graduated alignment info (not just "WAIT")
   - [ ] Lifecycle panel has 0 stale NEUTRAL trades
   - [ ] Trade Safety gate shows AMBER or GREEN (not RED)
   - [ ] Confidence scores in Execution Matrix are realistic (30-80 range)

8. If everything looks good, commit:
```powershell
git add . ; git commit -m "fix(phase19): tune score thresholds for live market conditions"
```

### Files Modified by Phase 19 (for reference)

| File | Fixes Applied |
|------|--------------|
| `engine.py` | FIX 12 (score multiplier L291-292), FIX 4 (VP codes L112-113), FIX 6 (funding fallback L180-182), FIX 8 (OI/basis thresholds L186-190), FIX 9 (ML threshold L298-301), FIX 5 (auto_rr early L303-313) |
| `scripts/pid-129/generate_dashboard.py` | FIX 10 (tier guard L187-192), FIX 13 (graduated execution L109-160), FIX 14 (NEUTRAL lifecycle L327-336), FIX 11 (safety threshold L450) |
| `intelligence/structure.py` | FIX 1 (bias codes L104-112) |
| `intelligence/session_levels.py` | FIX 2 (proximity codes L83-103) |
| `intelligence/anchored_vwap.py` | FIX 3 (band→probe codes L89-100) |
| `intelligence/macro_correlation.py` | FIX 7 (gold min candles L21, DXY inverse L28-30) |
| `core/infrastructure.py` | FIX 14 (NEUTRAL resolved L53-55) |
| `app.py` | FIX 14 (skip NEUTRAL portfolio L362-367) |

### Safety Rails (DO NOT CHANGE)
- ❌ Do NOT add new API calls or collectors
- ❌ Do NOT change the dashboard layout/CSS
- ❌ Do NOT modify `dashboard_server.py` WebSocket protocol
- ❌ Do NOT add new intelligence modules
- ❌ Do NOT change the 15 probe definitions list in `generate_dashboard.py`
- ❌ Do NOT rename any existing code variables or function signatures

### Test Command (run after ANY change)
```powershell
pytest tests/ -q --basetemp="c:\Users\lovel\trading\btc-alerts-mvp\tmp_pytest_base"
```
Must show 34 passed, 0 failures.
