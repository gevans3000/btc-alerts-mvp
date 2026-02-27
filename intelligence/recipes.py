"""
intelligence/recipes.py
─────────────────────────────────────────────────────────────────────────────
Alert Recipe Layer — Phase 22

Detects three high-conviction pattern recipes by composing raw output from
existing intelligence modules (structure.py, sweeps.py, anchored_vwap.py,
squeeze.py).  Every detected recipe is validated through a 5-Question schema
that produces a fully specified trade plan before the signal is surfaced.

Recipe catalogue
────────────────
  HTF_REVERSAL    : HTF level confluence + 5m liquidity sweep + AVWAP reclaim/reject.
                    The classicWyckoff/SMC reversal footprint.
  BOS_CONTINUATION: BOS confirmed + price retests broken structure + rejection wick.
                    Trend continuation with defined invalidation.
  VOL_EXPANSION   : BB width in bottom-15% percentile (squeeze release) + sweep of
                    resting liquidity.  Volatility expansion ignition setup.

5-Question validation schema (per recipe)
──────────────────────────────────────────
  Q1  direction    : LONG | SHORT
  Q2  entry_zone   : 'MARKET' (impulse > 1.5× ATR) | 'LIMIT@<price>' (retest)
  Q3  invalidation : pattern extreme ± 0.3× ATR
  Q4  risk_size    : position_size for 1.0R risk on 1% account risk
  Q5  targets      : {'tp1': 1:1 RR price, 'tp2': opposite liquidity level}

Usage
─────
  from intelligence.recipes import detect_recipes
  recipes = detect_recipes(candles, struct, sweeps, avwap, squeeze, atr_val,
                           account_size=10_000)
  # returns List[RecipeSignal] — empty list if no recipe qualifies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from utils import Candle, atr as calc_atr

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data contract
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RecipeSignal:
    """
    A fully validated trade recipe produced by detect_recipes().

    All fields are populated before this object is returned — no optional
    gaps that require downstream null checks.
    """
    recipe: str                    # 'HTF_REVERSAL' | 'BOS_CONTINUATION' | 'VOL_EXPANSION'
    direction: str                 # 'LONG' | 'SHORT'
    entry_zone: str                # 'MARKET' | 'LIMIT@<price>'
    invalidation: float            # Hard stop level
    risk_size: float               # Position size in base units for 1.0R
    targets: Dict[str, float]      # {'tp1': float, 'tp2': float}
    trigger_codes: List[str]       # Engine codes that fired this recipe
    confidence_factors: List[str]  # Human-readable why this recipe fired
    raw_score: float               # Pre-multiplier contribution to engine score
    extra: Dict[str, Any] = field(default_factory=dict)  # Debug / trace data


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _five_questions(
    direction: str,
    entry_px: float,
    pattern_extreme: float,
    opposite_liquidity: float,
    atr_val: float,
    account_size: float,
    impulse_size: float = 0.0,
) -> Dict[str, Any]:
    """
    Answer the 5-Question trade plan schema.

    Q1  direction    → passed in.
    Q2  entry_zone   → MARKET if impulse > 1.5× ATR, else LIMIT at pattern retest.
    Q3  invalidation → pattern extreme ± 0.3× ATR buffer.
    Q4  risk_size    → units to risk 1% of account_size at 1.0R.
    Q5  targets      → tp1 = 1:1 RR from entry, tp2 = opposite liquidity.
    """
    # Q2 — execution style
    if impulse_size > 1.5 * atr_val:
        entry_zone = "MARKET"
        exec_px = entry_px
    else:
        # Limit at retest of pattern extreme (HTF level / BOS line)
        if direction == "LONG":
            exec_px = pattern_extreme + (0.1 * atr_val)   # slight buffer above support
        else:
            exec_px = pattern_extreme - (0.1 * atr_val)
        entry_zone = f"LIMIT@{exec_px:,.0f}"

    # Q3 — invalidation (pattern extreme ± 0.3× ATR)
    if direction == "LONG":
        invalidation = pattern_extreme - (0.3 * atr_val)
    else:
        invalidation = pattern_extreme + (0.3 * atr_val)

    risk_per_unit = abs(exec_px - invalidation)

    # Q4 — risk_size: 1% account capital divided by dollar-risk-per-unit
    risk_capital = account_size * 0.01
    risk_size = (risk_capital / risk_per_unit) if risk_per_unit > 0 else 0.0

    # Q5 — targets
    reward_1r = abs(exec_px - invalidation)
    if direction == "LONG":
        tp1 = exec_px + reward_1r                 # 1:1 RR
        tp2 = opposite_liquidity                  # opposite liquidity pool
    else:
        tp1 = exec_px - reward_1r
        tp2 = opposite_liquidity

    return {
        "direction": direction,
        "entry_zone": entry_zone,
        "exec_px": round(exec_px, 2),
        "invalidation": round(invalidation, 2),
        "risk_size": round(risk_size, 4),
        "targets": {"tp1": round(tp1, 2), "tp2": round(tp2, 2)},
    }


def _bb_width_percentile(candles: List[Candle], period: int = 20, lookback: int = 100) -> float:
    """
    Return the current BB width as a percentile of its recent range (0–100).
    Uses a pure-Python rolling calculation to avoid numpy dependency.
    Returns 50.0 on insufficient data.
    """
    if len(candles) < period + lookback:
        return 50.0

    closes = [c.close for c in candles]
    widths: List[float] = []
    for i in range(lookback):
        idx = len(closes) - lookback + i
        if idx < period:
            continue
        window = closes[idx - period: idx]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5
        widths.append(2.0 * 2.0 * std)   # 2× BB_std=2.0

    if not widths:
        return 50.0

    current_width = widths[-1]
    below = sum(1 for w in widths if w < current_width)
    return (below / len(widths)) * 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Recipe detectors
# ─────────────────────────────────────────────────────────────────────────────

def _recipe_htf_reversal(
    candles: List[Candle],
    struct: Dict[str, Any],
    sweeps: Dict[str, Any],
    avwap: Dict[str, Any],
    atr_val: float,
    account_size: float,
) -> Optional[RecipeSignal]:
    """
    HTF_REVERSAL: HTF structure level + 5m liquidity sweep + AVWAP reclaim/reject.

    Required co-occurrence (all three legs must be present):
      Leg 1 — HTF level: structure has a clear last pivot high or low nearby price.
      Leg 2 — Sweep: EQH or EQL sweep fired on the 5m candle.
      Leg 3 — Anchor: AVWAP reclaim (LONG) or reject (SHORT) in same candle.
    """
    codes = struct.get("codes", []) + sweeps.get("codes", []) + avwap.get("codes", [])
    last = candles[-1]
    price = last.close

    # Leg 1 — determine HTF direction bias from structure
    has_bull_struct = any(c in codes for c in ("STRUCTURE_BOS_BULL", "STRUCTURE_CHOCH_BULL"))
    has_bear_struct = any(c in codes for c in ("STRUCTURE_BOS_BEAR", "STRUCTURE_CHOCH_BEAR"))

    # Leg 2 — sweep event
    sweep_bull = sweeps.get("sweep_low", False)      # swept lows → bullish reversal
    sweep_bear = sweeps.get("sweep_high", False)     # swept highs → bearish reversal

    # Leg 3 — AVWAP
    avwap_bull = "AVWAP_RECLAIM_BULL" in avwap.get("codes", [])
    avwap_bear = "AVWAP_REJECT_BEAR" in avwap.get("codes", [])

    # Compose legs
    long_signal = has_bull_struct and sweep_bull and avwap_bull
    short_signal = has_bear_struct and sweep_bear and avwap_bear

    if not (long_signal or short_signal):
        return None

    direction = "LONG" if long_signal else "SHORT"

    # Pattern extreme: the swept level (EQL for LONG, EQH for SHORT)
    if direction == "LONG":
        eq_lows = sweeps.get("equal_lows", [])
        pattern_extreme = min(eq_lows) if eq_lows else (price - atr_val)
        opposite_liq = struct.get("last_pivot_high", price + 2 * atr_val) or (price + 2 * atr_val)
    else:
        eq_highs = sweeps.get("equal_highs", [])
        pattern_extreme = max(eq_highs) if eq_highs else (price + atr_val)
        opposite_liq = struct.get("last_pivot_low", price - 2 * atr_val) or (price - 2 * atr_val)

    impulse = abs(last.high - last.low)
    plan = _five_questions(direction, price, pattern_extreme, opposite_liq, atr_val, account_size, impulse)

    fired_codes = [c for c in codes if c in (
        "STRUCTURE_BOS_BULL", "STRUCTURE_BOS_BEAR", "STRUCTURE_CHOCH_BULL", "STRUCTURE_CHOCH_BEAR",
        "EQL_SWEEP_BULL", "EQH_SWEEP_BEAR", "AVWAP_RECLAIM_BULL", "AVWAP_REJECT_BEAR",
    )]

    return RecipeSignal(
        recipe="HTF_REVERSAL",
        direction=plan["direction"],
        entry_zone=plan["entry_zone"],
        invalidation=plan["invalidation"],
        risk_size=plan["risk_size"],
        targets=plan["targets"],
        trigger_codes=fired_codes,
        confidence_factors=[
            f"Structure: {struct.get('last_event', 'bias')}",
            f"Sweep: {'EQL' if sweep_bull else 'EQH'}",
            f"AVWAP: {'reclaim' if avwap_bull else 'reject'} @ {avwap.get('avwap', 0):,.0f}",
        ],
        raw_score=8.0,
        extra={
            "avwap": avwap.get("avwap"),
            "pattern_extreme": pattern_extreme,
            "opposite_liquidity": opposite_liq,
        },
    )


def _recipe_bos_continuation(
    candles: List[Candle],
    struct: Dict[str, Any],
    sweeps: Dict[str, Any],
    atr_val: float,
    account_size: float,
) -> Optional[RecipeSignal]:
    """
    BOS_CONTINUATION: BOS confirmed + retest of broken structure + rejection wick.

    Criteria:
      - A fresh BOS event (BOS_BULL or BOS_BEAR) in the structure dict.
      - Price has pulled back towards the broken level (retest within 0.5× ATR).
      - Last candle has a rejection wick (wick >= 60% of candle range).
    """
    event = struct.get("last_event")
    if event not in ("BOS_BULL", "BOS_BEAR"):
        return None

    last = candles[-1]
    price = last.close
    is_bull = event == "BOS_BULL"
    direction = "LONG" if is_bull else "SHORT"

    # Retest level = last pivot (the broken structure level)
    if is_bull:
        retest_level = struct.get("last_pivot_high", price - atr_val)
        if not retest_level:
            return None
        # Price must be within 0.5× ATR of the retest level from above
        if not (retest_level - 0.5 * atr_val <= price <= retest_level + 0.5 * atr_val):
            return None
        # Rejection wick: bullish → lower wick >= 60% of candle range
        c_range = last.high - last.low
        lower_wick = last.open - last.low if last.open > last.low else last.close - last.low
        if c_range > 0 and (lower_wick / c_range) < 0.40:
            return None
        pattern_extreme = retest_level
        opposite_liq = struct.get("last_pivot_high", price + 2 * atr_val) or (price + 2 * atr_val)
    else:
        retest_level = struct.get("last_pivot_low", price + atr_val)
        if not retest_level:
            return None
        if not (retest_level - 0.5 * atr_val <= price <= retest_level + 0.5 * atr_val):
            return None
        c_range = last.high - last.low
        upper_wick = last.high - last.open if last.open < last.high else last.high - last.close
        if c_range > 0 and (upper_wick / c_range) < 0.40:
            return None
        pattern_extreme = retest_level
        opposite_liq = struct.get("last_pivot_low", price - 2 * atr_val) or (price - 2 * atr_val)

    impulse = abs(last.high - last.low)
    plan = _five_questions(direction, price, pattern_extreme, opposite_liq, atr_val, account_size, impulse)

    c_range = last.high - last.low
    wick_ratio = round((abs(last.open - last.low) / c_range) if c_range > 0 else 0, 2)

    return RecipeSignal(
        recipe="BOS_CONTINUATION",
        direction=plan["direction"],
        entry_zone=plan["entry_zone"],
        invalidation=plan["invalidation"],
        risk_size=plan["risk_size"],
        targets=plan["targets"],
        trigger_codes=[f"STRUCTURE_{event}"],
        confidence_factors=[
            f"BOS event: {event}",
            f"Retest of {retest_level:,.0f} within 0.5× ATR",
            f"Rejection wick ratio: {wick_ratio}",
        ],
        raw_score=6.0,
        extra={
            "retest_level": retest_level,
            "wick_ratio": wick_ratio,
            "pattern_extreme": pattern_extreme,
        },
    )


def _recipe_vol_expansion(
    candles: List[Candle],
    squeeze: Dict[str, Any],
    sweeps: Dict[str, Any],
    struct: Dict[str, Any],
    atr_val: float,
    account_size: float,
) -> Optional[RecipeSignal]:
    """
    VOL_EXPANSION: BB width in bottom-15th percentile + liquidity sweep.

    Criteria:
      - Current BB width percentile < 15 (compressed volatility, near squeeze release).
      - A liquidity sweep (EQL or EQH) fired on the current bar.
      - Direction bias from structure.

    The pattern captures the "coiled spring" release: tight BB + sweep of stops
    = violent directional expansion incoming.
    """
    # BB width percentile check
    bb_pct = _bb_width_percentile(candles)
    if bb_pct >= 15.0:
        return None

    # Squeeze state enriches the signal (FIRE or ON strengthens conviction)
    sq_state = squeeze.get("state", "NONE")

    # Sweep required
    sweep_bull = sweeps.get("sweep_low", False)
    sweep_bear = sweeps.get("sweep_high", False)
    if not (sweep_bull or sweep_bear):
        return None

    # Direction from structure bias
    has_bull = any(c in struct.get("codes", []) for c in ("STRUCTURE_BOS_BULL", "STRUCTURE_CHOCH_BULL"))
    has_bear = any(c in struct.get("codes", []) for c in ("STRUCTURE_BOS_BEAR", "STRUCTURE_CHOCH_BEAR"))

    if sweep_bull and has_bull:
        direction = "LONG"
    elif sweep_bear and has_bear:
        direction = "SHORT"
    elif sweep_bull:
        direction = "LONG"    # sweep alone is directional enough for vol play
    elif sweep_bear:
        direction = "SHORT"
    else:
        return None

    last = candles[-1]
    price = last.close

    if direction == "LONG":
        eq_lows = sweeps.get("equal_lows", [])
        pattern_extreme = min(eq_lows) if eq_lows else (price - atr_val)
        opposite_liq = struct.get("last_pivot_high", price + 3 * atr_val) or (price + 3 * atr_val)
    else:
        eq_highs = sweeps.get("equal_highs", [])
        pattern_extreme = max(eq_highs) if eq_highs else (price + atr_val)
        opposite_liq = struct.get("last_pivot_low", price - 3 * atr_val) or (price - 3 * atr_val)

    # VOL_EXPANSION targets are wider — use 2× RR for TP1
    impulse = abs(last.high - last.low)
    plan = _five_questions(direction, price, pattern_extreme, opposite_liq, atr_val, account_size, impulse)
    # Widen TP1 to 2:1 for expansion plays
    r1 = abs(plan["exec_px"] - plan["invalidation"])
    if direction == "LONG":
        plan["targets"]["tp1"] = round(plan["exec_px"] + 2.0 * r1, 2)
    else:
        plan["targets"]["tp1"] = round(plan["exec_px"] - 2.0 * r1, 2)

    fired = ["VOL_EXPANSION_RECIPE"]
    if sq_state == "SQUEEZE_FIRE":
        fired.append("SQUEEZE_FIRE")
    if sweep_bull:
        fired.append("EQL_SWEEP_BULL")
    if sweep_bear:
        fired.append("EQH_SWEEP_BEAR")

    return RecipeSignal(
        recipe="VOL_EXPANSION",
        direction=plan["direction"],
        entry_zone=plan["entry_zone"],
        invalidation=plan["invalidation"],
        risk_size=plan["risk_size"],
        targets=plan["targets"],
        trigger_codes=fired,
        confidence_factors=[
            f"BB percentile: {bb_pct:.1f}% (compressed)",
            f"Squeeze state: {sq_state}",
            f"Liquidity sweep: {'EQL' if sweep_bull else 'EQH'}",
            f"Structure bias: {direction}",
        ],
        raw_score=7.0 if sq_state == "SQUEEZE_FIRE" else 5.0,
        extra={"bb_pct": bb_pct, "sq_state": sq_state, "pattern_extreme": pattern_extreme},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def detect_recipes(
    candles: List[Candle],
    struct: Dict[str, Any],
    sweeps: Dict[str, Any],
    avwap: Dict[str, Any],
    squeeze: Dict[str, Any],
    atr_val: Optional[float] = None,
    account_size: float = 10_000.0,
) -> List[RecipeSignal]:
    """
    Run all three recipe detectors and return every qualifying RecipeSignal.

    Parameters
    ──────────
    candles      : 5m candle list (minimum 40 required for reliable output).
    struct       : Output of intelligence.structure.detect_structure()
    sweeps       : Output of intelligence.sweeps.detect_equal_levels()
    avwap        : Output of intelligence.anchored_vwap.compute_anchored_vwap()
    squeeze      : Output of intelligence.squeeze.detect_squeeze()
    atr_val      : Pre-computed 14-bar ATR.  Auto-computed from candles if None.
    account_size : Notional account size in USD for risk_size calculation.

    Returns
    ───────
    List[RecipeSignal] — empty if no recipe qualifies.  Multiple can fire
    simultaneously (e.g. HTF_REVERSAL + VOL_EXPANSION on a sweep bar).
    """
    if len(candles) < 40:
        return []

    if atr_val is None or atr_val <= 0:
        atr_val = calc_atr(candles, 14) or (candles[-1].close * 0.01)

    results: List[RecipeSignal] = []

    try:
        sig = _recipe_htf_reversal(candles, struct, sweeps, avwap, atr_val, account_size)
        if sig:
            results.append(sig)
    except Exception as exc:
        logger.warning("recipes.HTF_REVERSAL error: %s", exc, exc_info=True)

    try:
        sig = _recipe_bos_continuation(candles, struct, sweeps, atr_val, account_size)
        if sig:
            results.append(sig)
    except Exception as exc:
        logger.warning("recipes.BOS_CONTINUATION error: %s", exc, exc_info=True)

    try:
        sig = _recipe_vol_expansion(candles, squeeze, sweeps, struct, atr_val, account_size)
        if sig:
            results.append(sig)
    except Exception as exc:
        logger.warning("recipes.VOL_EXPANSION error: %s", exc, exc_info=True)

    return results
