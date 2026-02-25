from typing import List, Dict, Tuple
from utils import (
    Candle,
    donchian_break,
    ema as ema_calc,
    rsi,
    vwap,
    zscore,
    rsi_divergence,
    candle_patterns,
    bollinger_bands,
)
from config import DETECTORS, SESSION_WEIGHTS

def _detector_candidates(candles: List[Candle]) -> Tuple[Dict[str, int], List[str], List[str]]:
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return {"NONE": 0}, [], []

    candidates: Dict[str, int] = {}
    codes: List[str] = []
    reasons: List[str] = []

    div_type, div_strength = rsi_divergence(candles)
    if div_type == "bullish":
        candidates["DIVERGENCE_LONG"] = 14
        codes.append("RSI_DIVERGENCE")
    elif div_type == "bearish":
        candidates["DIVERGENCE_SHORT"] = -14
        codes.append("RSI_DIVERGENCE")

    patterns = candle_patterns(candles)
    for name, direction in patterns:
        bias = 6 if direction == "bullish" else -6
        candidates[f"{name.upper()}_{direction.upper()}"] = bias
        codes.append(f"{name.upper()}_{direction[:4].upper()}")

    lookback = DETECTORS["donchian_lookback"]
    up_break, dn_break = donchian_break(candles, lookback)
    if up_break:
        candidates["BREAKOUT_LONG"] = 12
        codes.append("DONCHIAN_BREAK")
    if dn_break:
        candidates["BREAKOUT_SHORT"] = -12
        codes.append("DONCHIAN_BREAK")

    z = zscore(closes, DETECTORS["zscore_period"]) or 0.0
    rrsi = rsi(closes, DETECTORS["rsi_period"]) or 50.0
    if abs(z) > DETECTORS["zscore_extreme"]:
        if z < 0 and rrsi < DETECTORS["rsi_oversold"]:
            candidates["MEAN_REVERSION_LONG"] = 10
            codes.append("ZSCORE_EXTREME")
        if z > 0 and rrsi > DETECTORS["rsi_overbought"]:
            candidates["MEAN_REVERSION_SHORT"] = -10
            codes.append("ZSCORE_EXTREME")

    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    rvwap = vwap(candles[-288:])
    if e9 and e21 and rvwap:
        if e9 > e21 and closes[-1] > rvwap:
            candidates["TREND_CONTINUATION_LONG"] = 9
            codes.append("VWAP_RECLAIM")
        if e9 < e21 and closes[-1] < rvwap:
            candidates["TREND_CONTINUATION_SHORT"] = -9
            codes.append("VWAP_REJECT")

    bb = bollinger_bands(closes, 20, 2)
    if bb and closes[-1] > bb[0]:
        candidates["VOLATILITY_EXPANSION_LONG"] = 6
        codes.append("BB_EXPANSION")
    elif bb and closes[-1] < bb[2]:
        candidates["VOLATILITY_EXPANSION_SHORT"] = -6
        codes.append("BB_EXPANSION")
    if any(v > 0 for v in candidates.values()):
        reasons.append("Momentum supports LONG setup")
    if any(v < 0 for v in candidates.values()):
        reasons.append("Momentum supports SHORT setup")

    return candidates, reasons, codes

def _arbitrate_candidates(candidates: Dict[str, int], htf_bias: int, session: str) -> Tuple[float, str, List[str], float]:
    if not candidates:
        return 0.0, "NONE", [], 0.0
    long_side = {k: v for k, v in candidates.items() if v > 0}
    short_side = {k: v for k, v in candidates.items() if v < 0}
    codes: List[str] = []
    penalty = 0.0
    if long_side and short_side:
        codes.append("CONFLICT_SUPPRESSED")
        penalty = -4.0
    
    max_abs = max(abs(v) for v in candidates.values())
    tied = [(k, v) for k, v in candidates.items() if abs(v) == max_abs]
    
    if len(tied) == 1:
        pick_key, pick_val = tied[0]
    else:
        aligned = [(k, v) for k, v in tied if (v > 0 and htf_bias > 0) or (v < 0 and htf_bias < 0)]
        if len(aligned) >= 1:
            pick_key, pick_val = aligned[0]
            codes.append("ARBITRATION_HTF_TIEBREAK")
        else:
            codes.append("ARBITRATION_TIE_NEUTRAL")
            return 0.0, "NONE", codes, penalty - 2.0
            
    strategy = pick_key.replace("_LONG", "").replace("_SHORT", "")
    if strategy in ["DIVERGENCE", "ENGULFING", "PIN"]:
        strategy = "TREND_CONTINUATION"
        for k, v in tied:
            base = k.replace("_LONG", "").replace("_SHORT", "")
            if base in ["BREAKOUT", "MEAN_REVERSION", "TREND_CONTINUATION", "VOLATILITY_EXPANSION"]:
                strategy = base
                break
    
    weight = SESSION_WEIGHTS.get(session, {"default": 1.0}).get(strategy, 1.0)
    adjusted_pts = float(pick_val * weight)
    if weight > 1.0: codes.append("SESSION_BOOST")
    elif weight < 1.0: codes.append("SESSION_PENALTY")

    return adjusted_pts, strategy, codes, penalty
