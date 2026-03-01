import pytest
import time
from engine import compute_score
from intelligence import AlertScore, IntelligenceBundle
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from utils import Candle

def setup_mock_data(price=100.0, taker_ratio=1.0, bias_1h=0, bias_4h=0, regime="range"):
    # Create candles with specific properties
    # For bias (EMA 9 vs 21), we need to set prices accordingly
    def create_candles(p, bias):
        candles = []
        for i in range(50):
            # Increase/Decrease price to create bias
            val = p + (i * bias * 0.1)
            candles.append(Candle(ts=str(i), open=val, high=val+1, low=val-1, close=val, volume=100.0))
        return candles

    mock_candles_5m = create_candles(price, 0) # Neutral 5m
    mock_candles_1h = create_candles(price, bias_1h)
    mock_candles_4h = create_candles(price, bias_4h)
    
    mock_price = PriceSnapshot(price=price, timestamp=time.time(), source="test", healthy=True)
    mock_fg = FearGreedSnapshot(value=50, label="Neutral", healthy=True)
    mock_news = []
    mock_derivatives = DerivativesSnapshot(funding_rate=0.0, oi_change_pct=0.0, basis_pct=0.0, healthy=True)
    mock_flows = FlowSnapshot(taker_ratio=taker_ratio, long_short_ratio=1.0, crowding_score=0, healthy=True)
    mock_macro = {"dxy": mock_candles_5m, "gold": mock_candles_5m}
    
    # We need to simulate a signal (e.g. by setting raw_score high in a recipe or just hacking it)
    # Actually compute_score calculates score from many things.
    # We'll just check if blockers are added.
    
    return {
        "price": mock_price,
        "candles": mock_candles_5m,
        "candles_15m": mock_candles_5m,
        "candles_1h": mock_candles_1h,
        "candles_4h": mock_candles_4h,
        "fg": mock_fg,
        "news": mock_news,
        "derivatives": mock_derivatives,
        "flows": mock_flows,
        "macro": mock_macro
    }

def test_macro_veto_long():
    # LONG signal (simulated by bias) but 1h and 4h are bearish
    data = setup_mock_data(taker_ratio=1.5, bias_1h=-1, bias_4h=-1)
    # Force a long bias in 5m candles to trigger LONG direction
    for i in range(40, 50):
        data["candles"][i].close = 110.0
        
    score = compute_score(
        symbol="BTC", timeframe="5m", 
        price=data["price"], candles=data["candles"],
        candles_15m=data["candles_15m"], candles_1h=data["candles_1h"],
        fg=data["fg"], news=data["news"], derivatives=data["derivatives"],
        flows=data["flows"], macro=data["macro"], candles_4h=data["candles_4h"]
    )
    
    assert score.direction == "LONG"
    assert any("Macro Bearish Veto" in b for b in score.blockers)
    assert score.action == "SKIP"

def test_flow_veto_long():
    # LONG signal (by bias) but taker ratio is low
    data = setup_mock_data(taker_ratio=0.7, bias_1h=1, bias_4h=1)
    # Force a massive long bias in 5m candles to overcome taker_ratio penalty
    for i in range(50):
        data["candles"][i].close = 100.0 + i * 2.0
        data["candles"][i].high = data["candles"][i].close + 1.0
        data["candles"][i].low = data["candles"][i].close - 1.0
    
    score = compute_score(
        symbol="BTC", timeframe="5m", 
        price=data["price"], candles=data["candles"],
        candles_15m=data["candles_15m"], candles_1h=data["candles_1h"],
        fg=data["fg"], news=data["news"], derivatives=data["derivatives"],
        flows=data["flows"], macro=data["macro"], candles_4h=data["candles_4h"]
    )
    
    # Debug print if it fails
    if score.direction != "LONG":
        print(f"Score: {score.confidence}, Direction: {score.direction}, Codes: {score.reason_codes}")
        
    assert score.direction == "LONG"
    assert any("Flow Bearish Veto" in b for b in score.blockers)
    assert score.action == "SKIP"

def test_chop_filter():
    # Create very stable candles to trigger CHOP regime (low ADX, low ATR rank)
    # We need at least 40 candles for regime check
    stable_candles = []
    for i in range(60):
        stable_candles.append(Candle(ts=str(i), open=100.0, high=100.01, low=99.99, close=100.0, volume=10.0))
    
    data = setup_mock_data()
    data["candles"] = stable_candles
    data["candles_15m"] = stable_candles
    data["candles_1h"] = stable_candles
    data["candles_4h"] = stable_candles
    
    # Force a signal direction (e.g. LONG) even in chop
    data["candles"][-1].close = 100.05 
    
    score = compute_score(
        symbol="BTC", timeframe="5m", 
        price=data["price"], candles=data["candles"],
        candles_15m=data["candles_15m"], candles_1h=data["candles_1h"],
        fg=data["fg"], news=data["news"], derivatives=data["derivatives"],
        flows=data["flows"], macro=data["macro"], candles_4h=data["candles_4h"]
    )
    
    if "REGIME_CHOP" in score.reason_codes or "REGIME_VOL_CHOP" in score.reason_codes:
        assert any("Chop Zone Veto" in b for b in score.blockers)
        assert score.action == "SKIP"
    else:
        # If it didn't hit chop regime, we might need more data or more 'stability'
        print(f"Detected Regime codes: {[c for c in score.reason_codes if 'REGIME' in c]}")
        # For the purpose of this task, we want to see the veto logic working.
        # So we expect it to be in CHOP.
        assert "REGIME_CHOP" in score.reason_codes
