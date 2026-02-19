"""Volume Profile with Point of Control (POC) detection."""
from typing import List, Dict, Any
from utils import Candle
from config import VOLUME_PROFILE
import logging
logger = logging.getLogger(__name__)


def compute_volume_profile(candles: List[Candle]) -> Dict[str, Any]:
    lookback = VOLUME_PROFILE["lookback_candles"]
    num_bins = VOLUME_PROFILE["num_bins"]
    poc_pct = VOLUME_PROFILE["poc_proximity_pct"]
    poc_pts = VOLUME_PROFILE["poc_pts"]

    if len(candles) < 20:
        return {"poc": 0.0, "near_poc": False, "pts": 0, "profile_bins": 0}

    subset = candles[-lookback:]
    lo = min(c.low for c in subset)
    hi = max(c.high for c in subset)
    if hi == lo:
        return {"poc": lo, "near_poc": True, "pts": 0, "profile_bins": 0}

    bin_size = (hi - lo) / num_bins
    bins = [0.0] * num_bins
    for c in subset:
        b_lo = max(0, min(int((c.low - lo) / bin_size), num_bins - 1))
        b_hi = max(0, min(int((c.high - lo) / bin_size), num_bins - 1))
        span = b_hi - b_lo + 1
        v = c.volume / span if span > 0 else c.volume
        for b in range(b_lo, b_hi + 1):
            bins[b] += v

    idx = bins.index(max(bins))
    poc = lo + (idx + 0.5) * bin_size
    near = abs(candles[-1].close - poc) / poc <= poc_pct
    return {"poc": round(poc, 2), "near_poc": near, "pts": poc_pts if near else 0, "profile_bins": num_bins}
