import pytest
from unittest.mock import Mock
from datetime import datetime, timedelta
from typing import List
from intelligence.squeeze import detect_squeeze
from utils import Candle, bollinger_bands, atr

# Helper to create a list of candles
def create_candles(base_price: float, num_candles: int, volatility: float = 0.01, trend: float = 0.0) -> List[Candle]:
    candles = []
    current_price = base_price
    for i in range(num_candles):
        open_price = current_price
        close_price = open_price * (1 + (2 * (i % 2) - 1) * volatility + trend)
        high_price = max(open_price, close_price) * (1 + volatility * 0.5)
        low_price = min(open_price, close_price) * (1 - volatility * 0.5)
        volume = 1000 + i * 100
        ts = (datetime.now() - timedelta(minutes=(num_candles - i))).isoformat()
        candles.append(Candle(ts=ts, open=open_price, high=high_price, low=low_price, close=close_price, volume=volume))
        current_price = close_price
    return candles

# Do not mock bollinger_bands and atr. Use actual implementations from utils.py.
# @pytest.fixture(autouse=True)
# def patch_utils(monkeypatch):
#     monkeypatch.setattr('intelligence.squeeze.bollinger_bands', bollinger_bands)
#     monkeypatch.setattr('intelligence.squeeze.atr', atr)

def test_squeeze_on():
    # Scenario: BB inside KC -> SQUEEZE_ON
    # To simulate this, BB width needs to be smaller than KC width.
    # We can control this by adjusting volatility for BB and ATR multiplier for KC.
    
    # For SQUEEZE_ON, we need BB to be inside KC. This implies low volatility.
    candles = create_candles(100, 30, volatility=0.005) 
    # Ensure the last few candles have very low true range to keep KC narrow and BB narrow.
    for i in range(5):
        # Reduce the high-low range and keep open/close very close
        candles[-1 - i].high = candles[-1 - i].close + 0.01
        candles[-1 - i].low = candles[-1 - i].close - 0.01
        candles[-1 - i].open = candles[-1 - i].close
    
    result = detect_squeeze(candles)
    assert result["state"] == "SQUEEZE_ON"
    assert result["pts"] == 0

def test_squeeze_fire():
    # Scenario: was inside, now outside -> SQUEEZE_FIRE, pts=8
    # This means the previous candle was in squeeze, but the current one is not.

    # Create candles: first 29 candles are in squeeze
    candles = create_candles(100, 29, volatility=0.005)
    for i in range(5):
        candles[-1 - i].high = candles[-1 - i].close + 0.01
        candles[-1 - i].low = candles[-1 - i].close - 0.01
        candles[-1 - i].open = candles[-1 - i].close

    # Add a candle that breaks the squeeze (e.g., high volatility)
    last_candle_close = candles[-1].close
    candles.append(Candle(ts=datetime.now().isoformat(), 
                          open=last_candle_close,
                              high=last_candle_close * 1.55,
                              low=last_candle_close * 0.95,
                              close=last_candle_close * 1.5, 
                          volume=2000))
    
    result = detect_squeeze(candles)
    assert result["state"] == "SQUEEZE_FIRE"
    assert result["pts"] == 8

def test_squeeze_none():
    # Scenario: normal volatility -> NONE
    # This means BB should not be inside KC. High volatility should achieve this.
    candles = create_candles(100, 25, volatility=0.005)
    # Generate additional candles with significant price swings to ensure no squeeze
    last_close = candles[-1].close
    for i in range(5):
        new_close = last_close + ((-1)**i) * 20.0  # Large +/- 20 price swings
        candles.append(Candle(ts=(datetime.now() + timedelta(minutes=i)).isoformat(),
                              open=last_close,
                              high=max(last_close, new_close) + 5.0,
                              low=min(last_close, new_close) - 5.0,
                              close=new_close,
                              volume=2000))
        last_close = new_close
    result = detect_squeeze(candles)
    assert result["state"] == "NONE"
    assert result["pts"] == 0

def test_short_candles():
    # Scenario: <22 candles -> graceful NONE
    candles = create_candles(100, 10) # Less than 22 candles
    result = detect_squeeze(candles)
    assert result["state"] == "NONE"
    assert result["pts"] == 0
    assert result["bb_width"] == 0.0
    assert result["kc_width"] == 0.0
