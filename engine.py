from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from utils import Candle, adx, atr, bollinger_bands, donchian_break, ema as ema_calc, percentile_rank, rsi, vwap, zscore

GROUPS = {
    "policy": {"trump": 0.0, "bitcoin reserve": 0.7, "tariff": -0.4, "regulation": -0.3},
    "macro": {"rate hike": -0.4, "rate cut": 0.4, "fed": -0.1},
    "market": {"etf": 0.2, "hack": -0.6, "adoption": 0.4},
}


@dataclass
class AlertScore:
    symbol: str
    timeframe: str
    regime: str
    confidence: int
    tier: str
    action: str
    reasons: List[str]
    reason_codes: List[str]
    blockers: List[str]
    quality: str
    direction: str
    strategy_type: str
    entry_zone: str
    invalidation: float
    tp1: float
    tp2: float
    rr_ratio: float
    session: str
    score_breakdown: Dict[str, int]
    lifecycle_key: str


def _session_label(candles: List[Candle]) -> str:
    if not candles:
        return "unknown"
    try:
        dt = datetime.fromtimestamp(int(float(candles[-1].ts)), tz=timezone.utc)
        if dt.weekday() >= 5:
            return "weekend"
        if 0 <= dt.hour < 8:
            return "asia"
        if 8 <= dt.hour < 13:
            return "europe"
        return "us"
    except Exception:
        return "unknown"


def _trend_bias(candles: List[Candle]) -> int:
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return 0
    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    if e9 is None or e21 is None:
        return 0
    return 1 if e9 > e21 else -1


def _macro_risk_bias(macro: Dict[str, List[Candle]]) -> tuple[int, List[str]]:
    reasons, score = [], 0
    spx = macro.get("spx", [])
    if len(spx) >= 30:
        closes = [c.close for c in spx[:-1]]
        e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
        if e9 and e21 and e9 > e21:
            score += 4
            reasons.append("MACRO_RISK_ON")
    return score, reasons


def _regime(candles: List[Candle]) -> tuple[str, int, List[str]]:
    closes = [c.close for c in candles[:-1]]
    adx_v = adx(candles, 14) or 18
    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    slope = (e9 - e21) / e21 if e9 and e21 else 0.0
    local_atr = atr(candles[:-1], 14) or 0.0
    atr_series = [atr(candles[:i], 14) for i in range(20, len(candles))]
    atr_clean = [x for x in atr_series if x is not None]
    rank = percentile_rank(atr_clean, local_atr) if atr_clean else 50.0
    if adx_v > 24 and abs(slope) > 0.003:
        return "trend", 8, ["REGIME_TREND"]
    if rank > 70 and adx_v < 20:
        return "vol_chop", -8, ["REGIME_VOL_CHOP"]
    return "range", -2, ["REGIME_RANGE"]


def _detectors(candles: List[Candle]) -> tuple[int, str, List[str], List[str]]:
    reasons, codes = [], []
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return 0, "NONE", reasons, codes

    score = 0
    strategy = "TREND_CONTINUATION"
    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    rvwap = vwap(candles[-288:])
    up_break, dn_break = donchian_break(candles, 20)
    z = zscore(closes, 20) or 0.0
    rrsi = rsi(closes, 14) or 50.0

    if up_break or dn_break:
        strategy = "BREAKOUT"
        score += 12 if up_break else -12
        codes.append("DONCHIAN_BREAK")
    elif abs(z) > 1.8 and ((z < 0 and rrsi < 35) or (z > 0 and rrsi > 65)):
        strategy = "MEAN_REVERSION"
        score += 10 if z < 0 else -10
        codes.append("ZSCORE_EXTREME")
    elif e9 and e21 and rvwap:
        if e9 > e21 and closes[-1] > rvwap:
            score += 9
            strategy = "TREND_CONTINUATION"
            codes.append("VWAP_RECLAIM")
        elif e9 < e21 and closes[-1] < rvwap:
            score -= 9
            strategy = "TREND_CONTINUATION"
            codes.append("VWAP_REJECT")

    bb = bollinger_bands(closes, 20, 2)
    if bb and (closes[-1] > bb[0] or closes[-1] < bb[2]):
        strategy = "VOLATILITY_EXPANSION"
        score += 6 if closes[-1] > bb[0] else -6
        codes.append("BB_EXPANSION")

    if score > 0:
        reasons.append("Momentum supports LONG setup")
    if score < 0:
        reasons.append("Momentum supports SHORT setup")
    return score, strategy, reasons, codes


def _tier_and_action(score: int, blockers: List[str]) -> tuple[str, str]:
    if blockers:
        return "NO-TRADE", "SKIP"
    if score >= 74 or score <= 26:
        return "A+", "TRADE"
    if score >= 58 or score <= 42:
        return "B", "WATCH"
    return "NO-TRADE", "SKIP"


def compute_score(
    symbol: str,
    timeframe: str,
    price: PriceSnapshot,
    candles: List[Candle],
    candles_15m: List[Candle],
    candles_1h: List[Candle],
    fg: FearGreedSnapshot,
    news: List[Headline],
    derivatives: DerivativesSnapshot,
    flows: FlowSnapshot,
    macro: Dict[str, List[Candle]],
) -> AlertScore:
    reasons, codes, degraded, blockers = [], [], [], []
    breakdown = {"trend_alignment": 0, "momentum": 0, "volatility": 0, "volume": 0, "htf": 0, "penalty": 0}
    if len(candles) < 40:
        degraded.append("candles")

    reg, reg_pts, reg_codes = _regime(candles)
    breakdown["volatility"] += reg_pts
    codes.extend(reg_codes)

    detector_pts, strategy, detector_reasons, detector_codes = _detectors(candles)
    breakdown["momentum"] += detector_pts
    reasons.extend(detector_reasons)
    codes.extend(detector_codes)

    closes = [c.close for c in candles[:-1]]
    vols = [c.volume for c in candles[:-1]]
    if len(closes) >= 30:
        e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
        if e9 and e21:
            breakdown["trend_alignment"] += 8 if e9 > e21 else -8
            codes.append("EMA_BULL" if e9 > e21 else "EMA_BEAR")
        if len(vols) > 20:
            avg_vol = sum(vols[-21:-1]) / 20
            if vols[-1] > avg_vol * 1.4:
                bump = 6 if closes[-1] > closes[-2] else -6
                breakdown["volume"] += bump
                codes.append("VOL_SURGE")

    t15 = _trend_bias(candles_15m)
    t1h = _trend_bias(candles_1h)
    if t15 + t1h > 0:
        breakdown["htf"] += 8
        codes.append("HTF_BULL")
    elif t15 + t1h < 0:
        breakdown["htf"] -= 8
        codes.append("HTF_BEAR")

    if symbol == "BTC" and fg.healthy:
        if fg.value < 20:
            breakdown["momentum"] += 3
        elif fg.value > 80:
            breakdown["momentum"] -= 3

    if symbol == "BTC" and derivatives.healthy:
        if derivatives.oi_change_pct > 0.7 and derivatives.basis_pct > 0:
            breakdown["trend_alignment"] += 4
            codes.append("OI_BASIS_CONFIRM")
    if symbol == "BTC" and flows.healthy and flows.crowding_score > 6:
        breakdown["penalty"] -= 5
        codes.append("CROWDING_LONG")

    macro_pts, macro_codes = _macro_risk_bias(macro)
    breakdown["trend_alignment"] += macro_pts
    codes.extend(macro_codes)

    if reg == "vol_chop":
        breakdown["penalty"] -= 6
        blockers.append("Chop regime")

    net = sum(breakdown.values())
    score = int(min(100, max(0, 50 + net)))
    direction = "LONG" if score >= 56 else "SHORT" if score <= 44 else "NEUTRAL"
    regime = "long_signal" if score >= 68 else "short_signal" if score <= 32 else f"{reg}_bias"

    px = price.price or (closes[-1] if closes else 0.0)
    local_atr = atr(candles[:-1], 14) or max(1.0, px * 0.002)
    if direction == "LONG":
        invalidation, tp1, tp2 = px - 1.1 * local_atr, px + 1.6 * local_atr, px + 2.8 * local_atr
        rr_ratio = (tp1 - px) / max(px - invalidation, 1e-6)
    elif direction == "SHORT":
        invalidation, tp1, tp2 = px + 1.1 * local_atr, px - 1.6 * local_atr, px - 2.8 * local_atr
        rr_ratio = (px - tp1) / max(invalidation - px, 1e-6)
    else:
        invalidation = tp1 = tp2 = rr_ratio = 0.0

    if rr_ratio < 1.25 and direction != "NEUTRAL":
        blockers.append("Low R:R")
    if direction == "LONG" and t1h < 0:
        blockers.append("HTF conflict")
    if direction == "SHORT" and t1h > 0:
        blockers.append("HTF conflict")

    for hl in news:
        text = hl.title.lower()
        for kws in GROUPS.values():
            for keyword, weight in kws.items():
                if keyword in text:
                    breakdown["momentum"] += int(weight * 2)
                    codes.append(f"NEWS_{keyword.replace(' ', '_').upper()}")

    tier, action = _tier_and_action(score, blockers)
    key = f"{symbol}:{timeframe}:{regime}:{strategy}:{int(px)}"

    return AlertScore(
        symbol=symbol,
        timeframe=timeframe,
        regime=regime,
        confidence=score,
        tier=tier,
        action=action,
        reasons=(reasons or ["No dominant setup"])[:5],
        reason_codes=sorted(set(codes))[:8],
        blockers=sorted(set(blockers)),
        quality="ok" if not degraded else f"degraded:{','.join(sorted(set(degraded)))}",
        direction=direction,
        strategy_type=strategy,
        entry_zone=f"{px - 0.1 * local_atr:,.0f}-{px + 0.1 * local_atr:,.0f}" if direction != "NEUTRAL" else "-",
        invalidation=invalidation,
        tp1=tp1,
        tp2=tp2,
        rr_ratio=rr_ratio,
        session=_session_label(candles),
        score_breakdown=breakdown,
        lifecycle_key=key,
    )
