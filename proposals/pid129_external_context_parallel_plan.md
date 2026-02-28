# PID-129: External Context Layer (Parallel, Non-UI Upgrade)

## Why this proposal
The current dashboard is a strong signal surface, but profitable BTC execution usually needs additional context outside internal technical signals.

This plan adds **optional, non-breaking modules** for:
1. Fundamental/news catalysts
2. Sentiment/social context
3. Advanced technical confirmation
4. Forward-looking risk/execution rules
5. Personal portfolio constraints

The dashboard look-and-feel remains unchanged.

---

## Design constraints
- **No dashboard redesign**.
- **Feature-flagged** and default-off until validated.
- **Read-only ingestion first** (no automatic trading actions).
- **Fail-safe behavior:** if new data is missing/stale, system falls back to current logic.

Suggested flags in `config.py`:
- `ENABLE_EXTERNAL_NEWS = False`
- `ENABLE_SENTIMENT_LAYER = False`
- `ENABLE_MTF_CONFIRMATION = False`
- `ENABLE_RISK_SCENARIO_ENGINE = False`
- `ENABLE_PORTFOLIO_GUARDRAILS = False`

---

## Parallel workstreams (can be built independently)

### Track A — Fundamental + News event stream
**Goal:** Add macro/event context without blocking current alerts.

Implementation path:
- New module: `intelligence/fundamentals.py`
- New collector adapter(s): `collectors/news.py` (provider-agnostic interface)
- Normalize events into a compact schema:
  - `event_type` (macro, geopolitics, regulation, ETF_flow, onchain_flow)
  - `severity` (0-100)
  - `directional_bias` (bullish, bearish, neutral)
  - `ttl_minutes`
- Add to engine as a bounded score modifier (example ±8 max on confidence).

Acceptance criteria:
- If provider fails, current alert engine behavior is unchanged.
- News context appears in reports/log fields, not as hard dependency.

---

### Track B — Sentiment + social indicators
**Goal:** Add crowd/positioning context for faster regime awareness.

Implementation path:
- New module: `intelligence/sentiment_ext.py`
- Extend existing `intelligence/sentiment.py` with optional external inputs:
  - Fear/Greed bucket
  - Social trend score (keyword momentum)
  - Options IV stress bucket
- Produce one fused metric: `sentiment_regime` (risk_on, mixed, risk_off)

Acceptance criteria:
- Sentiment layer runs independently and can be toggled off.
- Output is explainable in alert rationale text.

---

### Track C — Multi-timeframe + on-chain confirmation
**Goal:** Reduce false positives from single-frame setups.

Implementation path:
- New module: `intelligence/mtf_confirmation.py`
- Confirm lower-timeframe setup against daily/weekly trend state and key levels.
- Optional on-chain proxy input hooks (e.g., whale transfer pressure, holder behavior).
- Expose confirmation state as `confirm`, `neutral`, or `conflict`.

Acceptance criteria:
- Existing signal generation continues if MTF data is absent.
- Confluence output clearly marks when higher timeframe conflicts.

---

### Track D — Risk scenario engine (forward-looking)
**Goal:** Add strict controls before/while generating trade plans.

Implementation path:
- New module: `intelligence/risk_scenarios.py`
- Add reusable functions:
  - volatility-adjusted position sizing cap (1-2% risk budget default)
  - stop/TP templates by regime
  - geopolitical/inflation scenario map with directional playbooks
- Integrate with `intelligence/auto_rr.py` and/or `engine.py` as a guardrail layer.

Acceptance criteria:
- Trade plan always includes explicit invalidation and scenario tag.
- If risk module unavailable, current TP/SL path is used.

---

### Track E — Personal portfolio guardrails
**Goal:** Keep signal quality aligned with user capital constraints.

Implementation path:
- New module: `tools/portfolio_guardrails.py`
- Add constraints:
  - max leverage and max concurrent positions
  - BTC correlation awareness (gold/SPX proxy)
  - per-day risk budget cap
- Persist guardrail decisions in trade journal output.

Acceptance criteria:
- Guardrails never mutate historical signal logic.
- Blocking decisions are logged with reason codes.

---

## Minimal merge strategy (least actions)
Use a single integration branch and merge parallel tracks via small PRs:
1. Branches from `main`:
   - `feat/pid129-track-a-news`
   - `feat/pid129-track-b-sentiment`
   - `feat/pid129-track-c-mtf`
   - `feat/pid129-track-d-risk`
   - `feat/pid129-track-e-portfolio`
2. Merge order: A, B, C, D, E (each behind flags).
3. Final step: enable one flag at a time in paper mode and monitor outcomes.

---

## Notes on the market-context examples
The frequently cited conditions (e.g., elevated volatility, fear extremes, macro/geopolitical shock risk, ETF flow pressure) should be treated as **dynamic inputs** and ingested from live sources rather than hardcoded into strategy logic.

---

## Definition of done
- No visual dashboard changes.
- All new layers optional via config flags.
- Engine behavior is unchanged when flags are off.
- Added rationale fields in logs/reports for explainability.
