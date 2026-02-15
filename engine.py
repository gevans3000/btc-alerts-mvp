from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
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
    tier: str
    action: str
    reasons: List[str]
    blockers: List[str]
    trump_hits: str
    quality: str
    entry_zone: str
    invalidation: float
    tp1: float
    tp2: float
    rr_ratio: float
    direction: str
    time_horizon_bars: int
    session: str
    lifecycle_key: str


def _trend_bias(candles: List[Candle]) -> int:
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return 0
    fast, slow = ema_calc(closes, 9), ema_calc(closes, 21)
    if fast is None or slow is None:
        return 0
    return 1 if fast > slow else -1


def _pivot_high(candles: List[Candle], idx: int, lb: int = 2) -> bool:
    if idx < lb or idx + lb >= len(candles):
        return False
    px = candles[idx].high
    return all(candles[idx - k].high < px and candles[idx + k].high < px for k in range(1, lb + 1))


def _pivot_low(candles: List[Candle], idx: int, lb: int = 2) -> bool:
    if idx < lb or idx + lb >= len(candles):
        return False
    px = candles[idx].low
    return all(candles[idx - k].low > px and candles[idx + k].low > px for k in range(1, lb + 1))


def _market_structure_bias(candles: List[Candle]) -> tuple[float, List[str]]:
    reasons: List[str] = []
    if len(candles) < 40:
        return 0.0, reasons

    completed = candles[:-1]
    latest = completed[-1]

    swing_highs = [c.high for i, c in enumerate(completed[-30:-2], start=len(completed) - 30) if _pivot_high(completed, i)]
    swing_lows = [c.low for i, c in enumerate(completed[-30:-2], start=len(completed) - 30) if _pivot_low(completed, i)]
    if not swing_highs or not swing_lows:
        return 0.0, reasons

    key_high = max(swing_highs[-3:])
    key_low = min(swing_lows[-3:])

    bias = 0.0
    if latest.close > key_high:
        retest_zone = [c for c in completed[-4:] if c.low <= key_high * 1.001]
        if retest_zone and latest.close > latest.open:
            bias += 14
            reasons.append(f"Confirmed break-retest above {key_high:,.0f}")
        else:
            bias += 6
            reasons.append(f"Wicky break above {key_high:,.0f}")
    elif latest.close < key_low:
        retest_zone = [c for c in completed[-4:] if c.high >= key_low * 0.999]
        if retest_zone and latest.close < latest.open:
            bias -= 14
            reasons.append(f"Confirmed break-retest below {key_low:,.0f}")
        else:
            bias -= 6
            reasons.append(f"Wicky break below {key_low:,.0f}")

    return bias, reasons


def _session_label(candles: List[Candle]) -> str:
    if not candles:
        return "unknown"
    try:
        ts = int(float(candles[-1].ts))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hour = dt.hour
        if dt.weekday() >= 5:
            return "weekend"
        if 0 <= hour < 8:
            return "asia"
        if 8 <= hour < 13:
            return "europe"
        return "us"
    except Exception:
        return "unknown"


def _macro_risk_bias(macro: Dict[str, List[Candle]]) -> tuple[float, str, List[str]]:
    degraded: List[str] = []
    score = 0.0

    spx = macro.get("spx", [])
    if len(spx) >= 30:
        closes = [c.close for c in spx[:-1]]
        e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
        if e9 and e21:
            score += 4 if e9 > e21 else -4
    else:
        degraded.append("spx")

    vix = macro.get("vix", [])
    if len(vix) >= 14:
        v_closes = [c.close for c in vix[:-1]]
        if v_closes[-1] < v_closes[-13]:
            score += 3
        else:
            score -= 3
    else:
        degraded.append("vix")

    nq = macro.get("nq", [])
    if len(nq) >= 30:
        n_closes = [c.close for c in nq[:-1]]
        e9, e21 = ema_calc(n_closes, 9), ema_calc(n_closes, 21)
        if e9 and e21:
            score += 2 if e9 > e21 else -2
    else:
        degraded.append("nq")

    reason = "Macro risk-on" if score > 1 else "Macro risk-off" if score < -1 else "Macro mixed"
    return score, reason, degraded


def _tier_and_action(score: int, blockers: List[str]) -> tuple[str, str]:
    if blockers:
        return "NO-TRADE", "SKIP"
    if score >= 74 or score <= 26:
        return "A+", "TRADE"
    if score >= 58 or score <= 42:
        return "B", "WATCH"
    return "NO-TRADE", "SKIP"


def compute_score(
    price: PriceSnapshot,
    candles_5m: List[Candle],
    candles_15m: List[Candle],
    candles_1h: List[Candle],
    fg: FearGreedSnapshot,
    news: List[Headline],
    derivatives: DerivativesSnapshot,
    flows: FlowSnapshot,
    macro: Dict[str, List[Candle]],
) -> AlertScore:
    bias, reasons, degraded, blockers = 0.0, [], [], []

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
                bias += 16
                reasons.append(f"Oversold RSI ({r:.1f})")
            elif r > 70:
                bias -= 16
                reasons.append(f"Overbought RSI ({r:.1f})")

        bb = bollinger_bands(closes, 20, 2)
        if bb:
            upper, _, lower = bb
            width_series = []
            for i in range(20, len(closes) + 1):
                b = bollinger_bands(closes[:i], 20, 2)
                if b:
                    width_series.append((b[0] - b[2]) / b[1] if b[1] else 0)
            width = (upper - lower) / current_price if current_price else 0.0
            width_rank = percentile_rank(width_series, width) or 50.0
            reasons.append("Vol regime: compression" if width_rank < 35 else "Vol regime: expansion" if width_rank > 65 else "Vol regime: neutral")
            if current_price < lower:
                bias += 10
            elif current_price > upper:
                bias -= 10

        e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
        if e9 is not None and e21 is not None:
            bias += 8 if e9 > e21 else -8
            reasons.append("Bullish EMA 9/21" if e9 > e21 else "Bearish EMA 9/21")

        if len(volumes) > 20:
            avg_vol = sum(volumes[-21:-1]) / 20
            if volumes[-1] > avg_vol * 1.35:
                bias += 5 if closes[-1] > closes[-2] else -5
                reasons.append("Volume expansion")

        v = vwap(candles_5m[-288:])
        if v:
            bias += 4 if current_price > v else -4

        structure_bias, structure_reasons = _market_structure_bias(candles_5m)
        bias += structure_bias
        reasons.extend(structure_reasons)

    session = _session_label(candles_5m)
    session_shift = {"asia": 2, "europe": 0, "us": 0, "weekend": -4, "unknown": -1}.get(session, -1)
    bias += session_shift
    reasons.append(f"Session: {session}")

    t15 = _trend_bias(candles_15m)
    t1h = _trend_bias(candles_1h)
    htf_bias = t15 + t1h
    if htf_bias >= 1:
        bias += 8
    elif htf_bias <= -1:
        bias -= 8
    else:
        degraded.append("htf")

    if fg.healthy:
        if fg.value < 20:
            bias += 4
        if fg.value > 80:
            bias -= 4
    else:
        degraded.append("fg")

    hits = []
    for hl in news:
        text = hl.title.lower()
        for kws in GROUPS.values():
            for keyword, weight in kws.items():
                if keyword in text:
                    hits.append(keyword)
                    bias += weight * 3

    if derivatives.healthy:
        if derivatives.oi_change_pct > 0.6 and derivatives.basis_pct > 0:
            bias += 5
            reasons.append("OI rising with positive basis")
        if derivatives.funding_rate > 0.0012 and derivatives.oi_change_pct > 0.8:
            bias -= 6
            reasons.append("Crowded longs")
        if derivatives.funding_rate < -0.0012 and derivatives.oi_change_pct > 0.8:
            bias += 6
            reasons.append("Crowded shorts")
    else:
        degraded.append("derivatives")

    if flows.healthy:
        if flows.crowding_score > 5:
            bias -= 5
            reasons.append("Long crowding risk")
        if flows.crowding_score < -5:
            bias += 5
            reasons.append("Short crowding risk")
    else:
        degraded.append("flows")

    macro_bias, macro_reason, macro_degraded = _macro_risk_bias(macro)
    bias += macro_bias
    reasons.append(macro_reason)
    degraded.extend(macro_degraded)

    score = int(min(100, max(0, 50 + bias)))
    regime = "sideways / no signal"
    direction = "NEUTRAL"
    if score >= 68:
        regime, direction = "long_signal", "LONG"
    elif score <= 32:
        regime, direction = "short_signal", "SHORT"
    elif score >= 56:
        regime, direction = "bullish_bias", "LONG"
    elif score <= 44:
        regime, direction = "bearish_bias", "SHORT"

    completed = candles_5m[:-1] if len(candles_5m) > 1 else candles_5m
    px = price.price or (completed[-1].close if completed else 1.0)
    local_atr = atr(completed, 14) or max(1.0, px * 0.002)

    if direction == "LONG":
        invalidation = px - (1.2 * local_atr)
        tp1 = px + (1.5 * local_atr)
        tp2 = px + (2.5 * local_atr)
        rr_ratio = (tp1 - px) / (px - invalidation) if px > invalidation else 0.0
    elif direction == "SHORT":
        invalidation = px + (1.2 * local_atr)
        tp1 = px - (1.5 * local_atr)
        tp2 = px - (2.5 * local_atr)
        rr_ratio = (px - tp1) / (invalidation - px) if invalidation > px else 0.0
    else:
        invalidation = tp1 = tp2 = rr_ratio = 0.0

    if rr_ratio < 1.2 and direction != "NEUTRAL":
        blockers.append("Low R:R")
    if direction == "LONG" and htf_bias < 0:
        blockers.append("HTF conflict")
    if direction == "SHORT" and htf_bias > 0:
        blockers.append("HTF conflict")
    if len(set(degraded)) >= 3:
        blockers.append("Data quality degraded")

    tier, action = _tier_and_action(score, blockers)
    trump = ", ".join(sorted(set(k for k in hits if k in GROUPS["policy"])))
    key = f"{regime}:{tier}:{action}:{int(px)}"

    return AlertScore(
        regime=regime,
        confidence=score,
        tier=tier,
        action=action,
        reasons=reasons[:7],
        blockers=blockers,
        trump_hits=trump,
        quality="ok" if not degraded else f"degraded:{','.join(sorted(set(degraded)))}",
        entry_zone=f"{px - 0.1 * local_atr:,.0f}-{px + 0.1 * local_atr:,.0f}" if direction != "NEUTRAL" else "-",
        invalidation=invalidation,
        tp1=tp1,
        tp2=tp2,
        rr_ratio=rr_ratio,
        direction=direction,
        time_horizon_bars=8,
        session=session,
        lifecycle_key=key,
    )
