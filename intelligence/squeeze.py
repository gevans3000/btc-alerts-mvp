from typing import List, Dict, Any, Optional
from utils import bollinger_bands, atr, Candle


def keltner_channels(candles: List[Candle], period: int = 20, atr_mult: float = 1.5):
    """Returns (upper, middle, lower) for latest candle."""
    if len(candles) < period:
        return None
    closes = [c.close for c in candles[-period:]]
    middle = sum(closes) / len(closes)
    atr_val = atr(candles, period)
    if atr_val is None:
        return None
    return (middle + atr_mult * atr_val, middle, middle - atr_mult * atr_val)

def detect_squeeze(candles: List[Candle]) -> Dict[str, Any]:
    """Detect TTM Squeeze state.
    Returns: {"state": "SQUEEZE_ON"|"SQUEEZE_FIRE"|"NONE", "pts": int, "bb_width": float, "kc_width": float}
    """
    if len(candles) < 22:  # Need 20 + 2 for previous comparison
        return {"state": "NONE", "pts": 0, "bb_width": 0.0, "kc_width": 0.0}

    closes = [c.close for c in candles]

    # Current state
    bb = bollinger_bands(closes, period=20, multiplier=2.0)
    kc = keltner_channels(candles, period=20, atr_mult=1.5)
    if bb is None or kc is None:
        return {"state": "NONE", "pts": 0, "bb_width": 0.0, "kc_width": 0.0}

    bb_upper, bb_mid, bb_lower = bb
    kc_upper, kc_mid, kc_lower = kc
    squeeze_on = bb_lower > kc_lower and bb_upper < kc_upper

    # Previous state (for FIRE detection)
    prev_closes = closes[:-1]
    prev_bb = bollinger_bands(prev_closes, period=20, multiplier=2.0)
    prev_kc = keltner_channels(candles[:-1], period=20, atr_mult=1.5)

    was_squeeze = False
    if prev_bb and prev_kc:
        was_squeeze = prev_bb[2] > prev_kc[2] and prev_bb[0] < prev_kc[0]

    squeeze_fire = was_squeeze and not squeeze_on

    bb_width = bb_upper - bb_lower
    kc_width = kc_upper - kc_lower

    if squeeze_fire:
        return {"state": "SQUEEZE_FIRE", "pts": 8, "bb_width": bb_width, "kc_width": kc_width}
    elif squeeze_on:
        return {"state": "SQUEEZE_ON", "pts": 0, "bb_width": bb_width, "kc_width": kc_width}
    else:
        return {"state": "NONE", "pts": 0, "bb_width": bb_width, "kc_width": kc_width}