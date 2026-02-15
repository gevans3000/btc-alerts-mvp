"""Minimal utilities for the standalone alert system."""
from dataclasses import dataclass
from math import sqrt
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


def adx(candles: List[Candle], period: int = 14) -> Optional[float]:
    if len(candles) < period + 2:
        return None
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        up_move = c.high - p.high
        down_move = p.low - c.low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        trs.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
    tr_smooth = sum(trs[:period])
    p_dm_smooth = sum(plus_dm[:period])
    m_dm_smooth = sum(minus_dm[:period])
    dxs = []
    for i in range(period, len(trs)):
        tr_smooth = tr_smooth - (tr_smooth / period) + trs[i]
        p_dm_smooth = p_dm_smooth - (p_dm_smooth / period) + plus_dm[i]
        m_dm_smooth = m_dm_smooth - (m_dm_smooth / period) + minus_dm[i]
        pdi = (100 * p_dm_smooth / tr_smooth) if tr_smooth else 0.0
        mdi = (100 * m_dm_smooth / tr_smooth) if tr_smooth else 0.0
        dxs.append((100 * abs(pdi - mdi) / (pdi + mdi)) if (pdi + mdi) else 0.0)
    if not dxs:
        return None
    return sum(dxs[-period:]) / min(period, len(dxs))


def percentile_rank(values: List[float], value: float) -> Optional[float]:
    if not values:
        return None
    count = sum(1 for v in values if v <= value)
    return (count / len(values)) * 100.0


def zscore(values: List[float], period: int = 20) -> Optional[float]:
    if len(values) < period:
        return None
    recent = values[-period:]
    mu = sum(recent) / period
    variance = sum((x - mu) ** 2 for x in recent) / period
    sigma = sqrt(variance)
    return (recent[-1] - mu) / sigma if sigma > 0 else 0.0


def donchian_break(candles: List[Candle], lookback: int = 20) -> tuple[bool, bool]:
    if len(candles) < lookback + 2:
        return False, False
    completed = candles[:-1]
    high = max(c.high for c in completed[-lookback:])
    low = min(c.low for c in completed[-lookback:])
    close = completed[-1].close
    return close > high, close < low


def vwap(candles: List[Candle]) -> Optional[float]:
    if not candles:
        return None
    cum_pv = 0.0
    cum_vol = 0.0
    for c in candles:
        typical = (c.high + c.low + c.close) / 3
        cum_pv += typical * c.volume
        cum_vol += c.volume
    return cum_pv / cum_vol if cum_vol > 0 else None
