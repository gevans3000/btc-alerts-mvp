from typing import List, Dict, Any, Tuple
from collections import defaultdict
from utils import Candle

def volume_profile(candles: List[Candle], num_buckets: int = 100) -> Dict[str, Any]:
    """Calculates the Volume Profile, Point of Control (POC), and Value Area (VA) for a given list of candles.

    Args:
        candles: A list of Candle objects, sorted chronologically.
        num_buckets: The number of price buckets to divide the price range into.

    Returns:
        A dictionary containing:
            - 'poc_price': The price at the Point of Control (price with highest volume).
            - 'poc_volume': The volume at the Point of Control.
            - 'va_high': The upper bound of the Value Area.
            - 'va_low': The lower bound of the Value Area.
            - 'total_volume': The total volume across all candles.
            - 'profile': A list of tuples (price, volume) representing the volume profile.
            Returns an empty dictionary if insufficient candles or no volume.
    """
    if not candles:
        return {}

    min_price = min(c.low for c in candles)
    max_price = max(c.high for c in candles)
    total_volume = sum(c.volume for c in candles)

    if total_volume == 0:
        return {}

    price_range = max_price - min_price
    if price_range == 0:
        return {
            'poc_price': min_price,
            'poc_volume': total_volume,
            'va_high': min_price,
            'va_low': min_price,
            'total_volume': total_volume,
            'profile': [(min_price, total_volume)]
        }

    bucket_size = price_range / num_buckets
    if bucket_size == 0:
        # Handle cases where price_range is extremely small, causing bucket_size to be 0
        # This can happen if all highs and lows are virtually the same, but not exactly.
        # In such cases, treat it as a single bucket around the average price.
        avg_price = sum(c.close for c in candles) / len(candles)
        return {
            'poc_price': avg_price,
            'poc_volume': total_volume,
            'va_high': avg_price,
            'va_low': avg_price,
            'total_volume': total_volume,
            'profile': [(avg_price, total_volume)]
        }

    volume_by_price_bucket = defaultdict(float)

    for candle in candles:
        # Determine the price bucket for the candle's close price
        bucket_idx = int((candle.close - min_price) / bucket_size)
        # Ensure bucket_idx is within valid range
        bucket_idx = max(0, min(num_buckets - 1, bucket_idx))
        bucket_price = min_price + bucket_idx * bucket_size + (bucket_size / 2) # Midpoint of the bucket
        volume_by_price_bucket[bucket_price] += candle.volume

    # Sort buckets by price for a readable profile, and find POC
    sorted_profile = sorted(volume_by_price_bucket.items())
    poc_price = 0.0
    poc_volume = -1.0

    for price, volume in sorted_profile:
        if volume > poc_volume:
            poc_volume = volume
            poc_price = price

    # Calculate Value Area (VA)
    # The Value Area typically contains 70% of the total volume.
    va_volume_target = total_volume * 0.70
    current_volume = 0.0
    va_prices = []

    # Start from POC bucket and expand outwards to capture 70% of volume
    poc_idx = -1
    for i, (price, volume) in enumerate(sorted_profile):
        if price == poc_price:
            poc_idx = i
            break

    if poc_idx == -1:
        # Should not happen if poc_price is from sorted_profile
        return {}
    
    # Add POC bucket to VA
    current_volume += sorted_profile[poc_idx][1]
    va_prices.append(sorted_profile[poc_idx][0])

    low_idx = poc_idx
    high_idx = poc_idx

    while current_volume < va_volume_target and (low_idx > 0 or high_idx < len(sorted_profile) - 1):
        can_move_down = low_idx > 0
        can_move_up = high_idx < len(sorted_profile) - 1

        if can_move_down and (not can_move_up or sorted_profile[low_idx - 1][1] > sorted_profile[high_idx + 1][1]):
            low_idx -= 1
            current_volume += sorted_profile[low_idx][1]
            va_prices.append(sorted_profile[low_idx][0])
        elif can_move_up:
            high_idx += 1
            current_volume += sorted_profile[high_idx][1]
            va_prices.append(sorted_profile[high_idx][0])
        else:
            break # No more buckets to add

    va_high = max(va_prices) if va_prices else poc_price
    va_low = min(va_prices) if va_prices else poc_price

    return {
        'poc_price': poc_price,
        'poc_volume': poc_volume,
        'va_high': va_high,
        'va_low': va_low,
        'total_volume': total_volume,
        'profile': sorted_profile
    }