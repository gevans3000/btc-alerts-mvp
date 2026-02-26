"""Anchored VWAP from the last significant swing point."""
from typing import List, Dict, Any
from utils import Candle
from math import sqrt
import logging

logger = logging.getLogger(__name__)


def compute_anchored_vwap(candles: List[Candle], lookback_for_anchor: int = 50) -> Dict[str, Any]:
    """
    Find the last major swing (highest high or lowest low in lookback),
    then compute VWAP from that point forward with ±1σ and ±2σ bands.

    Returns:
        {
            "avwap": float,       # Anchored VWAP value
            "upper_1": float,     # +1 std dev band
            "lower_1": float,     # -1 std dev band
            "anchor_price": float,
            "anchor_type": "high" | "low",
            "price_vs_avwap": "above" | "below" | "at",
            "codes": [],
            "pts": float
        }
    """
    if len(candles) < 20:
        return {"avwap": 0, "upper_1": 0, "lower_1": 0, "anchor_price": 0, "anchor_type": "high", "price_vs_avwap": "at", "codes": [], "pts": 0}

    # Find anchor: highest high or lowest low in lookback
    subset = candles[-lookback_for_anchor:] if len(candles) >= lookback_for_anchor else candles
    max_high = max(range(len(subset)), key=lambda i: subset[i].high)
    min_low = min(range(len(subset)), key=lambda i: subset[i].low)

    # Use whichever is more recent as anchor
    if max_high > min_low:
        anchor_idx = max_high
        anchor_type = "high"
        anchor_price = subset[anchor_idx].high
    else:
        anchor_idx = min_low
        anchor_type = "low"
        anchor_price = subset[anchor_idx].low

    # Compute VWAP from anchor forward
    vwap_candles = subset[anchor_idx:]
    if len(vwap_candles) < 3:
        return {"avwap": 0, "upper_1": 0, "lower_1": 0, "anchor_price": anchor_price, "anchor_type": anchor_type, "price_vs_avwap": "at", "codes": [], "pts": 0}

    cum_vol = 0.0
    cum_tp_vol = 0.0
    cum_tp2_vol = 0.0
    for c in vwap_candles:
        tp = (c.high + c.low + c.close) / 3.0
        cum_vol += c.volume
        cum_tp_vol += tp * c.volume
        cum_tp2_vol += tp * tp * c.volume

    if cum_vol == 0:
        return {"avwap": 0, "upper_1": 0, "lower_1": 0, "anchor_price": anchor_price, "anchor_type": anchor_type, "price_vs_avwap": "at", "codes": [], "pts": 0}

    avwap = cum_tp_vol / cum_vol
    variance = max(0, (cum_tp2_vol / cum_vol) - avwap * avwap)
    std = sqrt(variance)
    upper_1 = avwap + std
    lower_1 = avwap - std

    last_price = candles[-1].close
    codes = []
    pts = 0.0

    if last_price > avwap:
        pos = "above"
    elif last_price < avwap:
        pos = "below"
    else:
        pos = "at"

    # Reclaim/reject signals
    prev_close = candles[-2].close if len(candles) >= 2 else last_price
    if prev_close < avwap and last_price > avwap:
        codes.append("AVWAP_RECLAIM_BULL")
        pts += 3.0
    elif prev_close > avwap and last_price < avwap:
        codes.append("AVWAP_REJECT_BEAR")
        pts -= 3.0

    # Band extremes
    if last_price > upper_1:
        codes.append("AVWAP_ABOVE_1SD")
    elif last_price < lower_1:
        codes.append("AVWAP_BELOW_1SD")

    return {
        "avwap": round(avwap, 2), "upper_1": round(upper_1, 2), "lower_1": round(lower_1, 2),
        "anchor_price": round(anchor_price, 2), "anchor_type": anchor_type,
        "price_vs_avwap": pos, "codes": codes, "pts": pts,
    }
