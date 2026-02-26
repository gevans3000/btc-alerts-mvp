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

    # VAH / VAL (Value Area = 70% of total volume centered on POC)
    total_vol = sum(bins)
    target_vol = total_vol * 0.70
    cum = bins[idx]
    lo_idx, hi_idx = idx, idx
    while cum < target_vol and (lo_idx > 0 or hi_idx < num_bins - 1):
        add_lo = bins[lo_idx - 1] if lo_idx > 0 else 0
        add_hi = bins[hi_idx + 1] if hi_idx < num_bins - 1 else 0
        if add_hi >= add_lo and hi_idx < num_bins - 1:
            hi_idx += 1
            cum += add_hi
        elif lo_idx > 0:
            lo_idx -= 1
            cum += add_lo
        else:
            break
    vah = lo + (hi_idx + 1) * bin_size
    val = lo + lo_idx * bin_size

    # LVN detection: bins with < 20% of POC volume near current price
    poc_vol = bins[idx]
    lvn_threshold = poc_vol * 0.20
    last_price = candles[-1].close
    lvn_zones = []
    for b in range(num_bins):
        if bins[b] < lvn_threshold:
            lvn_price = lo + (b + 0.5) * bin_size
            if abs(lvn_price - last_price) / last_price < 0.02:  # Within 2%
                lvn_zones.append(round(lvn_price, 2))

    codes = []
    extra_pts = 0
    if lvn_zones:
        codes.append("LVN_NEARBY")
        extra_pts = 2

    # Inside vs outside value area
    if val <= last_price <= vah:
        codes.append("INSIDE_VALUE")
    elif last_price > vah:
        codes.append("ABOVE_VALUE")
    elif last_price < val:
        codes.append("BELOW_VALUE")

    return {
        "poc": round(poc, 2), "vah": round(vah, 2), "val": round(val, 2),
        "near_poc": near, "pts": (poc_pts if near else 0) + extra_pts,
        "profile_bins": num_bins, "lvn_zones": lvn_zones, "codes": codes,
    }

