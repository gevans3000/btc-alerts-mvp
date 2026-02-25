import pytest
from intelligence.confluence import compute_confluence

def test_strong_bullish():
    codes = ["SQUEEZE_FIRE", "SENTIMENT_BULL", "NEAR_POC", "BID_WALL_SUPPORT", "DONCHIAN_BREAK"]
    bd = {"trend_alignment": 5, "momentum": 10, "volatility": 8, "volume": 3, "htf": 4}
    r = compute_confluence(codes, bd)
    assert r["bullish_count"] == 5 and r["bearish_count"] == 0 and r["strength"] == "STRONG"

def test_mixed_weak():
    r = compute_confluence(["SQUEEZE_FIRE", "SENTIMENT_BEAR"],
        {"trend_alignment": 0, "momentum": 0, "volatility": 0, "volume": 0, "htf": 0})
    assert r["bullish_count"] == 1 and r["bearish_count"] == 1 and r["strength"] == "WEAK"

def test_no_signals():
    r = compute_confluence(["REGIME_TREND"],
        {"trend_alignment": 0, "momentum": 0, "volatility": 0, "volume": 0, "htf": 0})
    assert r["bullish_count"] == 0 and r["strength"] == "WEAK"
