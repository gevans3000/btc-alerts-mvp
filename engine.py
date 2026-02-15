from dataclasses import dataclass
from typing import List

from collectors.derivatives import DerivativesSnapshot
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from utils import Candle, atr, bollinger_bands, ema as ema_calc, percentile_rank, rsi, vwap

GROUPS = {
    "policy": {"trump": 0.0, "bitcoin reserve": 0.7, "tariff": -0.4, "regulation": -0.3},
    "macro": {"rate hike": -0.4, "rate cut": 0.4, "fed": -0.1},
    "market": {"etf": 0.2, "hack": -0.6, "adoption": 0.4},
}


@dataclass
class AlertScore:
    regime: str
    confidence: int
    reasons: List[str]
    trump_hits: str
    quality: str
    entry_zone: str
    invalidation: float
    tp1: float
    tp2: float
    rr_ratio: float
    direction: str
    time_horizon_bars: int
    lifecycle_key: str


def _trend_bias(candles: List[Candle]) -> int:
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return 0
    fast, slow = ema_calc(closes, 9), ema_calc(closes, 21)
    if fast is None or slow is None:
        return 0
    return 1 if fast > slow else -1


def _market_structure_bias(candles: List[Candle]) -> tuple[float, List[str]]:
    reasons = []
    if len(candles) < 25:
        return 0.0, reasons

    completed = candles[:-1]
    recent = completed[-20:]
    prev = completed[-21:-1]
    latest = recent[-1]
    prior_high = max(c.high for c in prev)
    prior_low = min(c.low for c in prev)
    body = abs(latest.close - latest.open)
    range_size = max(1e-6, latest.high - latest.low)
    conviction = body / range_size

    bias = 0.0
    if latest.close > prior_high and conviction > 0.55:
        bias += 12
        reasons.append(f"BOS up {prior_high:,.0f}")
    elif latest.close < prior_low and conviction > 0.55:
        bias -= 12
        reasons.append(f"BOS down {prior_low:,.0f}")

    # Fakeout logic
    if latest.high > prior_high and latest.close < prior_high:
        bias -= 8
        reasons.append(f"Failed breakout {prior_high:,.0f}")
    if latest.low < prior_low and latest.close > prior_low:
        bias += 8
        reasons.append(f"Failed breakdown reclaim {prior_low:,.0f}")

    return bias, reasons


def _spx_risk_bias(spx_candles: List[Candle]) -> tuple[float, str, bool]:
    if len(spx_candles) < 30:
        return 0.0, "SPX unavailable", False
    closes = [c.close for c in spx_candles[:-1]]
    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    last = closes[-1]
    first = closes[-13]
    momentum = ((last - first) / first) * 100 if first else 0.0
    if e9 is None or e21 is None:
        return 0.0, "SPX insufficient", False
    if e9 > e21 and momentum > 0.1:
        return 5.0, "SPX risk-on", True
    if e9 < e21 and momentum < -0.1:
        return -5.0, "SPX risk-off", True
    return 0.0, "SPX mixed", True


def compute_score(
    price: PriceSnapshot,
    candles_5m: List[Candle],
    candles_15m: List[Candle],
    candles_1h: List[Candle],
    fg: FearGreedSnapshot,
    news: List[Headline],
    derivatives: DerivativesSnapshot,
    spx_candles: List[Candle],
) -> AlertScore:
    bias, reasons, degraded = 0.0, [], []

    if not candles_5m or len(candles_5m) < 40:
        degraded.append("candles_5m")
    else:
        completed = candles_5m[:-1]
        closes = [c.close for c in completed]
        volumes = [c.volume for c in completed]
        current_price = price.price if price.healthy else closes[-1]

        r = rsi(closes, 14)
        if r is not None:
            if r < 30:
                bias += 18
                reasons.append(f"Oversold RSI ({r:.1f})")
            elif r > 70:
                bias -= 18
                reasons.append(f"Overbought RSI ({r:.1f})")

        bb = bollinger_bands(closes, 20, 2)
        widths = []
        for i in range(20, len(closes) + 1):
            sample = closes[:i]
            band = bollinger_bands(sample, 20, 2)
            if band:
                widths.append((band[0] - band[2]) / band[1] if band[1] else 0.0)
        vol_regime = "neutral"
        if bb:
            upper, _, lower = bb
            width = (upper - lower) / current_price if current_price else 0.0
            width_rank = percentile_rank(widths, width) or 50.0
            current_atr = atr(completed, 14) or 0.0
            atr_series = [atr(completed[:i], 14) or 0.0 for i in range(20, len(completed) + 1)]
            atr_rank = percentile_rank(atr_series, current_atr) or 50.0
            if width_rank < 35 and atr_rank < 40:
                vol_regime = "compression"
            elif width_rank > 65 and atr_rank > 60:
                vol_regime = "expansion"
            reasons.append(f"Vol regime: {vol_regime}")

            if current_price < lower:
                bias += 12 if vol_regime != "expansion" else 6
                reasons.append("Below lower BB")
            elif current_price > upper:
                bias -= 12 if vol_regime != "expansion" else 6
                reasons.append("Above upper BB")

        e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
        if e9 is not None and e21 is not None:
            if e9 > e21:
                bias += 8
                reasons.append("Bullish EMA 9/21")
            else:
                bias -= 8
                reasons.append("Bearish EMA 9/21")

        if len(volumes) > 20:
            avg_vol = sum(volumes[-21:-1]) / 20
            vol_mult = 1.7 if "compression" in reasons else 1.35
            if volumes[-1] > avg_vol * vol_mult:
                direction = "Buy" if closes[-1] > closes[-2] else "Sell"
                bias += 6 if direction == "Buy" else -6
                reasons.append(f"High vol {direction}")

        # VWAP Logic
        v = vwap(candles_5m[-288:])  # approx 24h
        if v:
            if current_price > v:
                bias += 4
                reasons.append("Price above VWAP")
            else:
                bias -= 4
                reasons.append("Price below VWAP")

        structure_bias, structure_reasons = _market_structure_bias(candles_5m)
        bias += structure_bias
        reasons.extend(structure_reasons)

    t15 = _trend_bias(candles_15m)
    t1h = _trend_bias(candles_1h)
    htf_bias = t15 + t1h
    if htf_bias >= 1:
        bias += 8
        reasons.append("HTF trend aligned bullish")
    elif htf_bias <= -1:
        bias -= 8
        reasons.append("HTF trend aligned bearish")
    else:
        degraded.append("htf")

    if fg.healthy:
        if fg.value < 20:
            bias += 4
            reasons.append(f"Extreme fear ({fg.value})")
        if fg.value > 80:
            bias -= 4
            reasons.append(f"Extreme greed ({fg.value})")
    else:
        degraded.append("fg")

    hits = []
    for hl in news:
        text = hl.title.lower()
        for kws in GROUPS.values():
            for keyword, weight in kws.items():
                if keyword in text:
                    hits.append(keyword)
                    bias += weight * 4

    if derivatives.healthy:
        if derivatives.oi_change_pct > 0.6 and derivatives.basis_pct > 0:
            bias += 5
            reasons.append("OI rising with positive basis")
        if derivatives.oi_change_pct > 0.6 and derivatives.funding_rate > 0.0008:
            bias -= 4
            reasons.append("Crowded longs (funding high)")
        if derivatives.oi_change_pct < -0.6 and derivatives.funding_rate < -0.0008:
            bias += 4
            reasons.append("Short squeeze setup")
    else:
        degraded.append("derivatives")

    spx_bias, spx_reason, spx_ok = _spx_risk_bias(spx_candles)
    bias += spx_bias
    reasons.append(spx_reason)
    if not spx_ok:
        degraded.append("spx")

    score = int(min(100, max(0, 50 + bias)))
    regime = "sideways / no signal"
    direction = "NEUTRAL"

    if score >= 68:
        regime = "long_signal"
        direction = "LONG"
    elif score <= 32:
        regime = "short_signal"
        direction = "SHORT"
    elif score >= 56:
        regime = "bullish_bias"
        direction = "LONG"
    elif score <= 44:
        regime = "bearish_bias"
        direction = "SHORT"

    # downgrade hard signals when HTF mismatch
    if regime == "long_signal" and htf_bias < 0 and score < 78:
        regime = "bullish_bias"
        reasons.append("Long blocked by HTF mismatch")
    if regime == "short_signal" and htf_bias > 0 and score > 22:
        regime = "bearish_bias"
        reasons.append("Short blocked by HTF mismatch")

    completed = candles_5m[:-1] if len(candles_5m) > 1 else candles_5m
    px = price.price or (completed[-1].close if completed else 0.0)
    if px <= 0:
        px = 1.0
    local_atr = atr(completed, 14) or max(1.0, px * 0.002)
    
    rr_ratio = 0.0
    if direction == "LONG":
        invalidation = px - (1.2 * local_atr)
        tp1 = px + (1.5 * local_atr)  # Improved R:R
        tp2 = px + (2.5 * local_atr)
        risk = px - invalidation
        reward = tp1 - px
        rr_ratio = reward / risk if risk > 0 else 0.0
    elif direction == "SHORT":
        invalidation = px + (1.2 * local_atr)
        tp1 = px - (1.5 * local_atr)
        tp2 = px - (2.5 * local_atr)
        risk = invalidation - px
        reward = px - tp1
        rr_ratio = reward / risk if risk > 0 else 0.0
    else:
        # Neutral / Sideways
        invalidation = 0.0
        tp1 = 0.0
        tp2 = 0.0
        rr_ratio = 0.0

    trump = ", ".join(sorted(set(k for k in hits if k in GROUPS["policy"])))
    key = f"{regime}:{direction}:{int(px)}"

    return AlertScore(
        regime=regime,
        confidence=score,
        reasons=reasons[:7],
        trump_hits=trump,
        quality="ok" if not degraded else f"degraded:{','.join(sorted(set(degraded)))}",
        entry_zone=f"{px - 0.1 * local_atr:,.0f}-{px + 0.1 * local_atr:,.0f}" if direction != "NEUTRAL" else "-",
        invalidation=invalidation,
        tp1=tp1,
        tp2=tp2,
        rr_ratio=rr_ratio,
        direction=direction,
        time_horizon_bars=8,
        lifecycle_key=key,
    )
