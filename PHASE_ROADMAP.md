# BTC Alerts MVP — Phase Roadmap for AI Agents

**Project:** PID-129 — EMBER Progressive Capability Loop
**Current State:** v1.1 Production-Ready (OpenClaw-aligned)
**Last Updated:** 2026-02-16

---

## Phase 0: Foundation & Governance ✅ DONE

**Status:** Complete
**Owner:** EMBER (PID-129)
**Duration:** 2-hour cycle

### Deliverables
- ✅ OpenClaw governance contract (GOVERNANCE.md)
- ✅ Systemd services (main + watchdog)
- ✅ Health check script (healthcheck.sh)
- ✅ Daily scorecard generator (generate_scorecard.py)
- ✅ Remote operations documentation
- ✅ Failure & outcome matrix
- ✅ Alert schema (JSONL)
- ✅ Test gates (T1–T10)

### Evidence
- Path: `GOVERNANCE.md`, `scripts/pid-129/healthcheck.sh`, `reports/pid-129-daily-scorecard.md`

---

## Phase 1: Core Signal Quality Improvements 🎯 NEXT

**Status:** Ready for AI Agent Execution
**Estimated Duration:** 2–4 hours
**Priority:** HIGH

### Objective
Improve signal quality by implementing missing technical indicators and enhancing existing logic.

### Sub-Phases

#### Phase 1A: Advanced Technical Indicators
- **What:** Add missing indicators identified in IMPLEMENTATION_PLAN.md
  - RSI Divergence Detection (already in utils.py, verify correctness)
  - Candle Patterns (Engulfing/Pin Bars) - verify implementation
  - Volume Delta (already in utils.py, verify correctness)
  - Swing Support/Resistance Levels (already in utils.py, verify correctness)
  - Confluence Gating (verify session weights and VIX bias)

- **How:**
  - Run comprehensive test suite: `python tests/test_utils_engine.py`
  - Manually test indicator outputs with historical candles
  - Compare signal quality before/after improvements

- **Deliverables:**
  - Updated utils.py with verified implementations
  - Test results documenting improved signal quality
  - Updated IMPLEMENTATION_PLAN.md with confirmed changes

- **Success Criteria:**
  - All indicators pass existing tests
  - Signal quality metrics improve by ≥15%
  - No new false positives introduced

#### Phase 1B: Enhanced Market Regime Classification
- **What:** Improve regime detection accuracy
  - Better ADX + ATR threshold tuning
  - Improve trend detection (EMA crossover improvements)
  - Enhance range vs volatility-chop discrimination

- **How:**
  - Review regime detection logic in engine.py
  - Tune thresholds in config.py based on historical performance
  - Add regime confidence scoring

- **Deliverables:**
  - Updated regime detection functions
  - Regime quality report (accuracy, precision, recall)
  - Updated config.py with new thresholds

- **Success Criteria:**
  - Regime classification accuracy improves by ≥10%
  - Reduced regime confusion (less switching between trend/range)

#### Phase 1C: Better Trade Plan Accuracy
- **What:** Improve entry, TP/SL precision
  - Better invalidation levels (use S/R levels more aggressively)
  - Dynamic TP/SL multipliers based on volatility regime
  - More accurate entry zones (tighten range)

- **How:**
  - Review swing levels usage in engine.py
  - Tune TP_MULTIPLIERS in config.py
  - Add confidence-based entry zone tightening

- **Deliverables:**
  - Improved entry zone logic
  - Updated TP/SL calculation
  - Trade plan accuracy report (hit rate, R multiple accuracy)

- **Success Criteria:**
  - Trade plan accuracy improves by ≥20%
  - Lower average R multiple variance

---

## Phase 2: Operational Excellence 🚀

**Status:** Ready for AI Agent Execution
**Estimated Duration:** 2 hours
**Priority:** HIGH

### Objective
Make the system more reliable, observable, and maintainable.

### Sub-Phases

#### Phase 2A: Comprehensive Logging & Observability
- **What:** Add structured logging throughout the stack
  - Request/response logging for all API calls
  - Alert decision trace logging (why an alert was generated)
  - Score breakdown logging (what contributed to the final score)
  - Error stack traces with context

- **How:**
  - Add structured logging to app.py, engine.py, collectors/
  - Log format: JSON with timestamps, log levels, correlation IDs
  - Log volume management (log rotation, compression)

- **Deliverables:**
  - Structured logs in all modules
  - Centralized logging configuration
  - Log analysis tools (grep, jq queries)

- **Success Criteria:**
  - All critical events logged with context
  - Log volume stays under 10MB/day (manageable)
  - Debugging an alert takes ≤5 minutes with logs

#### Phase 2B: Alert History & Replay
- **What:** Full alert history with replay capability
  - Persistent JSONL storage of all alerts
  - Replay tool that can play back alerts on historical data
  - Alert outcome tracking (TP hit, SL hit, breakeven, none)

- **How:**
  - Improve alert schema (add outcome tracking)
  - Add replay.py tool from IMPLEMENTATION_PLAN.md
  - Add outcome tracking to app.py (track TP1/SL hits)

- **Deliverables:**
  - Alert history storage (logs/pid-129-alerts.jsonl with outcomes)
  - Replay tool (`tools/replay_alerts.py`)
  - Outcome tracking metrics

- **Success Criteria:**
  - All alerts have outcomes tracked
  - Replay tool works on last 30 days of alerts
  - Win rate and average R can be calculated from history

#### Phase 2C: Test Suite Expansion
- **What:** Comprehensive test coverage
  - Unit tests for all utility functions
  - Integration tests for engine scoring
  - End-to-end tests for alert generation
  - Regression tests for known issues

- **How:**
  - Expand tests/test_utils_engine.py
  - Add tests/test_engine_scoring.py
  - Add tests/test_alert_pipeline.py

- **Deliverables:**
  - ≥80% test coverage for core logic
  - CI/CD pipeline (optional)
  - Test documentation

- **Success Criteria:**
  - All tests pass on every change
  - Test suite runs in <60 seconds
  - New features require test updates before merge

---

## Phase 3: Advanced Features (Optional) 🌟

**Status:** Backlog
**Estimated Duration:** 4–6 hours per feature
**Priority:** MEDIUM

### Sub-Phases

#### Phase 3A: Multiple Exchange Aggregation
- **What:** Aggregate signals from multiple exchanges
  - Fetch BTC data from Kraken, Bybit, OKX
  - Aggregate scores (voting mechanism)
  - Handle data discrepancies gracefully

- **How:**
  - Add exchange list to config
  - Create exchange manager in collectors/
  - Implement voting logic in engine.py

- **Deliverables:**
  - Multi-exchange aggregator
  - Confidence from exchange consensus
  - Exchange quality scoring

- **Success Criteria:**
  - Consensus alerts have higher confidence
  - Exchange disagreement detected and logged

#### Phase 3B: Machine Learning Signal Enhancement
- **What:** Use ML to improve signal quality
  - Train model on historical alerts + outcomes
  - Predict alert accuracy before generation
  - Adjust thresholds dynamically

- **How:**
  - Collect labeled dataset (alert → outcome)
  - Train simple model (XGBoost or Random Forest)
  - Integrate into scoring pipeline

- **Deliverables:**
  - ML model for accuracy prediction
  - Model evaluation report
  - Integration into engine.py

- **Success Criteria:**
  - ML improves prediction accuracy by ≥15%
  - Model retraining pipeline (monthly)

#### Phase 3C: Paper Trading Simulation
- **What:** Realistic paper trading environment
  - Simulate trades based on alerts
  - Track P&L, win rate, max drawdown
  - Compare against actual alerts over time

- **How:**
  - Create paper trading account in app.py
  - Add trade execution logic
  - Generate performance reports

- **Deliverables:**
  - Paper trading engine
  - Performance dashboard
  - Trade journal

- **Success Criteria:**
  - Paper trading matches live alerts 1:1
  - Win rate tracks live performance over time

---

## Phase 4: Production Hardening 🔒

**Status:** Backlog
**Estimated Duration:** 2 hours
**Priority:** HIGH (if moving to production)

### Sub-Phases

#### Phase 4A: Security Hardening
- **What:** Secure credentials and API access
  - Environment variable management
  - API key rotation
  - Rate limit protection

- **How:**
  - Use .env file for secrets
  - Add rate limiting to API calls
  - Implement key rotation schedule

- **Deliverables:**
  - Secure credential management
  - Rate limiting in place
  - Security audit report

- **Success Criteria:**
  - No secrets in logs
  - API rate limits respected
  - Security audit passes

#### Phase 4B: Reliability Improvements
- **What:** Make system more robust
  - Better error handling
  - Graceful degradation
  - Circuit breakers for failing APIs

- **How:**
  - Add circuit breakers in collectors/
  - Improve error messages
  - Add fallback providers

- **Deliverables:**
  - Circuit breaker implementation
  - Better error handling
  - Fallback strategies

- **Success Criteria:**
  - System degrades gracefully on failures
  - No cascading failures
  - All critical paths have fallbacks

#### Phase 4C: Performance Optimization
- **What:** Improve performance
  - Reduce API calls
  - Optimize computation
  - Cache results

- **How:**
  - Implement caching for market data
  - Optimize indicator calculations
  - Reduce redundant calculations

- **Deliverables:**
  - Cache implementation
  - Performance benchmarks
  - Optimization report

- **Success Criteria:**
  - Cycle time reduced by ≥30%
  - API calls reduced by ≥20%
  - No quality degradation

---

## Execution Guidelines for AI Agents

### Workflow
1. **Read Governance.md** — Understand PID-129 scope and OpenClaw patterns
2. **Review Current State** — Check logs, scorecards, and recent alerts
3. **Plan 2-Hour Improvement** — Pick ONE sub-phase from above
4. **Execute** — Make changes, run tests
5. **Evaluate** — Compare before/after metrics
6. **Document** — Update scorecard, logs, and governance
7. **Report** — Emit strict output contract (STATUS, IMPROVEMENT, DELTA, GRADE, NEXT_STEP, EVIDENCE)

### Success Criteria
- One concrete improvement completed per cycle
- No breaking changes
- Tests pass
- Evidence documented
- Output follows strict contract

### Safety Rules
- Never delete code without explicit approval
- Never change configuration without testing
- Always run tests before committing
- Always document changes

---

## References

- **Governance:** `GOVERNANCE.md`
- **Current Code:** `app.py`, `engine.py`, `config.py`, `utils.py`, `collectors/`
- **Implementation Plan:** `IMPLEMENTATION_PLAN.md` (v1.1)
- **Agent Playbook:** `OpenClaw_Effective_Agents_Playbook_PLUS.md`
- **PID-129 Charter:** `clawd/ops/pid-129-status.md`
- **Daily Scorecard:** `reports/pid-129-daily-scorecard.md`

---

**Next Phase:** Phase 1 (Core Signal Quality Improvements)
**Next AI Agent:** EMBER (PID-129)
