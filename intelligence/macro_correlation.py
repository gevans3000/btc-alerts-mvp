"""Macro correlation: DXY and Gold vs BTC on daily timeframes."""
from typing import Dict, Any, List
from utils import Candle, ema
from config import MACRO_CORRELATION
import logging
logger = logging.getLogger(__name__)

def analyze_macro_correlation(macro: Dict[str, List[Candle]]) -> Dict[str, Any]:
    cfg = MACRO_CORRELATION
    pts, dxy_trend, gold_trend = 0, "neutral", "neutral"

    dxy = macro.get("dxy", [])
    if len(dxy) >= cfg["min_candles"]:
        closes = [c.close for c in dxy]
        e9, e21 = ema(closes, 9), ema(closes, 21)
        if e9 is not None and e21 is not None:
            if e9 < e21: dxy_trend, pts = "falling", pts + cfg["dxy_falling_pts"]
            elif e9 > e21: dxy_trend, pts = "rising", pts + cfg["dxy_rising_pts"]

    gold = macro.get("gold", [])
    if len(gold) >= cfg["min_candles"]:
        closes = [c.close for c in gold]
        e9, e21 = ema(closes, 9), ema(closes, 21)
        if e9 is not None and e21 is not None:
            if e9 > e21: gold_trend, pts = "rising", pts + cfg["gold_rising_pts"]
            elif e9 < e21: gold_trend, pts = "falling", pts + cfg["gold_falling_pts"]

    return {"dxy_trend": dxy_trend, "gold_trend": gold_trend, "pts": pts,
            "details": {"dxy_candles": len(dxy), "gold_candles": len(gold)}}
