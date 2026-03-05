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

from utils import Candle, atr as calc_atr, rsi as calc_rsi, donchian_break

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
    exec_px: float                 # Intended execution price
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


def _donchian_width_percentile(candles: List[Candle], period: int = 20, lookback: int = 100) -> float:
    """Return Donchian channel width percentile."""
    if len(candles) < period + lookback:
        return 50.0
    widths = []
    for i in range(len(candles) - lookback, len(candles)):
        window = candles[i - period: i]
        if not window: continue
        w = max(c.high for c in window) - min(c.low for c in window)
        widths.append(w)
    if not widths: return 50.0
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

    # Compose legs: require structure + at least ONE of (sweep, avwap)
    # Previously required all 3 — too strict, fired <1% of candles
    long_signal = has_bull_struct and (sweep_bull or avwap_bull)
    short_signal = has_bear_struct and (sweep_bear or avwap_bear)

    if not (long_signal or short_signal):
        return None

    direction = "LONG" if long_signal else "SHORT"

    # Pattern extreme: the swept level (EQL for LONG, EQH for SHORT)
    if direction == "LONG":
        eq_lows = sweeps.get("equal_lows", [])
        pattern_extreme = min(eq_lows) if (isinstance(eq_lows, list) and eq_lows) else (price - atr_val)
        opposite_liq = struct.get("last_pivot_high", price + 2 * atr_val) or (price + 2 * atr_val)
    else:
        eq_highs = sweeps.get("equal_highs", [])
        pattern_extreme = max(eq_highs) if (isinstance(eq_highs, list) and eq_highs) else (price + atr_val)
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
        exec_px=plan["exec_px"],
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
        if not (retest_level - 1.0 * atr_val <= price <= retest_level + 1.0 * atr_val):
            return None
        # Rejection wick: bullish → lower wick >= 30% of candle range
        c_range = last.high - last.low
        lower_wick = last.open - last.low if last.open > last.low else last.close - last.low
        if c_range > 0 and (lower_wick / c_range) < 0.30:
            return None
        pattern_extreme = retest_level
        opposite_liq = struct.get("last_pivot_high", price + 2 * atr_val) or (price + 2 * atr_val)
    else:
        retest_level = struct.get("last_pivot_low", price + atr_val)
        if not retest_level:
            return None
        if not (retest_level - 1.0 * atr_val <= price <= retest_level + 1.0 * atr_val):
            return None
        c_range = last.high - last.low
        upper_wick = last.high - last.open if last.open < last.high else last.high - last.close
        if c_range > 0 and (upper_wick / c_range) < 0.30:
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
        exec_px=plan["exec_px"],
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
    if bb_pct >= 25.0:
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
        pattern_extreme = min(eq_lows) if (isinstance(eq_lows, list) and eq_lows) else (price - atr_val)
        opposite_liq = struct.get("last_pivot_high", price + 3 * atr_val) or (price + 3 * atr_val)
    else:
        eq_highs = sweeps.get("equal_highs", [])
        pattern_extreme = max(eq_highs) if (isinstance(eq_highs, list) and eq_highs) else (price + atr_val)
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
        exec_px=plan["exec_px"],
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


def _recipe_range_breakout(
    candles: List[Candle],
    atr_val: float,
    account_size: float,
) -> Optional[RecipeSignal]:
    """
    RANGE_BREAKOUT: Low-volatility range breakout with volume confirmation.
    """
    if len(candles) < 40: return None
    
    # Donchian width percentile (squeeze check)
    width_pct = _donchian_width_percentile(candles, 20, 100)
    if width_pct > 25.0:
        return None
        
    # Volume confirmation
    vol_avg = sum(c.volume for c in candles[-21:-1]) / 20
    if candles[-1].volume <= 1.5 * vol_avg:
        return None
        
    # Breakout check
    bull_break, bear_break = donchian_break(candles, 20)
    if not (bull_break or bear_break):
        return None
        
    direction = "LONG" if bull_break else "SHORT"
    last = candles[-1]
    price = last.close
    
    # Range extreme
    window = candles[-21:-1]
    high_20 = max(c.high for c in window)
    low_20 = min(c.low for c in window)
    width = high_20 - low_20
    
    pattern_extreme = low_20 if direction == "LONG" else high_20
    opposite_liq = high_20 + width if direction == "LONG" else low_20 - width
    
    plan = _five_questions(direction, price, pattern_extreme, opposite_liq, atr_val, account_size, abs(last.high - last.low))
    
    # Phase 30: TP1 = 1:1, TP2 = 2:1
    r = abs(plan["exec_px"] - plan["invalidation"])
    if direction == "LONG":
        plan["targets"]["tp1"] = round(plan["exec_px"] + r, 2)
        plan["targets"]["tp2"] = round(plan["exec_px"] + 2 * r, 2)
    else:
        plan["targets"]["tp1"] = round(plan["exec_px"] - r, 2)
        plan["targets"]["tp2"] = round(plan["exec_px"] - 2 * r, 2)

    return RecipeSignal(
        recipe="RANGE_BREAKOUT",
        direction=direction,
        entry_zone=plan["entry_zone"],
        exec_px=plan["exec_px"],
        invalidation=plan["invalidation"],
        risk_size=plan["risk_size"],
        targets=plan["targets"],
        trigger_codes=["RANGE_BREAKOUT"],
        confidence_factors=[f"Width percentile: {width_pct:.1f}", "Volume confirmed (1.5x)"],
        raw_score=6.0
    )


def _recipe_momentum_divergence(
    candles: List[Candle],
    struct: Dict[str, Any],
    atr_val: float,
    account_size: float,
) -> Optional[RecipeSignal]:
    """
    MOMENTUM_DIVERGENCE: Price extreme + RSI divergence + BOS confirmation.
    """
    if len(candles) < 30: return None
    
    last = candles[-1]
    prev_10 = candles[-11:-1]
    
    # 1. Price new high/low (10 bars)
    is_high = last.high > max(c.high for c in prev_10)
    is_low = last.low < min(c.low for c in prev_10)
    if not (is_high or is_low):
        return None
        
    # 2. RSI Divergence
    # Bullish: Price new low, RSI NOT new low (or rising)
    # Bearish: Price new high, RSI NOT new high (or falling)
    rsi_vals = [calc_rsi([c.close for c in candles[:i+1]], 14) for i in range(len(candles)-20, len(candles))]
    rsi_vals = [r for r in rsi_vals if r is not None]
    if len(rsi_vals) < 10: return None
    
    curr_rsi = rsi_vals[-1]
    prev_rsi_max = max(rsi_vals[:-1])
    prev_rsi_min = min(rsi_vals[:-1])
    
    div_bull = is_low and curr_rsi > prev_rsi_min
    div_bear = is_high and curr_rsi < prev_rsi_max
    
    if not (div_bull or div_bear):
        return None
        
    # 3. BOS Confirmation
    event = struct.get("last_event", "")
    if div_bull and event != "BOS_BULL": return None
    if div_bear and event != "BOS_BEAR": return None
    
    direction = "LONG" if div_bull else "SHORT"
    price = last.close
    
    # Entry: Limit at retest of divergence swing (1% buffer)
    pattern_extreme = last.low if direction == "LONG" else last.high
    retrace_px = price * (1.01 if direction == "SHORT" else 0.99)
    
    # Use structure for TP
    opposite_liq = struct.get("last_pivot_high" if direction == "LONG" else "last_pivot_low", price + (2 * atr_val if direction == "LONG" else -2 * atr_val))
    
    plan = _five_questions(direction, price, pattern_extreme, opposite_liq, atr_val, account_size)
    plan["entry_zone"] = f"LIMIT@{retrace_px:,.0f}"
    plan["exec_px"] = round(retrace_px, 2)
    
    # TP2: 2x ATR
    if direction == "LONG":
        plan["targets"]["tp2"] = round(price + 2 * atr_val, 2)
    else:
        plan["targets"]["tp2"] = round(price - 2 * atr_val, 2)

    return RecipeSignal(
        recipe="MOMENTUM_DIVERGENCE",
        direction=direction,
        entry_zone=plan["entry_zone"],
        exec_px=plan["exec_px"],
        invalidation=plan["invalidation"],
        risk_size=plan["risk_size"],
        targets=plan["targets"],
        trigger_codes=["MOM_DIVERGENCE"],
        confidence_factors=["Price extreme (10-bar)", "RSI Divergence", f"BOS {event}"],
        raw_score=7.0
    )


def _recipe_funding_flush(
    candles: List[Candle],
    context: Dict[str, Any],
    struct: Dict[str, Any],
    atr_val: float,
    account_size: float,
) -> Optional[RecipeSignal]:
    """
    FUNDING_FLUSH: Extreme funding + Taker ratio flip + Structure alignment.
    """
    deriv = context.get("derivatives", {})
    flows = context.get("flows", {})
    
    funding = deriv.get("funding_rate", 0)
    taker_ratio = flows.get("taker_ratio", 1.0)
    
    # 1. Extreme funding
    long_flush = funding > 0.0005  # 0.05%
    short_flush = funding < -0.0003 # -0.03%
    
    if not (long_flush or short_flush):
        return None
        
    # 2. Taker ratio flip (fade the crowd)
    # If longs paying heavy (funding > 0.05), we want shorts entering (taker_ratio < 1.0)
    # If shorts paying (funding < -0.03), we want longs entering (taker_ratio > 1.0)
    if long_flush and taker_ratio >= 1.0: return None
    if short_flush and taker_ratio <= 1.0: return None
    
    # 3. Structure alignment
    direction = "SHORT" if long_flush else "LONG"
    struct_trend = struct.get("trend", "").upper()
    if direction not in struct_trend:
        # Allow if CHoCH just happened
        if "CHOCH" not in struct.get("last_event", ""):
            return None
            
    last = candles[-1]
    price = last.close
    
    # Invalidation: 1.5x ATR
    invalidation = price + (1.5 * atr_val if direction == "SHORT" else -1.5 * atr_val)
    
    # TP1: nearest structure (1:1), TP2: 2x ATR
    tp1 = price + (abs(price - invalidation)) * (1 if direction == "LONG" else -1)
    tp2 = price + (2 * atr_val) * (1 if direction == "LONG" else -1)
    
    plan = {
        "direction": direction,
        "entry_zone": "MARKET",
        "exec_px": price,
        "invalidation": round(invalidation, 2),
        "risk_size": round((account_size * 0.01) / abs(price - invalidation), 4),
        "targets": {"tp1": round(tp1, 2), "tp2": round(tp2, 2)}
    }

    return RecipeSignal(
        recipe="FUNDING_FLUSH",
        direction=direction,
        entry_zone=plan["entry_zone"],
        exec_px=plan["exec_px"],
        invalidation=plan["invalidation"],
        risk_size=plan["risk_size"],
        targets=plan["targets"],
        trigger_codes=["FUNDING_FLUSH"],
        confidence_factors=[f"Funding: {funding*100:.3f}%", f"Taker Ratio: {taker_ratio:.2f}"],
        raw_score=5.0
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

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
    if not signals:
        return []

    directions = set(s.direction for s in signals)
    
    # Rule 1: Contradictory directions
    if "LONG" in directions and "SHORT" in directions:
        return []
    
    # Rule 2: Multiple signals in same direction -> take best
    # Sort by raw_score descending
    sorted_signals = sorted(signals, key=lambda x: x.raw_score, reverse=True)
    return [sorted_signals[0]]

def detect_recipes(
    candles: List[Candle],
    struct: Dict[str, Any],
    sweeps: Dict[str, Any],
    avwap: Dict[str, Any],
    squeeze: Dict[str, Any],
    atr_val: Optional[float] = None,
    account_size: float = 10_000.0,
    context: Dict[str, Any] = None,
) -> List[RecipeSignal]:
    """
    Run all recipe detectors and return every qualifying RecipeSignal.
    """
    if len(candles) < 40:
        return []

    context = context or {}
    if atr_val is None or atr_val <= 0:
        atr_val = calc_atr(candles, 14) or (candles[-1].close * 0.01)

    results: List[RecipeSignal] = []

    # Original Recipes
    try:
        sig = _recipe_htf_reversal(candles, struct, sweeps, avwap, atr_val, account_size)
        if sig: results.append(sig)
    except Exception as exc:
        logger.warning("recipes.HTF_REVERSAL error: %s", exc)

    try:
        sig = _recipe_bos_continuation(candles, struct, sweeps, atr_val, account_size)
        if sig: results.append(sig)
    except Exception as exc:
        logger.warning("recipes.BOS_CONTINUATION error: %s", exc)

    try:
        sig = _recipe_vol_expansion(candles, squeeze, sweeps, struct, atr_val, account_size)
        if sig: results.append(sig)
    except Exception as exc:
        logger.warning("recipes.VOL_EXPANSION error: %s", exc)

    # Phase 30: New Recipes
    try:
        sig = _recipe_range_breakout(candles, atr_val, account_size)
        if sig: results.append(sig)
    except Exception as exc:
        logger.warning("recipes.RANGE_BREAKOUT error: %s", exc)

    try:
        sig = _recipe_momentum_divergence(candles, struct, atr_val, account_size)
        if sig: results.append(sig)
    except Exception as exc:
        logger.warning("recipes.MOMENTUM_DIVERGENCE error: %s", exc)

    if context:
        try:
            sig = _recipe_funding_flush(candles, context, struct, atr_val, account_size)
            if sig: results.append(sig)
        except Exception as exc:
            logger.warning("recipes.FUNDING_FLUSH error: %s", exc)

    return results
