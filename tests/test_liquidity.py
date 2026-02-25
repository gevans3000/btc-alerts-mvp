import pytest
from intelligence.liquidity import analyze_liquidity
from collectors.orderbook import OrderBookSnapshot

def test_support():
    r = analyze_liquidity(OrderBookSnapshot(ts=1000, bids=[(100.0,10.0),(99.5,2.0)], asks=[(100.5,0.5)]))
    assert r["support"] is True and r["pts"] > 0

def test_resistance():
    r = analyze_liquidity(OrderBookSnapshot(ts=1000, bids=[(100.0,0.5)], asks=[(100.5,10.0)]))
    assert r["resistance"] is True and r["pts"] < 0

def test_none():
    r = analyze_liquidity(OrderBookSnapshot(ts=1000, bids=[(100.0,0.1)], asks=[(100.5,0.1)]))
    assert r["pts"] == 0

def test_unhealthy():
    # OrderBookSnapshot __post_init__ will set healthy=False if bids/asks are empty
    # so we manually set it or rely on the logic
    obs = OrderBookSnapshot(ts=1000, bids=[], asks=[])
    obs.healthy = False
    assert analyze_liquidity(obs)["pts"] == 0
