import pytest
from intelligence.volume_profile import compute_volume_profile
from utils import Candle
from datetime import datetime, timedelta

def _make(base, n, vol=1000.0):
    return [Candle(ts=(datetime.now()-timedelta(hours=n-i)).isoformat(),
            open=base-1, high=base+2, low=base-2, close=base+1, volume=vol) for i in range(n)]

def test_poc_near():
    r = compute_volume_profile(_make(50000, 30))
    # print(f"DEBUG r: {r}")
    assert r["near_poc"] is True and r["pts"] == 5

def test_poc_far():
    c = _make(50000, 30)
    c[-1] = Candle(ts=c[-1].ts, open=60000, high=60500, low=59500, close=60000, volume=100)
    assert compute_volume_profile(c)["near_poc"] is False

def test_short():
    assert compute_volume_profile(_make(50000, 5))["poc"] == 0.0
