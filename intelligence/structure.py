"""Market Structure: BOS (Break of Structure) and CHoCH (Change of Character)."""
from typing import List, Dict, Any, Tuple
from utils import Candle
import logging

logger = logging.getLogger(__name__)


def _find_pivots(candles: List[Candle], left: int = 3, right: int = 3) -> List[Dict]:
    """Find pivot highs and lows using left/right bar comparison."""
    pivots = []
    for i in range(left, len(candles) - right):
        # Pivot High
        is_ph = all(candles[i].high >= candles[i - j].high for j in range(1, left + 1)) and \
                all(candles[i].high >= candles[i + j].high for j in range(1, right + 1))
        if is_ph:
            pivots.append({"type": "high", "price": candles[i].high, "index": i, "ts": candles[i].ts})
        # Pivot Low
        is_pl = all(candles[i].low <= candles[i - j].low for j in range(1, left + 1)) and \
                all(candles[i].low <= candles[i + j].low for j in range(1, right + 1))
        if is_pl:
            pivots.append({"type": "low", "price": candles[i].low, "index": i, "ts": candles[i].ts})
    return pivots


def detect_structure(candles: List[Candle], left: int = 3, right: int = 3) -> Dict[str, Any]:
    """
    Detect BOS and CHoCH from recent candle data.

    Returns:
        {
            "trend": "bullish" | "bearish" | "neutral",
            "last_event": "BOS_BULL" | "BOS_BEAR" | "CHOCH_BULL" | "CHOCH_BEAR" | None,
            "last_pivot_high": float,
            "last_pivot_low": float,
            "codes": ["STRUCTURE_BOS_BULL"] etc.,
            "pts": float
        }
    """
    if len(candles) < 20:
        return {"trend": "neutral", "last_event": None, "last_pivot_high": 0, "last_pivot_low": 0, "codes": [], "pts": 0}

    pivots = _find_pivots(candles, left, right)
    if len(pivots) < 4:
        return {"trend": "neutral", "last_event": None, "last_pivot_high": 0, "last_pivot_low": 0, "codes": [], "pts": 0}

    # Get the last few highs and lows
    highs = [p for p in pivots if p["type"] == "high"]
    lows = [p for p in pivots if p["type"] == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return {"trend": "neutral", "last_event": None, "last_pivot_high": 0, "last_pivot_low": 0, "codes": [], "pts": 0}

    last_price = candles[-1].close
    prev_high = highs[-2]["price"]
    last_high = highs[-1]["price"]
    prev_low = lows[-2]["price"]
    last_low = lows[-1]["price"]

    # Determine current trend from higher highs / higher lows vs lower highs / lower lows
    hh = last_high > prev_high  # Higher high
    hl = last_low > prev_low    # Higher low
    lh = last_high < prev_high  # Lower high
    ll = last_low < prev_low    # Lower low

    codes = []
    pts = 0.0
    event = None

    if hh and hl:
        # Bullish structure
        trend = "bullish"
        # BOS = price breaks above the last pivot high
        if last_price > last_high:
            event = "BOS_BULL"
            codes.append("STRUCTURE_BOS_BULL")
            pts = 5.0
    elif lh and ll:
        # Bearish structure
        trend = "bearish"
        if last_price < last_low:
            event = "BOS_BEAR"
            codes.append("STRUCTURE_BOS_BEAR")
            pts = -5.0
    elif hh and ll:
        trend = "neutral"  # Expanding — no clear structure
    elif lh and hl:
        trend = "neutral"  # Contracting — range
    else:
        trend = "neutral"

    # CHoCH: was bearish (LH+LL) but now made a higher high, or vice versa
    if lh and not ll and last_price > last_high:
        event = "CHOCH_BULL"
        codes.append("STRUCTURE_CHOCH_BULL")
        pts = 6.0
        trend = "shift_bullish"
    elif hh and not hl and last_price < last_low:
        event = "CHOCH_BEAR"
        codes.append("STRUCTURE_CHOCH_BEAR")
        pts = -6.0
        trend = "shift_bearish"

    return {
        "trend": trend,
        "last_event": event,
        "last_pivot_high": last_high,
        "last_pivot_low": last_low,
        "codes": codes,
        "pts": pts,
    }
