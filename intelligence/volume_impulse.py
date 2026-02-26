"""Volume impulse detector and micro-volatility regime."""
from typing import List, Dict, Any
from utils import Candle, atr, percentile_rank
import logging

logger = logging.getLogger(__name__)


def detect_volume_impulse(candles: List[Candle], vol_lookback: int = 20, spike_mult: float = 2.0, atr_lookback: int = 50) -> Dict[str, Any]:
    """
    1. Volume impulse: current candle volume vs rolling average.
    2. ATR percentile: current ATR rank over history for regime flag.

    Returns:
        {
            "rvol": float,              # Relative volume (current / avg)
            "is_spike": bool,
            "atr_percentile": float,    # 0–100
            "vol_regime": "low" | "normal" | "expansion",
            "codes": [],
            "pts": float
        }
    """
    if len(candles) < vol_lookback + 5:
        return {"rvol": 1.0, "is_spike": False, "atr_percentile": 50, "vol_regime": "normal", "codes": [], "pts": 0}

    volumes = [c.volume for c in candles[-(vol_lookback + 1):-1]]
    avg_vol = sum(volumes) / len(volumes) if volumes else 1.0
    current_vol = candles[-1].volume
    rvol = current_vol / max(avg_vol, 1e-9)
    is_spike = rvol >= spike_mult

    # ATR percentile
    atr_series = []
    for i in range(20, min(len(candles), atr_lookback + 20)):
        a = atr(candles[:i], 14)
        if a is not None:
            atr_series.append(a)
    current_atr = atr(candles, 14) or 0.0
    atr_pct = percentile_rank(atr_series, current_atr) if atr_series else 50.0

    if atr_pct >= 80:
        vol_regime = "expansion"
    elif atr_pct <= 20:
        vol_regime = "low"
    else:
        vol_regime = "normal"

    codes = []
    pts = 0.0

    if is_spike:
        codes.append("VOLUME_IMPULSE")
        pts += 2.0  # Neutral — direction determined by price action context
    if vol_regime == "expansion":
        codes.append("VOL_REGIME_EXPANSION")
    elif vol_regime == "low":
        codes.append("VOL_REGIME_LOW")

    return {
        "rvol": round(rvol, 2), "is_spike": is_spike,
        "atr_percentile": round(atr_pct, 1), "vol_regime": vol_regime,
        "codes": codes, "pts": pts,
    }
