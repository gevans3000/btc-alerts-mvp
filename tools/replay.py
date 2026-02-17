"""Backtest-lite replay harness for deterministic alert tuning."""

from dataclasses import dataclass
from typing import Dict, List, Tuple

from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot
from engine import AlertScore, compute_score
from utils import Candle

FORWARD_BARS = {"5m": 3, "15m": 2, "1h": 1}


@dataclass
class ReplayMetrics:
    alerts: int
    trades: int
    noise_ratio: float
    directional_hit_proxy: float
    horizon_bars: int
    htf_mode: str


def _slice(candles: List[Candle], end: int) -> List[Candle]:
    return candles[: max(40, end)]


def _aggregate(candles: List[Candle], factor: int) -> List[Candle]:
    if factor <= 1:
        return candles
    out: List[Candle] = []
    for i in range(0, len(candles), factor):
        chunk = candles[i : i + factor]
        if len(chunk) < factor:
            continue
        out.append(
            Candle(
                ts=chunk[-1].ts,
                open=chunk[0].open,
                high=max(c.high for c in chunk),
                low=min(c.low for c in chunk),
                close=chunk[-1].close,
                volume=sum(c.volume for c in chunk),
            )
        )
    return out


def _context_streams(candles_5m: List[Candle]) -> Tuple[List[Candle], List[Candle]]:
    """Generates 15m and 1h context streams from a 5m source."""
    return _aggregate(candles_5m, 3), _aggregate(candles_5m, 12)


def replay_symbol_timeframe(symbol: str, timeframe: str, candles_5m: List[Candle]) -> ReplayMetrics:
    factors = {"5m": 1, "15m": 3, "1h": 12}
    factor = factors.get(timeframe, 1)
    
    if len(candles_5m) < (50 * factor):
        return ReplayMetrics(0, 0, 0.0, 0.0, FORWARD_BARS.get(timeframe, 1), "aggregated")

    fg = FearGreedSnapshot(50, "Neutral", healthy=False)
    deriv = DerivativesSnapshot(0.0, 0.0, 0.0, healthy=False)
    flow = FlowSnapshot(1.0, 1.0, 0.0, healthy=False)

    fired: List[AlertScore] = []
    wins = 0
    horizon_bars = FORWARD_BARS.get(timeframe, 1)
    # The horizon in 5m source candles is (horizon_bars * factor)
    horizon_5m = horizon_bars * factor
    
    for i in range(50, len(candles_5m)):
        # Gating: only evaluate at the end of a candle for the target timeframe
        # i is the current 5m candle index (0-indexed)
        if (i + 1) % factor != 0:
            continue
            
        # Get the slice of 5m candles up to i (inclusive)
        c_5m = candles_5m[: i + 1]
        
        # Higher timeframe context ALWAYS derived from 5m source
        c15, c1h = _context_streams(c_5m)
        
        # The main candles for the engine must match the target timeframe
        if timeframe == "5m":
            c_main = c_5m
        elif timeframe == "15m":
            c_main = c15
        elif timeframe == "1h":
            c_main = c1h
        else:
            c_main = c_5m
            
        if len(c_main) < 30: # Ensure enough history for indicators
            continue

        px = PriceSnapshot(price=c_main[-1].close, timestamp=0, source="replay", healthy=True)
        score = compute_score(
            symbol, timeframe, px, c_main, c15, c1h, 
            fg, [], deriv, flow, 
            {"spx": c_5m, "vix": c_5m, "nq": c_5m} # Use 5m for macro proxy
        )
        
        if score.action == "SKIP":
            continue
            
        fired.append(score)
        
        # Check forward performance in source (5m) resolution for higher accuracy
        # but relative to the end of the timeframe bar
        if i + horizon_5m < len(candles_5m):
            fwd = candles_5m[i + horizon_5m].close - candles_5m[i].close
            if (score.direction == "LONG" and fwd > 0) or (score.direction == "SHORT" and fwd < 0):
                wins += 1

    alerts = len(fired)
    trades = sum(1 for a in fired if a.action == "TRADE")
    noise_ratio = 0.0 if alerts == 0 else round((alerts - trades) / alerts, 4)
    hit = 0.0 if alerts == 0 else round(wins / alerts, 4)
    return ReplayMetrics(alerts, trades, noise_ratio, hit, horizon_bars, "aggregated")


def summarize(metrics: Dict[str, ReplayMetrics]) -> dict:
    return {
        k: {
            "alerts": v.alerts,
            "trades": v.trades,
            "noise_ratio": v.noise_ratio,
            "directional_hit_proxy": v.directional_hit_proxy,
            "horizon_bars": v.horizon_bars,
            "htf_mode": v.htf_mode,
        }
        for k, v in metrics.items()
    }
