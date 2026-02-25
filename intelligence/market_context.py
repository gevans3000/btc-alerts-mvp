import time
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from utils import ema as ema_calc, adx, atr, percentile_rank, Candle
from config import REGIME, STALE_SECONDS

def _session_label(candles: List[Candle]) -> str:
    if not candles:
        return "unknown"
    try:
        dt = datetime.fromtimestamp(int(float(candles[-1].ts)), tz=timezone.utc)
        if 0 <= dt.weekday() < 5:
            if 20 <= dt.hour < 22:
                return "dead_zone"
        if dt.weekday() >= 5:
            return "weekend"
        if 0 <= dt.hour < 8:
            return "asia"
        if 8 <= dt.hour < 13:
            return "europe"
        return "us"
    except Exception:
        return "unknown"

def _vix_bias(macro: Dict[str, List[Candle]]) -> Tuple[float, List[str], List[str]]:
    vix = macro.get("vix", [])
    if len(vix) < 13:
        return 0.0, [], []
    
    reasons, codes = [], []
    vix_closes = [c.close for c in vix]
    vix_change = (vix_closes[-1] - vix_closes[-12]) / max(vix_closes[-12], 1e-8)
    
    if vix_change > 0.05:
        reasons.append("VIX spiking, risk-off")
        codes.append("VIX_SPIKE")
        return -4.0, reasons, codes
    
    if vix_closes[-1] > 30:
        codes.append("VIX_EXTREME")
        return -1.0, ["VIX extremely high"], codes
        
    return 0.0, [], []

def _trend_bias(candles: List[Candle]) -> int:
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return 0
    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    if e9 is None or e21 is None:
        return 0
    return 1 if e9 > e21 else -1

def _macro_risk_bias(macro: Dict[str, List[Candle]]) -> Tuple[float, List[str]]:
    reasons, score = [], 0.0
    spx = macro.get("spx", [])
    if len(spx) >= 30:
        closes = [c.close for c in spx[:-1]]
        e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
        if e9 and e21 and e9 > e21:
            score += 4.0
            reasons.append("MACRO_RISK_ON")
    return score, reasons

def _calculate_raw_regime(candles: List[Candle]) -> str:
    closes = [c.close for c in candles[:-1]]
    if len(candles) < 30:
        return "range"
    adx_v = adx(candles, 14) or 18
    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    slope = (e9 - e21) / e21 if e9 and e21 else 0.0
    local_atr = atr(candles[:-1], 14) or 0.0
    atr_series = [atr(candles[:i], 14) for i in range(20, len(candles))]
    atr_clean = [x for x in atr_series if x is not None]
    rank = percentile_rank(atr_clean, local_atr) if atr_clean else 50.0
    
    if adx_v > REGIME["adx_trend"] and abs(slope) > REGIME["slope_trend"]:
        return "trend"
    if rank > REGIME["atr_rank_chop"] and adx_v < REGIME["adx_chop"]:
        return "vol_chop"
    if adx_v < REGIME.get("adx_low", 20) and rank < REGIME.get("atr_rank_low", 30):
        return "chop"
    return "range"

def _regime(candles: List[Candle]) -> Tuple[str, float, List[str]]:
    if len(candles) < 35:
        r = _calculate_raw_regime(candles)
        return r, 0.0, [f"REGIME_{r.upper()}"]
        
    r1 = _calculate_raw_regime(candles)
    r2 = _calculate_raw_regime(candles[:-1])
    r3 = _calculate_raw_regime(candles[:-2])
    
    if r1 == r2 == r3:
        final_regime = r1
    elif r2 == r3:
        final_regime = r2
    else:
        final_regime = "range"

    pts = 0.0
    if final_regime == "trend":
        pts = 8.0
    elif final_regime == "vol_chop":
        pts = -8.0
    elif final_regime == "chop":
        pts = -15.0
    else:
        pts = -2.0
        
    return final_regime, pts, [f"REGIME_{final_regime.upper()}"]

def _is_stale(candles: List[Candle], timeframe: str) -> bool:
    if not candles:
        return True
    max_age_seconds = STALE_SECONDS.get(timeframe, STALE_SECONDS["5m"])
    try:
        last_ts = int(float(candles[-1].ts))
    except (TypeError, ValueError):
        return True
    return (time.time() - last_ts) > max_age_seconds
