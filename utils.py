"""Minimal utilities for the standalone alert system."""
from dataclasses import dataclass
from math import sqrt
from typing import List, Optional, Tuple


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


def rsi_divergence(candles: List[Candle], period: int = 14, lookback: int = 30) -> Tuple[Optional[str], float]:
    if len(candles) < lookback + period:
        return None, 0.0

    closes = [c.close for c in candles]
    rsis = []
    for i in range(len(candles) - lookback - 1, len(candles)):
        val = rsi(closes[: i + 1], period)
        rsis.append(val if val is not None else 50.0)

    def find_swings(data: List[float], start_idx: int, is_low: bool):
        swings = []
        for i in range(len(data) - 2, 1, -1):
            if is_low:
                if data[i] < data[i - 1] and data[i] < data[i + 1]:
                    swings.append(i)
            else:
                if data[i] > data[i - 1] and data[i] > data[i + 1]:
                    swings.append(i)
            if len(swings) >= 2:
                break
        return swings

    price_recent = closes[-lookback:]
    rsi_recent = rsis[-lookback:]

    lows = find_swings(price_recent, lookback, True)
    if len(lows) >= 2:
        i2, i1 = lows[0], lows[1]
        if price_recent[i2] < price_recent[i1] and rsi_recent[i2] > rsi_recent[i1]:
            return "bullish", rsi_recent[i2] - rsi_recent[i1]

    highs = find_swings(price_recent, lookback, False)
    if len(highs) >= 2:
        i2, i1 = highs[0], highs[1]
        if price_recent[i2] > price_recent[i1] and rsi_recent[i2] < rsi_recent[i1]:
            return "bearish", rsi_recent[i1] - rsi_recent[i2]

    return None, 0.0


def is_engulfing(candles: List[Candle]) -> Optional[str]:
    if len(candles) < 3:
        return None
    c1, c2 = candles[-3], candles[-2]
    c1_high_body = max(c1.open, c1.close)
    c1_low_body = min(c1.open, c1.close)
    c2_high_body = max(c2.open, c2.close)
    c2_low_body = min(c2.open, c2.close)

    if c2_high_body > c1_high_body and c2_low_body < c1_low_body:
        if c2.close > c2.open:
            return "bullish"
        if c2.close < c2.open:
            return "bearish"
    return None


def is_pin_bar(candle: Candle) -> Optional[str]:
    body = abs(candle.close - candle.open)
    high_wick = candle.high - max(candle.open, candle.close)
    low_wick = min(candle.open, candle.close) - candle.low
    total_range = candle.high - candle.low
    if total_range == 0:
        return None
    if low_wick >= 2 * body and high_wick < 0.5 * body:
        return "bullish"
    if high_wick >= 2 * body and low_wick < 0.5 * body:
        return "bearish"
    return None


def candle_patterns(candles: List[Candle]) -> List[Tuple[str, str]]:
    patterns = []
    eng = is_engulfing(candles)
    if eng:
        patterns.append(("engulfing", eng))
    pin = is_pin_bar(candles[-2])
    if pin:
        patterns.append(("pin_bar", pin))
    return patterns


def volume_delta(candles: List[Candle], period: int = 20) -> Tuple[float, float]:
    if len(candles) < period:
        return 0.0, 0.0
    deltas = []
    for c in candles[-period:]:
        max_range = max(c.high - c.low, 1e-8)
        deltas.append(c.volume * (c.close - c.open) / max_range)
    return sum(deltas), deltas[-1] - deltas[0]


def swing_levels(candles: List[Candle], lookback: int = 50, tolerance: float = 0.002) -> Tuple[List[float], List[float]]:
    if len(candles) < lookback + 5:
        return [], []
    supports, resistances = [], []
    completed = candles[-lookback - 1 : -1]
    for i in range(1, len(completed) - 1):
        c, p, n = completed[i], completed[i - 1], completed[i + 1]
        if c.high > p.high and c.high > n.high:
            resistances.append(c.high)
        if c.low < p.low and c.low < n.low:
            supports.append(c.low)

    def cluster(levels: List[float]):
        if not levels:
            return []
        levels.sort()
        clustered = []
        curr = levels[0]
        for l in levels[1:]:
            if (l - curr) / curr > tolerance:
                clustered.append(curr)
                curr = l
            else:
                curr = (curr + l) / 2
        clustered.append(curr)
        return clustered

    return cluster(supports), cluster(resistances)
