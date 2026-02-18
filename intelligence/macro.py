from typing import Dict, List, Any
from utils import Candle, rsi

def analyze_macro_correlation(
    btc_candles: List[Candle],
    macro_context: Dict[str, List[Candle]],
) -> Dict[str, Any]:
    """
    Analyzes macro correlation with BTC using DXY, Gold, and SPX.
    """
    # Default values
    macro_data = {
        "spx_correlation": 0.0,
        "dxy_correlation": 0.0,
        "gold_correlation": 0.0,
        "btc_rsi": 0.0,
        "spx_rsi": 0.0,
        "dxy_rsi": 0.0,
        "gold_rsi": 0.0,
        "pts": 0.0,
        "reasons": [],
        "codes": []
    }

    # Helper to calculate closes and RSI
    def get_closes_and_rsi(candles: List[Candle], period: int = 14):
        if not candles or len(candles) < period + 1:
            return [], 0.0
        closes = [c.close for c in candles]
        return closes, rsi(closes, period) or 0.0

    # Get BTC data
    btc_closes, btc_rsi_val = get_closes_and_rsi(btc_candles)
    macro_data["btc_rsi"] = btc_rsi_val

    # Get SPX data
    spx_candles = macro_context.get("spx", [])
    spx_closes, spx_rsi_val = get_closes_and_rsi(spx_candles)
    macro_data["spx_rsi"] = spx_rsi_val

    # Get DXY data
    dxy_candles = macro_context.get("dxy", [])
    dxy_closes, dxy_rsi_val = get_closes_and_rsi(dxy_candles)
    macro_data["dxy_rsi"] = dxy_rsi_val

    # Get Gold data
    gold_candles = macro_context.get("gold", [])
    gold_closes, gold_rsi_val = get_closes_and_rsi(gold_candles)
    macro_data["gold_rsi"] = gold_rsi_val

    # Calculate correlations (simple approach for now, could use more advanced methods)
    # For simplicity, we'll use a basic comparison for trend alignment
    pts = 0.0
    reasons = []
    codes = []

    # SPX correlation (positive) - Using RSI for trend comparison
    if btc_rsi_val > 50 and spx_rsi_val > 50:
        pts += 3.0
        reasons.append("BTC and SPX showing bullish momentum")
        codes.append("MACRO_SPX_BULL")
    elif btc_rsi_val < 50 and spx_rsi_val < 50:
        pts -= 3.0
        reasons.append("BTC and SPX showing bearish momentum")
        codes.append("MACRO_SPX_BEAR")
    
    # DXY correlation (negative) - Using RSI for trend comparison
    if btc_rsi_val > 50 and dxy_rsi_val < 50:
        pts += 3.0
        reasons.append("BTC bullish momentum, DXY bearish momentum")
        codes.append("MACRO_DXY_BULL_BTC")
    elif btc_rsi_val < 50 and dxy_rsi_val > 50:
        pts -= 3.0
        reasons.append("BTC bearish momentum, DXY bullish momentum")
        codes.append("MACRO_DXY_BEAR_BTC")

    # Gold correlation (mixed/safe haven) - Using RSI for trend comparison
    # Gold can be a safe haven, so positive correlation with BTC could be seen as risk-on
    # or negative correlation as flight to safety. Let's assume a slight positive bias for risk-on.
    if btc_rsi_val > 50 and gold_rsi_val > 50:
        pts += 1.0
        reasons.append("BTC and Gold showing bullish momentum (risk-on)")
        codes.append("MACRO_GOLD_BULL")
    elif btc_rsi_val < 50 and gold_rsi_val < 50:
        pts -= 1.0
        reasons.append("BTC and Gold showing bearish momentum")
        codes.append("MACRO_GOLD_BEAR")

    macro_data["pts"] = pts
    macro_data["reasons"] = reasons
    macro_data["codes"] = codes

    return macro_data