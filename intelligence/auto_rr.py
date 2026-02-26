"""Auto R:R computation to nearest liquidity."""
from typing import List, Dict, Any
from utils import Candle, swing_levels, atr
import logging

logger = logging.getLogger(__name__)


def compute_auto_rr(candles: List[Candle], direction: str) -> Dict[str, Any]:
    """
    Given a direction (LONG/SHORT), compute:
     - Entry = current close
     - Stop = nearest opposing swing level (support for long, resistance for short)
     - Target = nearest same-side level beyond entry
     - R:R ratio

    Returns: {"entry": float, "stop": float, "target": float, "rr": float, "codes": [], "pts": float}
    """
    if len(candles) < 30 or direction not in ("LONG", "SHORT"):
        return {"entry": 0, "stop": 0, "target": 0, "rr": 0, "codes": [], "pts": 0}

    entry = candles[-1].close
    levels = swing_levels(candles, lookback=50, tolerance=0.002)
    local_atr = atr(candles, 14) or (entry * 0.01)

    above = sorted([l for l in levels if l > entry])
    below = sorted([l for l in levels if l < entry], reverse=True)

    if direction == "LONG":
        stop = below[0] if below else entry - local_atr * 2
        target = above[0] if above else entry + local_atr * 2
    else:
        stop = above[0] if above else entry + local_atr * 2
        target = below[0] if below else entry - local_atr * 2

    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = reward / risk if risk > 0 else 0

    codes = []
    pts = 0.0

    if rr >= 2.0:
        codes.append("AUTO_RR_EXCELLENT")
        pts = 3.0
    elif rr >= 1.2:
        codes.append("AUTO_RR_ADEQUATE")
        pts = 1.0
    else:
        codes.append("AUTO_RR_POOR")
        pts = -2.0

    return {
        "entry": round(entry, 2), "stop": round(stop, 2),
        "target": round(target, 2), "rr": round(rr, 2),
        "codes": codes, "pts": pts,
    }
