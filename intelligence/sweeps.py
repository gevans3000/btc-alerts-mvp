"""Equal highs/lows and liquidity sweep detection."""
from typing import List, Dict, Any
from utils import Candle
import logging

logger = logging.getLogger(__name__)


def detect_equal_levels(candles: List[Candle], tolerance_pct: float = 0.001, min_touches: int = 2, lookback: int = 50) -> Dict[str, Any]:
    """
    Detect equal highs and equal lows (resting liquidity).
    Also detect takeout/sweep: wick through the cluster then close back.

    Returns:
        {
            "equal_highs": [price, ...],
            "equal_lows": [price, ...],
            "sweep_high": bool,  # Just swept above equal highs
            "sweep_low": bool,   # Just swept below equal lows
            "codes": [],
            "pts": float
        }
    """
    if len(candles) < 20:
        return {"equal_highs": [], "equal_lows": [], "sweep_high": False, "sweep_low": False, "codes": [], "pts": 0}

    subset = candles[-lookback:]
    last = candles[-1]
    ref = last.close

    # Cluster highs by proximity
    highs = [c.high for c in subset[:-1]]
    lows = [c.low for c in subset[:-1]]

    def _find_clusters(levels: List[float], tol: float) -> List[float]:
        if not levels:
            return []
        sorted_lvls = sorted(levels)
        clusters = []
        group = [sorted_lvls[0]]
        for lvl in sorted_lvls[1:]:
            if abs(lvl - group[0]) / max(group[0], 1e-9) <= tol:
                group.append(lvl)
            else:
                if len(group) >= min_touches:
                    clusters.append(sum(group) / len(group))
                group = [lvl]
        if len(group) >= min_touches:
            clusters.append(sum(group) / len(group))
        return clusters

    eq_highs = _find_clusters(highs, tolerance_pct)
    eq_lows = _find_clusters(lows, tolerance_pct)

    codes = []
    pts = 0.0

    # Filter to nearby levels (within 1% of current price)
    eq_highs = [h for h in eq_highs if abs(h - ref) / ref < 0.01]
    eq_lows = [l for l in eq_lows if abs(l - ref) / ref < 0.01]

    if eq_highs:
        codes.append("EQUAL_HIGHS_NEARBY")
    if eq_lows:
        codes.append("EQUAL_LOWS_NEARBY")

    # Sweep detection
    sweep_high = False
    sweep_low = False
    for h in eq_highs:
        if last.high > h and last.close < h:
            sweep_high = True
            codes.append("EQH_SWEEP_BEAR")
            pts -= 4.0
            break
    for l in eq_lows:
        if last.low < l and last.close > l:
            sweep_low = True
            codes.append("EQL_SWEEP_BULL")
            pts += 4.0
            break

    return {
        "equal_highs": [round(h, 2) for h in eq_highs],
        "equal_lows": [round(l, 2) for l in eq_lows],
        "sweep_high": sweep_high,
        "sweep_low": sweep_low,
        "codes": codes,
        "pts": pts,
    }
