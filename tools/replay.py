"""Backtest-lite replay harness for deterministic alert tuning."""

from dataclasses import dataclass
from typing import Dict, List

from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot
from engine import AlertScore, compute_score
from utils import Candle


@dataclass
class ReplayMetrics:
    alerts: int
    trades: int
    noise_ratio: float
    directional_hit_proxy: float


def _slice(candles: List[Candle], end: int) -> List[Candle]:
    return candles[: max(40, end)]


def replay_symbol_timeframe(symbol: str, timeframe: str, candles: List[Candle]) -> ReplayMetrics:
    if len(candles) < 60:
        return ReplayMetrics(0, 0, 0.0, 0.0)

    fg = FearGreedSnapshot(50, "Neutral", healthy=False)
    deriv = DerivativesSnapshot(0.0, 0.0, 0.0, healthy=False)
    flow = FlowSnapshot(1.0, 1.0, 0.0, healthy=False)

    fired: List[AlertScore] = []
    wins = 0
    for i in range(50, len(candles)):
        c = _slice(candles, i)
        px = PriceSnapshot(price=c[-1].close, timestamp=0, source="replay", healthy=True)
        score = compute_score(symbol, timeframe, px, c, c, c, fg, [], deriv, flow, {"spx": c, "vix": c, "nq": c})
        if score.action == "SKIP":
            continue
        fired.append(score)
        if i + 3 < len(candles):
            fwd = candles[i + 3].close - candles[i].close
            if (score.direction == "LONG" and fwd > 0) or (score.direction == "SHORT" and fwd < 0):
                wins += 1

    alerts = len(fired)
    trades = sum(1 for a in fired if a.action == "TRADE")
    noise_ratio = 0.0 if alerts == 0 else round((alerts - trades) / alerts, 4)
    hit = 0.0 if alerts == 0 else round(wins / alerts, 4)
    return ReplayMetrics(alerts, trades, noise_ratio, hit)


def summarize(metrics: Dict[str, ReplayMetrics]) -> dict:
    return {
        k: {
            "alerts": v.alerts,
            "trades": v.trades,
            "noise_ratio": v.noise_ratio,
            "directional_hit_proxy": v.directional_hit_proxy,
        }
        for k, v in metrics.items()
    }
