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


def _context_streams(candles: List[Candle], timeframe: str) -> Tuple[List[Candle], List[Candle], str]:
    if timeframe == "5m":
        return _aggregate(candles, 3), _aggregate(candles, 12), "aggregated"
    if timeframe == "15m":
        return candles, _aggregate(candles, 4), "aggregated"
    return candles, candles, "native"


def replay_symbol_timeframe(symbol: str, timeframe: str, candles: List[Candle]) -> ReplayMetrics:
    if len(candles) < 60:
        return ReplayMetrics(0, 0, 0.0, 0.0, FORWARD_BARS.get(timeframe, 1), "native")

    fg = FearGreedSnapshot(50, "Neutral", healthy=False)
    deriv = DerivativesSnapshot(0.0, 0.0, 0.0, healthy=False)
    flow = FlowSnapshot(1.0, 1.0, 0.0, healthy=False)

    fired: List[AlertScore] = []
    wins = 0
    horizon = FORWARD_BARS.get(timeframe, 1)
    mode = "native"
    for i in range(50, len(candles)):
        c = _slice(candles, i)
        c15, c1h, mode = _context_streams(c, timeframe)
        px = PriceSnapshot(price=c[-1].close, timestamp=0, source="replay", healthy=True)
        score = compute_score(symbol, timeframe, px, c, c15, c1h, fg, [], deriv, flow, {"spx": c, "vix": c, "nq": c})
        if score.action == "SKIP":
            continue
        fired.append(score)
        
        # Check forward performance
        if i + horizon < len(candles):
            fwd = candles[i + horizon].close - candles[i].close
            if (score.direction == "LONG" and fwd > 0) or (score.direction == "SHORT" and fwd < 0):
                wins += 1

    alerts = len(fired)
    trades = sum(1 for a in fired if a.action == "TRADE")
    noise_ratio = 0.0 if alerts == 0 else round((alerts - trades) / alerts, 4)
    hit = 0.0 if alerts == 0 else round(wins / alerts, 4)
    return ReplayMetrics(alerts, trades, noise_ratio, hit, horizon, mode)


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
