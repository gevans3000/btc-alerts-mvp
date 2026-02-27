# Phase 23: Recipe-Aware Execution & Multi-TF Confirmation

**Status:** ✅ DONE  
**Depends on:** Phase 22 (recipes.py, confluence rubric, bot_schema_json — all ✅ DONE)  
**Goal:** Close the gap between what recipes *calculate* and what the dashboard *actually uses*. Right now recipes fire, score points, and produce perfect entry/SL/TP plans — but the final AlertScore ignores all of it and falls back to generic ATR multipliers. This phase wires recipe intelligence directly into execution output and adds multi-timeframe confirmation to eliminate single-TF noise.

---

## 🧩 PROBLEM STATEMENT

### What Phase 22 Built (already working)
- `intelligence/recipes.py` — 3 recipes (HTF_REVERSAL, BOS_CONTINUATION, VOL_EXPANSION)
- 5-Question validation (direction, entry_zone, invalidation, risk_size, targets)
- 6-point Confluence Rubric in `engine.py` (gated at 5/6 for A+, 3/6 for B)
- `core/formatting.py` → `bot_schema_json()` standardized output

### What's Broken / Wasted
1. **Recipe exits are thrown away.** `engine.py` lines 396–416 compute entry/SL/TP from generic ATR multipliers regardless of whether a recipe fired. The recipe's precise `invalidation`, `entry_zone`, and `targets` (from `_five_questions()`) are stored in `intel.recipes` but never used for the final `AlertScore` fields.
2. **No multi-TF confirmation.** Recipes run only on the current timeframe's 5m candles. A BOS_CONTINUATION on 5m means nothing if 1h structure is counter-trend.
3. **Recipe conflicts are unhandled.** If HTF_REVERSAL (bearish) and BOS_CONTINUATION (bullish) fire simultaneously, both get appended — contradicting each other and inflating the score.
4. **SCORE_MULTIPLIER reference bug.** `engine.py` line 295 references `SCORE_MULTIPLIER` before it's defined on line 318. The `locals()` check silently uses a fallback, but this is fragile.

---

## 📋 IMPLEMENTATION TASKS

### Task 1: Wire Recipe Outputs Into AlertScore (`engine.py`)

**File:** `engine.py` — modify the exit-levels block (lines ~396–416)

**Logic:**
```
IF intel.recipes is not empty:
    best_recipe = pick highest-confidence recipe (by raw_score)
    
    # Use recipe's 5-Question answers instead of generic ATR math
    entry_zone  = best_recipe.entry_zone          # e.g. "MARKET" or "LIMIT@96,450"
    invalidation = best_recipe.invalidation        # precise pattern-based stop
    tp1         = best_recipe.targets["tp1"]       # 1:1 RR target
    tp2         = best_recipe.targets["tp2"]       # opposite liquidity target
    risk_size   = best_recipe.risk_size            # 1.0R position size
    
    # Recalculate RR from recipe levels (don't trust generic ATR ratio)
    risk   = abs(last_price - invalidation)
    reward = abs(tp1 - last_price)
    rr     = reward / risk if risk > 0 else 0.0
ELSE:
    # Keep existing ATR-based fallback (no recipe fired)
    [current logic unchanged]
```

**Why:** The entire point of recipes is to produce *better* exits than blind ATR. If we don't use them, the recipe layer is dead weight.

---

### Task 2: Recipe Conflict Resolution (`intelligence/recipes.py`)

**File:** `intelligence/recipes.py` — add function `resolve_conflicts()`

**Logic:**
```python
def resolve_conflicts(signals: List[RecipeSignal]) -> List[RecipeSignal]:
    """
    When multiple recipes fire, resolve contradictions.
    
    Rules:
    1. If LONG and SHORT recipes fire simultaneously → keep NEITHER (cancel).
       Contradictory signals = no edge, sit out.
    2. If multiple same-direction recipes fire → keep highest raw_score only.
       Stacking inflates confidence artificially.
    3. Return at most 1 RecipeSignal.
    """
```

**Wire into `engine.py`:** Call `resolve_conflicts()` after `detect_recipes()` returns, before appending to `intel.recipes`.

**Why:** Two contradictory recipes both adding score = false confidence. The rubric may still pass 4/6 on conflicting data.

---

### Task 3: Multi-Timeframe Recipe Confirmation (`engine.py`)

**File:** `engine.py` — add after recipe detection block (~line 298)

**Logic:**  
The engine already receives `candles_15m` and `candles_1h`. Use them for a lightweight structural check:

```python
def _htf_confirms(recipe_direction: str, candles_htf: List[Candle]) -> bool:
    """
    Check if Higher-Timeframe structure doesn't contradict the recipe.
    
    Not requiring full alignment — just checking for NO active counter-signal.
    - LONG recipe: 1h must NOT have BOS_BEAR or CHOCH_BEAR in last 3 candles
    - SHORT recipe: 1h must NOT have BOS_BULL or CHOCH_BULL in last 3 candles
    
    Returns True if HTF is neutral or aligned. False if actively counter.
    """
```

**Integration:** If `_htf_confirms()` returns False:
- Downgrade recipe contribution by 50% (halve `raw_score` before adding to breakdown)
- Append `"HTF_CONFLICT"` to reason codes
- Do NOT cancel the recipe entirely — let the rubric gate handle final filtering

**Why:** Single-TF recipes without HTF context are the #1 source of false A+ signals. A 5m BOS_CONTINUATION against a 1h bearish trend is a counter-trend scalp at best, not a high-conviction trade.

---

### Task 4: Fix SCORE_MULTIPLIER Reference Order (`engine.py`)

**File:** `engine.py`

**Change:** Move `SCORE_MULTIPLIER = 7.0` to module-level constant (near the imports, or in `config.py`).

```python
# config.py or top of engine.py
SCORE_MULTIPLIER = 7.0
```

Remove the `locals()` check on line 295. Replace with direct reference:
```python
breakdown["momentum"] += sig.raw_score / SCORE_MULTIPLIER
```

**Why:** Eliminates a silent bug. If the constant name ever changes, the fallback silently uses a different value instead of raising an error.

---

### Task 5: Recipe Metadata in Dashboard (`dashboard.html` / `generate_dashboard.py`)

**File:** Dashboard rendering (wherever the alert cards are generated)

**Add to alert card display when a recipe fires:**
- Recipe name badge (e.g., `🔮 HTF_REVERSAL`)
- Recipe-specific entry/SL/TP (not the generic ones)
- Position size suggestion (risk_size from 5-Question)

**Implementation:** The data is already in `AlertScore.intel.recipes[0]` — this is purely a display task. Render the `RecipeSignal` fields in the alert card.

**Why:** If recipes calculate precise levels but the UI shows generic ATR levels, the user sees wrong numbers and loses trust.

---

## ⚙️ EXECUTION ORDER

```
1. Task 4 (SCORE_MULTIPLIER fix)         — 2 min, zero risk
2. Task 2 (conflict resolution)           — new function, no existing code modified
3. Task 3 (HTF confirmation)              — new function + small integration
4. Task 1 (wire recipe exits)             — modifies exit calculation path
5. Task 5 (dashboard display)             — UI only, after data pipeline is correct
```

---

## ✅ VERIFICATION CHECKLIST

- [x] `python -m pytest tests/ -q` — all existing tests pass
- [x] `python app.py --once` — no exceptions, recipes still fire
- [x] When a recipe fires: AlertScore.invalidation matches `RecipeSignal.invalidation` (not ATR fallback)
- [x] When no recipe fires: exit levels unchanged (ATR fallback still works)
- [x] Contradictory recipes (LONG + SHORT simultaneously) produce NO recipe signal
- [x] HTF counter-trend reduces recipe score contribution by 50%
- [x] Dashboard alert card shows recipe name + recipe-specific levels when available
- [x] `bot_schema_json()` output reflects recipe levels (not generic ATR)

---

## 🚫 WHAT THIS PHASE DOES NOT CHANGE

- No new recipes added (3 existing recipes are sufficient)
- No changes to the 6-point rubric categories or thresholds
- No changes to collectors, data sources, or API calls
- No changes to the confidence normalization (SCORE_MULTIPLIER value stays 7.0)
- No removal of any existing functionality

---

_Phase 23 | Recipe-Aware Execution | v23.0_
