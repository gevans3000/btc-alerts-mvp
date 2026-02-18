from typing import List, Dict, Any
from utils import Candle

def compute_volume_profile(candles: List[Candle], current_price: float, num_bins: int = 50) -> Dict[str, Any]:
    """Compute volume profile, POC, and value area.
    Returns: {"poc": float, "va_high": float, "va_low": float, "position": str, "pts": float}
    """
    if len(candles) < 5:
        return {"poc": 0.0, "va_high": 0.0, "va_low": 0.0, "position": "UNKNOWN", "pts": 0.0}

    all_highs = [c.high for c in candles]
    all_lows = [c.low for c in candles]
    price_min, price_max = min(all_lows), max(all_highs)

    if price_max == price_min:
        return {"poc": price_min, "va_high": price_max, "va_low": price_min, "position": "AT_VALUE", "pts": 0.0}

    bin_size = (price_max - price_min) / num_bins
    bins = [0.0] * num_bins

    for c in candles:
        low_bin = int((c.low - price_min) / bin_size)
        high_bin = int((c.high - price_min) / bin_size)
        low_bin = max(0, min(low_bin, num_bins - 1))
        high_bin = max(0, min(high_bin, num_bins - 1))
        spread = max(high_bin - low_bin, 1)
        for b in range(low_bin, min(high_bin + 1, num_bins)):
            bins[b] += c.volume / spread

    # POC
    poc_bin = bins.index(max(bins))
    poc_price = price_min + (poc_bin + 0.5) * bin_size

    # Value Area (70% of total volume)
    total_vol = sum(bins)
    target_vol = total_vol * 0.70
    accumulated = bins[poc_bin]
    low_idx, high_idx = poc_bin, poc_bin
    while accumulated < target_vol and (low_idx > 0 or high_idx < num_bins - 1):
        look_down = bins[low_idx - 1] if low_idx > 0 else 0
        look_up = bins[high_idx + 1] if high_idx < num_bins - 1 else 0
        if look_down >= look_up and low_idx > 0:
            low_idx -= 1
            accumulated += bins[low_idx]
        elif high_idx < num_bins - 1:
            high_idx += 1
            accumulated += bins[high_idx]
        else:
            low_idx -= 1
            accumulated += bins[low_idx]

    va_low = price_min + low_idx * bin_size
    va_high = price_min + (high_idx + 1) * bin_size

    # Position relative to value area
    if current_price < va_low:
        position = "BELOW_VALUE"
        pts = 3.0
    elif current_price > va_high:
        position = "ABOVE_VALUE"
        pts = -3.0
    else:
        position = "AT_VALUE"
        pts = 0.0

    return {"poc": round(poc_price, 2), "va_high": round(va_high, 2), "va_low": round(va_low, 2), "position": position, "pts": pts}
