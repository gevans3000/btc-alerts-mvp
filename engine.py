from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Dict, List, Tuple

from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from config import DETECTORS, REGIME, STALE_SECONDS, TIMEFRAME_RULES
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
    decision_trace: Dict[str, object] = field(default_factory=dict)


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
    if adx_v > REGIME["adx_trend"] and abs(slope) > REGIME["slope_trend"]:
        return "trend", 8, ["REGIME_TREND"]
    if rank > REGIME["atr_rank_chop"] and adx_v < REGIME["adx_chop"]:
        return "vol_chop", -8, ["REGIME_VOL_CHOP"]
    return "range", -2, ["REGIME_RANGE"]


def _detector_candidates(candles: List[Candle]) -> tuple[Dict[str, int], List[str], List[str]]:
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return {"NONE": 0}, [], []

    candidates: Dict[str, int] = {}
    codes: List[str] = []
    reasons: List[str] = []

    lookback = DETECTORS["donchian_lookback"]
    up_break, dn_break = donchian_break(candles, lookback)
    if up_break:
        candidates["BREAKOUT_LONG"] = 12
        codes.append("DONCHIAN_BREAK")
    if dn_break:
        candidates["BREAKOUT_SHORT"] = -12
        codes.append("DONCHIAN_BREAK")

    z = zscore(closes, DETECTORS["zscore_period"]) or 0.0
    rrsi = rsi(closes, DETECTORS["rsi_period"]) or 50.0
    if abs(z) > DETECTORS["zscore_extreme"]:
        if z < 0 and rrsi < DETECTORS["rsi_oversold"]:
            candidates["MEAN_REVERSION_LONG"] = 10
            codes.append("ZSCORE_EXTREME")
        if z > 0 and rrsi > DETECTORS["rsi_overbought"]:
            candidates["MEAN_REVERSION_SHORT"] = -10
            codes.append("ZSCORE_EXTREME")

    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    rvwap = vwap(candles[-288:])
    if e9 and e21 and rvwap:
        if e9 > e21 and closes[-1] > rvwap:
            candidates["TREND_CONTINUATION_LONG"] = 9
            codes.append("VWAP_RECLAIM")
        if e9 < e21 and closes[-1] < rvwap:
            candidates["TREND_CONTINUATION_SHORT"] = -9
            codes.append("VWAP_REJECT")

    bb = bollinger_bands(closes, 20, 2)
    if bb and closes[-1] > bb[0]:
        candidates["VOLATILITY_EXPANSION_LONG"] = 6
        codes.append("BB_EXPANSION")
    elif bb and closes[-1] < bb[2]:
        candidates["VOLATILITY_EXPANSION_SHORT"] = -6
        codes.append("BB_EXPANSION")

    if any(v > 0 for v in candidates.values()):
        reasons.append("Momentum supports LONG setup")
    if any(v < 0 for v in candidates.values()):
        reasons.append("Momentum supports SHORT setup")
    return candidates, reasons, codes


def _arbitrate_candidates(candidates: Dict[str, int]) -> Tuple[int, str, List[str], int]:
    if not candidates:
        return 0, "NONE", [], 0
    long_side = {k: v for k, v in candidates.items() if v > 0}
    short_side = {k: v for k, v in candidates.items() if v < 0}
    codes: List[str] = []
    penalty = 0
    if long_side and short_side:
        codes.append("CONFLICT_SUPPRESSED")
        penalty = -4
    strongest = max(candidates.items(), key=lambda kv: abs(kv[1]))
    strategy = strongest[0].replace("_LONG", "").replace("_SHORT", "")
    return strongest[1], strategy, codes, penalty


def _is_stale(candles: List[Candle], timeframe: str) -> bool:
    if not candles:
        return True
    max_age_seconds = STALE_SECONDS.get(timeframe, STALE_SECONDS["5m"])
    try:
        last_ts = int(float(candles[-1].ts))
    except (TypeError, ValueError):
        return True
    return (time.time() - last_ts) > max_age_seconds


def _tier_and_action(score: int, blockers: List[str], timeframe: str) -> tuple[str, str]:
    cfg = TIMEFRAME_RULES.get(timeframe, TIMEFRAME_RULES["5m"])
    if blockers:
        return "NO-TRADE", "SKIP"
    if score >= cfg["trade_long"] or score <= cfg["trade_short"]:
        return "A+", "TRADE"
    if score >= cfg["watch_long"] or score <= cfg["watch_short"]:
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
    trace: Dict[str, object] = {"degraded": [], "candidates": {}, "blockers": []}

    if len(candles) < 40:
        degraded.append("candles")
    if _is_stale(candles, timeframe):
        degraded.append("stale")
        blockers.append("Stale market data")

    reg, reg_pts, reg_codes = _regime(candles)
    breakdown["volatility"] += reg_pts
    codes.extend(reg_codes)

    candidates, detector_reasons, detector_codes = _detector_candidates(candles)
    trace["candidates"] = candidates
    detector_pts, strategy, arb_codes, arb_penalty = _arbitrate_candidates(candidates)
    breakdown["momentum"] += detector_pts
    breakdown["penalty"] += arb_penalty
    reasons.extend(detector_reasons)
    codes.extend(detector_codes)
    codes.extend(arb_codes)

    closes = [c.close for c in candles[:-1]]
    vols = [c.volume for c in candles[:-1]]
    if len(closes) >= 30:
        e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
        if e9 and e21:
            breakdown["trend_alignment"] += 8 if e9 > e21 else -8
            codes.append("EMA_BULL" if e9 > e21 else "EMA_BEAR")
        if len(vols) > 20:
            avg_vol = sum(vols[-21:-1]) / 20
            if vols[-1] > avg_vol * DETECTORS["volume_multiplier"]:
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

    if symbol == "BTC" and derivatives.healthy and derivatives.oi_change_pct > 0.7 and derivatives.basis_pct > 0:
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

    for hl in news:
        text = hl.title.lower()
        for kws in GROUPS.values():
            for keyword, weight in kws.items():
                if keyword in text:
                    breakdown["momentum"] += int(weight * 2)
                    codes.append(f"NEWS_{keyword.replace(' ', '_').upper()}")

    net = sum(breakdown.values())
    score = int(min(100, max(0, 50 + net)))
    direction = "LONG" if score >= TIMEFRAME_RULES[timeframe]["watch_long"] else "SHORT" if score <= TIMEFRAME_RULES[timeframe]["watch_short"] else "NEUTRAL"
    regime = "long_signal" if score >= TIMEFRAME_RULES[timeframe]["trade_long"] else "short_signal" if score <= TIMEFRAME_RULES[timeframe]["trade_short"] else f"{reg}_bias"

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

    if rr_ratio < TIMEFRAME_RULES[timeframe]["min_rr"] and direction != "NEUTRAL":
        blockers.append("Low R:R")
    if direction == "LONG" and t1h < 0:
        blockers.append("HTF conflict")
    if direction == "SHORT" and t1h > 0:
        blockers.append("HTF conflict")

    tier, action = _tier_and_action(score, blockers, timeframe)
    key = f"{symbol}:{timeframe}:{regime}:{strategy}:{int(px)}"
    trace["degraded"] = sorted(set(degraded))
    trace["blockers"] = sorted(set(blockers))
    trace["strategy"] = strategy
    trace["net"] = net

    return AlertScore(
        symbol=symbol,
        timeframe=timeframe,
        regime=regime,
        confidence=score,
        tier=tier,
        action=action,
        reasons=(reasons or ["No dominant setup"])[:5],
        reason_codes=sorted(set(codes))[:10],
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
        decision_trace=trace,
    )
