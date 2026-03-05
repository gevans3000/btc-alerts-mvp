# EMBER COMMAND: Phases 29–31 & Hardening (COMPLETED)

**Status:** ALL PHASES VERIFIED AND COMPLETE.
**Date of Completion:** 2026-03-05

This document serves as the single source of truth, combining the objectives and completion status from both `PHASE_ROADMAP_2.md` and `PHASE_roadmap_finalize.md`.

## 1. Core Signal Updates (Phases 29-31)
- **Phase 29 (Weighted Confluence & B-Tier Demotion):** Rubric shifted to prioritize Structure=2.0 and Location=1.5. A+ requires 6.0+, B tier 4.0+, and C tier 2.5+. B-tier alerts demoted to grey C-tier, leaving only the highest-probability alerts as actionable.
- **Phase 30 (Recipe Expansion):** Implemented three new high-conviction recipes: `RANGE_BREAKOUT`, `MOMENTUM_DIVERGENCE`, and `FUNDING_FLUSH`.
- **Phase 31 (HTF Cascade Scoring & Directional Seasoning):** Multi-timeframe trend alignment provides gradient scoring (+3/+2/+1). Extremes in funding and taker ratio skew thresholds to effectively fade the crowded side.

## 2. Dashboard & Integration Hardening (Finalization)
- **Port Matching:** Fixed all documentation (`CLAUDE.md`, `OPERATOR.md`) to align with `dashboard_server.py`'s true port (8002).
- **Auto-Generation:** Re-wired `app.py` to seamlessly auto-generate the dashboard HTML upon new alerts via internal script imports.
- **Heartbeat E2E:** Verified dashboard consumes `last_cycle.json` for live UI heartbeat monitoring.
- **Alert Caps:** Documented the intentional asymmetry in `_load_alerts()` (50-alert limits for display vs. 1000 for backend portfolio stats).
- **Concurrency & Flat-file IPC:** Addressed concurrent JSONL writes, ensured safe `paper_trader.py` JSON data handling, and verified read-only frontend data streams.
- **Backtest Validation:** Updated `tools/run_backtest.py` documentation and outputs to validate A+/B/C tier statistical edge. Tests created and passing.

## Current Truth Summary
There is **NO** outstanding work required for Phases 29 through 31, nor for the dashboard server flat-file IPC hardening. The system is live, tested, and actively filtering A+ trades while reliably pushing updates to the dashboard at port `8002`.
