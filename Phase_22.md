# Phase 22: Alert Recipe Layer & Confluence Rubric

**Status:** ✅ DONE  
**Goal:** Implement a high-conviction "Recipe" layer that composes raw signals into validated trade plans, and replace the arbitrary confluence count with a weighted 6-point quantitative rubric.

---

## ⚡ IMPLEMENTATION SUMMARY

### 1. New Module: `intelligence/recipes.py`
- **Pattern Composition**: Imports logic from `structure.py`, `sweeps.py`, and `anchored_vwap.py`.
- **Three Core Recipes**:
    - `HTF_REVERSAL`: HTF Level + 5m Sweep + AVWAP Reclaim/Reject.
    - `BOS_CONTINUATION`: BOS + Retest/Hold with rejection wicks.
    - `VOL_EXPANSION`: BB Width bottom 15% + Liquidity Sweep.
- **5-Question Validation Schema**: Every alert calculates:
    - **Direction**: LONG/SHORT.
    - **Entry Zone**: Market if impulse > 1.5x ATR, else Limit at retest.
    - **Invalidation**: Pattern extreme +/- 0.3x ATR.
    - **Risk Size**: Position sizing for 1.0R risk on 1% account.
    - **Targets**: TP1 at 1:1 RR, TP2 at opposite liquidity.

### 2. Weighted Confluence Rubric (`engine.py`)
- **Category-Based Scoring**: Replaced simple code counting with a 6-point rubric:
    1. **Structure**: BOS/CHoCH/Retest alignment.
    2. **Location**: Value Area/Liquidity proximity.
    3. **Anchors**: AVWAP reclaim/reject.
    4. **Derivatives**: Funding/OI/Basis conviction.
    5. **Momentum**: HTF Bias/Flows/Sentiment.
    6. **Volatility**: Squeeze/BB Compression.
- **Selective Gating**: `A+ TRADE` signals now require a minimum **4/6 rubric score**.

### 3. Standardized Bot Output (`core/formatting.py`)
- **`bot_schema_json`**: New function to produce standardized JSON objects for execution bots.
- **Schema Fields**: `type`, `setup_conditions`, `risk_rules`, `execution_details`.

---

## ✅ VERIFICATION RESULTS

- [x] **Recipes firing**: Verified via `app.py --once`.
- [x] **Rubric selectivity**: A+ alerts now correctly gated by the 4/6 threshold.
- [x] **Risk calculations**: 5-Question schema producing realistic Position Size and TP/SL levels.
- [x] **Tests passed**: All 34+ unit tests remain green.

---
_Phase 22 | Principal Quant Dev | v22.0_
