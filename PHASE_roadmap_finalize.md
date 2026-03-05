# PHASE_ROADMAP_FINALIZE.md

**Objective:** Fix integration issues between app.py and dashboard_server.py, harden flat-file IPC, and validate Phase 29–31 weighted confluence system.

**Scope:** Bug fixes and hardening ONLY. No new features.

---

## Part 1: Fix Port Mismatch [x]

**Priority:** High — anyone following docs gets a broken dashboard.

### Issue
- `CLAUDE.md` line 25: says `http://localhost:8000`
- `OPERATOR.md` line 53: says `http://localhost:8000/api/alerts`
- `OPERATOR.md` line 55: says `ws://localhost:8000/ws`
- `dashboard_server.py` line 22: `PORT = 8002` (actual)

### Fix
1. `CLAUDE.md` line 25 — change `8000` → `8002`
2. `OPERATOR.md` line 53 — change `http://localhost:8000/api/alerts` → `http://localhost:8002/api/alerts`
3. `OPERATOR.md` line 55 — change `ws://localhost:8000/ws` → `ws://localhost:8002/ws`
4. Search both files for any other `8000` refs and fix them

### Verification
```bash
grep -n "8000" CLAUDE.md OPERATOR.md
# Expected: zero matches after fix
```

---

## Part 2: Re-enable Dashboard HTML Auto-Generation [x]

**Priority:** Medium — dashboard.html goes stale after code changes.

### Issue
- `app.py` line 417 has:
  ```python
  # os.system(f"{sys.executable} scripts/pid-129/generate_dashboard.py")
  ```
- `scripts/pid-129/generate_dashboard.py` EXISTS. Main function is `generate_html()`.
- Without this call, `dashboard.html` is never regenerated.

### Fix
1. In `app.py` line 417, replace the commented `os.system` call with a proper Python import:
   ```python
   try:
       from scripts.pid_129.generate_dashboard import generate_html
       generate_html()
   except Exception as e:
       logging.warning(f"Dashboard HTML generation failed: {e}")
   ```
   **Note:** The function is `generate_html()` (NOT `generate_dashboard_html()`). The module path uses underscores (`pid_129`) because Python imports can't use hyphens — verify the directory has an `__init__.py` or use `importlib`.

2. **Alternative if import path fails** (scripts/pid-129 has a hyphen):
   ```python
   import subprocess
   subprocess.run([sys.executable, "scripts/pid-129/generate_dashboard.py"],
                  capture_output=True, timeout=30)
   ```
   This is what the original commented code did (via `os.system`), just safer.

3. **Guard:** Only regenerate when alerts were produced (not on SKIP cycles):
   ```python
   if any(a.get("action") != "SKIP" for a in alerts):
       # regenerate dashboard HTML
   ```

### Verification
```bash
python app.py --once
# Check: dashboard.html mtime should be within last 60 seconds
```

### Gotcha
The directory `scripts/pid-129/` has a hyphen. Python can't import `pid-129` as a module name. Check if `scripts/pid_129/` (underscore) also exists as a symlink or alias. If not, use the subprocess approach (Option 2 above).

---

## Part 3: Dashboard Heartbeat — Already Partially Wired [x]

**Priority:** Low — verify existing wiring, don't add new code.

### Issue (CORRECTED from original plan)
The original plan said "dashboard_server.py never reads last_cycle.json" — **THIS WAS WRONG.**

**Actual state:**
- `app.py` lines 430–443: writes `data/last_cycle.json` with heartbeat data
- `dashboard_server.py` lines 936–958: ALREADY reads it via `_safe_json(BASE_DIR / "data" / "last_cycle.json", {})`

### Fix
1. **Verify** the heartbeat data flows end-to-end:
   - Run `python app.py --once`
   - Check `data/last_cycle.json` has fresh timestamp
   - Start dashboard, confirm heartbeat appears in UI
2. If heartbeat is read but not displayed in the HTML, check `generate_dashboard.py` for heartbeat rendering.
3. **No new endpoints needed** — this is already wired.

### Verification
```bash
python -c "import json; print(json.load(open('data/last_cycle.json')))"
# Should show recent timestamp, btc_price, cycle_duration_s
```

---

## Part 4: Document 50-Alert Cap [x]

**Priority:** Low — cosmetic.

### Issue
- `dashboard_server.py` line 333: `def _load_alerts(limit=50)`
- Display endpoints use `limit=50`, stats fallback uses `limit=1000`
- This is correct behavior but undocumented

### Fix
1. Add a comment above `_load_alerts()` at line 333:
   ```python
   # Display uses limit=50 (last ~4 hours of 5-min cycles).
   # Portfolio stats fallback uses limit=1000 for full history.
   ```
2. No code changes needed — the asymmetry is intentional and correct.

---

## Part 5: Backtest Validation of Phases 29–31 [x]

**Priority:** High — new scoring is live but unvalidated.

### Issue (CORRECTED)
`tools/run_backtest.py` does **NOT** support `--symbol`, `--since`, `--to`, or `--use-phase-XX-rules` flags. It is hardcoded to BTC with last 1000 candles. The CLAUDE.md documents flags that don't exist.

### Steps

1. **Run the backtest as-is** (no flags):
   ```bash
   python tools/run_backtest.py
   ```
   This uses current Phase 29–31 logic. Capture output.

2. **Analyze output** — look for:
   - Total signals generated, A+/B/C tier split
   - Win rate per tier
   - Average R per tier
   - Recipe fire rate (RANGE_BREAKOUT, MOMENTUM_DIVERGENCE, FUNDING_FLUSH, HTF_REVERSAL, BOS_CONTINUATION, VOL_EXPANSION)

3. **Compare to known baseline:**
   - Old A+ (Phase 28, flat rubric): 15 trades, WR=66.7%, AvgR=+0.166
   - If new A+ WR < 55% → weighted thresholds need tuning
   - If new recipes add signals with negative R → disable them in config.py

4. **Write results** to `reports/phase_29_31_backtest.md`

5. **Fix CLAUDE.md line 35** — either:
   - Remove the fake CLI flags from the docs, OR
   - Add argparse to `run_backtest.py` to support `--since` and `--to`
   (Recommend: add argparse since it's useful)

---

## Part 6: Hardening Checklist

### Already Verified (no action needed)
- [x] **JSONL append-only:** `core/infrastructure.py` line 59: `open(self.path, "a")` ✅
- [x] **Dashboard read-only:** dashboard_server.py only reads JSONL ✅
- [x] **SPX_PROXY filter:** `_load_alerts()` lines 345–350 filters `None`, `TEST`, `SYNTHETIC`, `SPX`, `SPX_PROXY` ✅
- [x] **Heartbeat wiring:** dashboard reads `last_cycle.json` (lines 936–958) ✅

### Needs Verification
- [x] **Portfolio JSON concurrency:** `tools/paper_trader.py` uses `path.write_text()` (full overwrite, no locking). If `app.py` and `paper_trader.py` run concurrently, data could be lost. **Fix:** Add `msvcrt.locking()` (Windows) or `fcntl.flock()` (Unix) around writes. Or accept single-writer assumption and document it.
- [x] **Empty JSONL fallback:** If `logs/pid-129-alerts.jsonl` is 0 bytes or missing, does dashboard crash or degrade gracefully? Test: `echo -n > logs/pid-129-alerts.jsonl && python scripts/pid-129/dashboard_server.py`
- [x] **generate_dashboard.py import path:** Verify `scripts/pid-129/` can be imported (hyphen issue). If not, document that subprocess is required.

### New Tests to Add
- [x] `tests/test_dashboard_integration.py`:
  - Write a mock JSONL with 3 alerts
  - Call `_load_alerts()` with that path
  - Assert correct count, filtering, and ordering
- [x] `tests/test_backtest_output.py`:
  - Run backtest in test mode
  - Assert output contains WR, avg R, tier split

---

## Part 7: Implementation Order (for coding agent)

| Step | Task | Files | Est. |
|------|------|-------|------|
| 1 | Fix port docs | `CLAUDE.md`, `OPERATOR.md` | 5 min |
| 2 | Re-enable HTML gen | `app.py` line 417 | 15 min |
| 3 | Document alert cap | `dashboard_server.py` line 333 | 5 min |
| 4 | Verify heartbeat e2e | `app.py --once` + dashboard check | 10 min |
| 5 | Run backtest | `python tools/run_backtest.py` | 30 min |
| 6 | Write backtest report | `reports/phase_29_31_backtest.md` | 15 min |
| 7 | Fix CLAUDE.md backtest flags | `CLAUDE.md` line 35 | 10 min |
| 8 | Portfolio write safety | `tools/paper_trader.py` | 20 min |
| 9 | Add integration test | `tests/test_dashboard_integration.py` | 30 min |

**Total:** ~2.5 hours

**Critical path:** Steps 1–4 (fixes) → Step 5–6 (validation) → Steps 7–9 (hardening)

---

## Part 8: Acceptance Criteria

- [x] `grep -n "8000" CLAUDE.md OPERATOR.md` returns zero matches
- [x] `python app.py --once` regenerates `dashboard.html` (fresh mtime)
- [x] `data/last_cycle.json` has timestamp within last 60 seconds after a cycle
- [x] Backtest report exists at `reports/phase_29_31_backtest.md` with A+/B/C tier stats
- [x] `PYTHONPATH=. python -m pytest tests/test_dashboard_integration.py -v` passes
- [x] CLAUDE.md backtest command matches actual `run_backtest.py` capabilities

---

## Reference: Verified File Locations & Line Numbers

| File | Line | Current State | Action |
|------|------|---------------|--------|
| `CLAUDE.md` | 25 | `http://localhost:8000` | → `8002` |
| `CLAUDE.md` | 35 | Documents `--symbol --since --to` flags | Fix to match reality |
| `OPERATOR.md` | 53 | `http://localhost:8000/api/alerts` | → `8002` |
| `OPERATOR.md` | 55 | `ws://localhost:8000/ws` | → `8002` |
| `app.py` | 417 | `# os.system(f"{sys.executable} scripts/pid-129/generate_dashboard.py")` | Uncomment/replace |
| `app.py` | 430–443 | Writes `data/last_cycle.json` | Verify works |
| `dashboard_server.py` | 22 | `PORT = 8002` | Confirmed correct |
| `dashboard_server.py` | 333 | `def _load_alerts(limit=50)` | Add comment |
| `dashboard_server.py` | 936–958 | Reads `last_cycle.json` | Verify e2e |
| `core/infrastructure.py` | 59 | `open(self.path, "a")` | Confirmed append |
| `scripts/pid-129/generate_dashboard.py` | EOF | `generate_html()` is main function | Import target |
| `tools/run_backtest.py` | all | No argparse, hardcoded BTC | Add flags or fix docs |
| `tools/paper_trader.py` | 71–81 | `path.write_text()` no locking | Add locking |
