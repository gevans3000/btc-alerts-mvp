# v4 Action Plan Progress

## Part 1: DATA LAYERS (Phases 1-3)
- [x] **Phase 1: Volume Profile / POC**
  - [x] IntelligenceBundle field added
  - [x] Config added
  - [x] `intelligence/volume_profile.py` created
  - [x] Wired into `engine.py`
  - [x] Wired into `app.py`
  - [x] Formatting added
  - [x] Tests passed (`tests/test_volume_profile.py`)
- [x] **Phase 2: Liquidity Walls**
  - [x] IntelligenceBundle field added
  - [x] Config added
  - [x] `intelligence/liquidity.py` created
  - [x] Wired into `engine.py`
  - [x] Wired into `app.py`
  - [x] Formatting added
  - [x] Tests passed (`tests/test_liquidity.py`)
- [x] **Phase 3: Macro Correlation**
  - [x] IntelligenceBundle field added
  - [x] Config added
  - [x] `intelligence/macro_correlation.py` created
  - [x] Wired into `engine.py`
  - [x] Wired into `app.py`
  - [x] Formatting added
  - [x] Tests passed (`tests/test_macro_correlation.py`)

## Part 2: INTEGRATION (Phases 4-5)
- [x] **Phase 4: Confluence Heatmap**
  - [x] `intelligence/confluence.py` created
  - [x] Wired into `engine.py`
  - [x] Wired into `config.py`
  - [x] Formatting added
  - [x] Tests passed (`tests/test_confluence.py`)
- [x] **Phase 5: Dashboard Upgrade**
  - [x] Modified `scripts/pid-129/generate_dashboard.py` to include Intel Layers
  - [x] Updated `core/infrastructure.py` to persist `decision_trace`
  - [x] Verify data population in `dashboard.html`

## Part 3: CALIBRATION & VALIDATION (Phases 6-8)
- [x] **Phase 6: Score Recalibration**
  - [x] Updated `TIMEFRAME_RULES` in `config.py`
  - [x] Updated `CONFLUENCE_RULES` in `config.py`
  - [x] Verified system still fires alerts (A+/B)
- [x] **Phase 7: Historical Backtest**
  - [x] Created `tools/backtest.py`
  - [x] Fixed `DerivativesSnapshot` and `FlowSnapshot` dummies
  - [x] Successfully ran backtest and generated CSV
- [x] **Phase 8: Observability**
  - [x] Added loggers to all new intelligence modules
  - [x] Added cycle timing to `app.py`
  - [x] Added health summary to `app.py`
  - [x] Verified timing/health logs in smoke test (app.py --once)

**✅ Action Plan v4 Complete.**

