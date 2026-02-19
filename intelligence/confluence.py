"""Confluence heatmap: counts how many intelligence layers agree."""
from typing import Dict, Any, List
import logging
logger = logging.getLogger(__name__)


def compute_confluence(reason_codes: List[str], breakdown: Dict[str, float]) -> Dict[str, Any]:
    bullish_signals = [
        "SQUEEZE_FIRE", "SENTIMENT_BULL", "NEAR_POC",
        "BID_WALL_SUPPORT", "DXY_FALLING_BULLISH", "GOLD_RISING_BULLISH",
        "DONCHIAN_BREAK", "VWAP_RECLAIM", "RSI_DIVERGENCE",
        "BB_EXPANSION", "SESSION_BOOST",
    ]
    bearish_signals = [
        "SENTIMENT_BEAR", "ASK_WALL_RESISTANCE",
        "DXY_RISING_BEARISH", "GOLD_FALLING_BEARISH",
        "VWAP_REJECT", "VIX_SPIKE",
    ]

    bull = sum(1 for c in reason_codes if c in bullish_signals)
    bear = sum(1 for c in reason_codes if c in bearish_signals)
    net = bull - bear

    if abs(net) >= 4:
        strength = "STRONG"
    elif abs(net) >= 2:
        strength = "MODERATE"
    else:
        strength = "WEAK"

    categories = {
        "trend": breakdown.get("trend_alignment", 0.0),
        "momentum": breakdown.get("momentum", 0.0),
        "volatility": breakdown.get("volatility", 0.0),
        "volume": breakdown.get("volume", 0.0),
        "htf": breakdown.get("htf", 0.0),
    }

    return {
        "bullish_count": bull,
        "bearish_count": bear,
        "net": net,
        "strength": strength,
        "layers": categories,
    }
