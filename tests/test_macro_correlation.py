import pytest
from intelligence.macro_correlation import analyze_macro_correlation
from utils import Candle
from datetime import datetime, timedelta

def _daily(base, n, trend=0.0):
    p = base
    out = []
    for i in range(n):
        ts = (datetime.now()-timedelta(days=n-i)).isoformat()
        out.append(Candle(ts=ts, open=p, high=p+1, low=p-1, close=p, volume=1e6))
        p += trend
    return out

def test_dxy_falling():
    r = analyze_macro_correlation({"dxy": _daily(105,30,-0.5), "gold": _daily(2000,30)})
    assert r["dxy_trend"] == "falling" and r["pts"] >= 3

def test_dxy_rising():
    r = analyze_macro_correlation({"dxy": _daily(100,30,0.5), "gold": _daily(2000,30)})
    assert r["dxy_trend"] == "rising" and r["pts"] <= -3

def test_no_data():
    r = analyze_macro_correlation({"dxy": _daily(100,5), "gold": []})
    assert r["pts"] == 0

def test_gold_rising():
    r = analyze_macro_correlation({"dxy": _daily(100,30), "gold": _daily(1800,30,5)})
    assert r["gold_trend"] == "rising" and r["pts"] >= 2
