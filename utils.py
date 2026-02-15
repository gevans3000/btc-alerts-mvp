"""Minimal utilities for the standalone alert system."""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def ema(values: List[float], period: int) -> Optional[float]:
    if period <= 0 or len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = (v - e) * k + e
    return e


def rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(0, d) for d in deltas]
    losses = [abs(min(0, d)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def bollinger_bands(values: List[float], period: int = 20, multiplier: float = 2.0) -> Optional[tuple[float, float, float]]:
    if len(values) < period:
        return None
    recent = values[-period:]
    sma = sum(recent) / period
    variance = sum((x - sma) ** 2 for x in recent) / period
    std_dev = variance ** 0.5
    return (sma + multiplier * std_dev, sma, sma - multiplier * std_dev)


def atr(candles: List[Candle], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    true_ranges = []
    for i in range(1, len(candles)):
        c = candles[i]
        p = candles[i - 1]
        true_ranges.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:]) / period


def percentile_rank(values: List[float], value: float) -> Optional[float]:
    if not values:
        return None
    count = sum(1 for v in values if v <= value)
    return (count / len(values)) * 100.0
