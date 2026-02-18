from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Dict, Any, List, Optional, Tuple

from config import INTELLIGENCE_FLAGS, VOLUME_PROFILE
from intelligence import IntelligenceBundle
from intelligence.macro import analyze_macro_correlation

from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from config import DETECTORS, REGIME, STALE_SECONDS, TIMEFRAME_RULES, SESSION_WEIGHTS, CONFLUENCE_RULES, TP_MULTIPLIERS
from utils import (
    Candle,
    adx,
    atr,
    bollinger_bands,
    donchian_break,
    ema as ema_calc,
    percentile_rank,
    rsi,
    vwap,
    zscore,
    rsi_divergence,
    candle_patterns,
    volume_delta,
    swing_levels,
)

GROUPS = {
    "policy": {"bitcoin reserve": 0.7, "tariff": -0.4, "regulation": -0.3},
    "macro": {"rate hike": -0.4, "rate cut": 0.4, "fed": -0.1},
    "market": {
        "etf": 0.2,
        "hack": -0.6,
        "adoption": 0.4,
        "whale": 0.3,
        "dump": -0.5,
        "rally": 0.3,
        "crash": -0.5,
        "ban": -0.6,
        "approval": 0.5,
    },
    "defi": {"exploit": -0.5, "tvl": 0.2, "stablecoin": 0.1},
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
    score_breakdown: Dict[str, float]
    lifecycle_key: str
    last_candle_ts: int = 0
    decision_trace: Dict[str, object] = field(default_factory=dict)
    context: Dict[str, object] = field(default_factory=dict)


def _session_label(candles: List[Candle]) -> str:
    if not candles:
        return "unknown"
    try:
        dt = datetime.fromtimestamp(int(float(candles[-1].ts)), tz=timezone.utc)
        # Dead Zone: Weekday 20:00-22:00 UTC (US Close to Asia Open gap)
        if 0 <= dt.weekday() < 5:
            if 20 <= dt.hour < 22:
                return "dead_zone"
        if dt.weekday() >= 5:
            return "weekend"
        if 0 <= dt.hour < 8:
            return "asia"
        if 8 <= dt.hour < 13:
            return "europe"
        return "us"
    except Exception:
        return "unknown"


def _vix_bias(macro: Dict[str, List[Candle]]) -> Tuple[float, List[str], List[str]]:
    vix = macro.get("vix", [])
    if len(vix) < 13:
        return 0.0, [], []
    
    reasons, codes = [], []
    vix_closes = [c.close for c in vix]
    vix_change = (vix_closes[-1] - vix_closes[-12]) / max(vix_closes[-12], 1e-8)
    
    if vix_change > 0.05:
        reasons.append("VIX spiking, risk-off")
        codes.append("VIX_SPIKE")
        return -4.0, reasons, codes
    
    if vix_closes[-1] > 30:
        codes.append("VIX_EXTREME")
        return -1.0, ["VIX extremely high"], codes
        
    return 0.0, [], []


def _trend_bias(candles: List[Candle]) -> int:
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return 0
    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    if e9 is None or e21 is None:
        return 0
    return 1 if e9 > e21 else -1


def _macro_risk_bias(macro: Dict[str, List[Candle]]) -> tuple[float, List[str]]:
    reasons, score = [], 0.0
    spx = macro.get("spx", [])
    if len(spx) >= 30:
        closes = [c.close for c in spx[:-1]]
        e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
        if e9 and e21 and e9 > e21:
            score += 4.0
            reasons.append("MACRO_RISK_ON")
    return score, reasons


def _calculate_raw_regime(candles: List[Candle]) -> str:
    closes = [c.close for c in candles[:-1]]
    if len(candles) < 30:
        return "range"
    adx_v = adx(candles, 14) or 18
    e9, e21 = ema_calc(closes, 9), ema_calc(closes, 21)
    slope = (e9 - e21) / e21 if e9 and e21 else 0.0
    local_atr = atr(candles[:-1], 14) or 0.0
    atr_series = [atr(candles[:i], 14) for i in range(20, len(candles))]
    atr_clean = [x for x in atr_series if x is not None]
    rank = percentile_rank(atr_clean, local_atr) if atr_clean else 50.0
    
    if adx_v > REGIME["adx_trend"] and abs(slope) > REGIME["slope_trend"]:
        return "trend"
    if rank > REGIME["atr_rank_chop"] and adx_v < REGIME["adx_chop"]:
        return "vol_chop"
    if adx_v < REGIME.get("adx_low", 20) and rank < REGIME.get("atr_rank_low", 30):
        return "chop"
    return "range"


def _regime(candles: List[Candle]) -> tuple[str, float, List[str]]:
    # Persistence check: require 3 consecutive candles in the same raw regime
    if len(candles) < 35:
        r = _calculate_raw_regime(candles)
        return r, 0.0, [f"REGIME_{r.upper()}"]
        
    r1 = _calculate_raw_regime(candles)
    r2 = _calculate_raw_regime(candles[:-1])
    r3 = _calculate_raw_regime(candles[:-2])
    
    if r1 == r2 == r3:
        final_regime = r1
    elif r2 == r3:
        final_regime = r2
    else:
        final_regime = "range"

    pts = 0.0
    if final_regime == "trend":
        pts = 8.0
    elif final_regime == "vol_chop":
        pts = -8.0
    elif final_regime == "chop":
        pts = -15.0 # CHOP regime automatically penalizes score by 15
    else:
        pts = -2.0
        
    return final_regime, pts, [f"REGIME_{final_regime.upper()}"]


def _detector_candidates(candles: List[Candle]) -> tuple[Dict[str, int], List[str], List[str]]:
    closes = [c.close for c in candles[:-1]]
    if len(closes) < 30:
        return {"NONE": 0}, [], []

    candidates: Dict[str, int] = {}
    codes: List[str] = []
    reasons: List[str] = []

    div_type, div_strength = rsi_divergence(candles)
    if div_type == "bullish":
        candidates["DIVERGENCE_LONG"] = 14
        codes.append("RSI_DIVERGENCE")
    elif div_type == "bearish":
        candidates["DIVERGENCE_SHORT"] = -14
        codes.append("RSI_DIVERGENCE")

    patterns = candle_patterns(candles)
    for name, direction in patterns:
        bias = 6 if direction == "bullish" else -6
        candidates[f"{name.upper()}_{direction.upper()}"] = bias
        codes.append(f"{name.upper()}_{direction[:4].upper()}")

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


def _arbitrate_candidates(candidates: Dict[str, int], htf_bias: int, session: str) -> Tuple[float, str, List[str], float]:
    if not candidates:
        return 0.0, "NONE", [], 0.0
    long_side = {k: v for k, v in candidates.items() if v > 0}
    short_side = {k: v for k, v in candidates.items() if v < 0}
    codes: List[str] = []
    penalty = 0.0
    if long_side and short_side:
        codes.append("CONFLICT_SUPPRESSED")
        penalty = -4.0
    
    max_abs = max(abs(v) for v in candidates.values())
    tied = [(k, v) for k, v in candidates.items() if abs(v) == max_abs]
    
    if len(tied) == 1:
        pick_key, pick_val = tied[0]
    else:
        aligned = [(k, v) for k, v in tied if (v > 0 and htf_bias > 0) or (v < 0 and htf_bias < 0)]
        if len(aligned) >= 1:
            pick_key, pick_val = aligned[0]
            codes.append("ARBITRATION_HTF_TIEBREAK")
        else:
            codes.append("ARBITRATION_TIE_NEUTRAL")
            return 0.0, "NONE", codes, penalty - 2.0
            
    strategy = pick_key.replace("_LONG", "").replace("_SHORT", "")
    if strategy in ["DIVERGENCE", "ENGULFING", "PIN"]:
        strategy = "TREND_CONTINUATION"
        for k, v in tied:
            base = k.replace("_LONG", "").replace("_SHORT", "")
            if base in ["BREAKOUT", "MEAN_REVERSION", "TREND_CONTINUATION", "VOLATILITY_EXPANSION"]:
                strategy = base
                break

    weight = SESSION_WEIGHTS.get(session, {"default": 1.0}).get(strategy, 1.0)
    adjusted_pts = float(pick_val * weight)
    if weight > 1.0: codes.append("SESSION_BOOST")
    elif weight < 1.0: codes.append("SESSION_PENALTY")

    return adjusted_pts, strategy, codes, penalty


def _is_stale(candles: List[Candle], timeframe: str) -> bool:
    if not candles:
        return True
    max_age_seconds = STALE_SECONDS.get(timeframe, STALE_SECONDS["5m"])
    try:
        last_ts = int(float(candles[-1].ts))
    except (TypeError, ValueError):
        return True
    return (time.time() - last_ts) > max_age_seconds


def _tier_and_action(score: int, blockers: List[str], timeframe: str, confluence: int) -> tuple[str, str]:
    cfg = TIMEFRAME_RULES.get(timeframe, TIMEFRAME_RULES["5m"])
    if blockers:
        return "NO-TRADE", "SKIP"
    
    tier = "NO-TRADE"
    action = "SKIP"

    if score >= cfg["trade_long"] or score <= cfg["trade_short"]:
        tier = "A+"
        action = "TRADE"
    elif score >= cfg["watch_long"] or score <= cfg["watch_short"]:
        tier = "B"
        action = "WATCH"

    required = CONFLUENCE_RULES.get(tier, 0)
    if confluence < required:
        if tier == "A+":
            tier = "B"
            if confluence < CONFLUENCE_RULES.get("B", 0):
                tier = "NO-TRADE"
                action = "SKIP"
        else:
            tier = "NO-TRADE"
            action = "SKIP"

    return tier, action


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
    intel: Optional[IntelligenceBundle] = None,
) -> AlertScore:
    tf_cfg = TIMEFRAME_RULES.get(timeframe, TIMEFRAME_RULES["5m"])
    reasons, codes, degraded, blockers = [], [], [], []
    breakdown: Dict[str, float] = {"trend_alignment": 0.0, "momentum": 0.0, "volatility": 0.0, "volume": 0.0, "htf": 0.0, "penalty": 0.0}
    trace: Dict[str, object] = {"degraded": [], "candidates": {}, "blockers": [], "context": {}, "codes": []}

    # --- Intelligence Layer: Volume Profile ---
    if intel and intel.volume_profile and INTELLIGENCE_FLAGS.get("volume_profile_enabled", True):
        vp = intel.volume_profile
        
        if vp["position"] == "ABOVE_VALUE":
            breakdown["volume"] += vp["pts"]
            codes.append("VP_ABOVE_VALUE")
        elif vp["position"] == "BELOW_VALUE":
            breakdown["volume"] += vp["pts"]
            codes.append("VP_BELOW_VALUE")
        else: # AT_VALUE
            codes.append("VP_AT_VALUE")
        trace["context"]["volume_profile"] = vp
    intel = intel or IntelligenceBundle()

    # --- Intelligence Layer: Squeeze ---
    if intel and intel.squeeze and INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
        sq = intel.squeeze
        if sq["state"] == "SQUEEZE_FIRE":
            breakdown["volatility"] += sq["pts"]
            codes.append("SQUEEZE_FIRE")
        elif sq["state"] == "SQUEEZE_ON":
            codes.append("SQUEEZE_ON")
        trace["context"]["squeeze"] = sq["state"]

    # --- Intelligence Layer: Liquidity Walls ---
    if intel and intel.liquidity and INTELLIGENCE_FLAGS.get("liquidity_enabled", True):
        liq = intel.liquidity
        breakdown["volume"] += liq["pts"]
        codes.append(f"LIQUIDITY_IMBALANCE_{liq['imbalance']:.2f}")
        trace["context"]["liquidity"] = liq

    # --- Intelligence Layer: Macro Correlation ---
    if intel and INTELLIGENCE_FLAGS.get("macro_correlation_enabled", True):
        macro_analysis = analyze_macro_correlation(candles, macro)
        breakdown["trend_alignment"] += macro_analysis["pts"]
        codes.extend(macro_analysis["codes"])
        trace["context"]["macro_correlation"] = macro_analysis

    if len(candles) < 40:
        degraded.append("candles")
    if _is_stale(candles, timeframe):
        degraded.append("stale")
        blockers.append("Stale market data")

    session = _session_label(candles)
    if session == "dead_zone":
        blockers.append("Market dead zone")
    if session == "weekend":
        breakdown["penalty"] -= 10.0 # Weekend liquidity penalty

    reg, reg_pts, reg_codes = _regime(candles)
    breakdown["volatility"] += reg_pts
    codes.extend(reg_codes)

    t15 = _trend_bias(candles_15m)
    t1h = _trend_bias(candles_1h)
    htf_bias = t15 + t1h

    candidates, detector_reasons, detector_codes = _detector_candidates(candles)
    trace["candidates"] = candidates
    detector_pts, strategy, arb_codes, arb_penalty = _arbitrate_candidates(candidates, htf_bias, session)
    
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
            breakdown["trend_alignment"] += 8.0 if e9 > e21 else -8.0
            codes.append("EMA_BULL" if e9 > e21 else "EMA_BEAR")
        
        c_delta, d_trend = volume_delta(candles)
        if c_delta > 0 and d_trend > 0:
            breakdown["volume"] += 5.0
            codes.append("DELTA_BUY_PRESSURE")
        elif c_delta < 0 and d_trend < 0:
            breakdown["volume"] -= 5.0
            codes.append("DELTA_SELL_PRESSURE")
        
        if len(vols) > 20:
            avg_vol = sum(vols[-21:-1]) / 20
            if vols[-1] > avg_vol * DETECTORS["volume_multiplier"]:
                bump = 6.0 if closes[-1] > closes[-2] else -6.0
                breakdown["volume"] += bump
                codes.append("VOL_SURGE")

    if htf_bias > 0:
        breakdown["htf"] += 8.0
        codes.append("HTF_BULL")
    elif htf_bias < 0:
        breakdown["htf"] -= 8.0
        codes.append("HTF_BEAR")

    if symbol == "BTC" and fg.healthy:
        if fg.value < 20: breakdown["momentum"] += 3.0
        elif fg.value > 80: breakdown["momentum"] -= 3.0

    if symbol == "BTC" and derivatives.healthy:
        if derivatives.oi_change_pct > 0.7 and derivatives.basis_pct > 0:
            breakdown["trend_alignment"] += 4.0
            codes.append("OI_BASIS_CONFIRM")
            
    if symbol == "BTC" and flows.healthy and flows.crowding_score > 6:
        breakdown["penalty"] -= 5.0
        codes.append("CROWDING_LONG")

    vix_pts, vix_reasons, vix_codes = _vix_bias(macro)
    breakdown["volatility"] += vix_pts
    reasons.extend(vix_reasons)
    codes.extend(vix_codes)
    if "VIX_EXTREME" in vix_codes and strategy == "BREAKOUT":
        blockers.append("High VIX")

    macro_pts, macro_codes = _macro_risk_bias(macro)
    breakdown["trend_alignment"] += macro_pts
    codes.extend(macro_codes)

    if reg == "vol_chop":
        breakdown["penalty"] -= 6.0
        blockers.append("Chop regime")

    # 1G. Swing Levels
    px = price.price or (closes[-1] if closes else 0.0)
    supports, resistances = swing_levels(candles)
    near_supp = any(abs(px - s) / s < 0.005 for s in supports)
    near_resists = any(abs(px - r) / r < 0.005 for r in resistances)
    
    keyword_hits: Dict[str, int] = {}
    for hl in news:
        text = hl.title.lower()
        for kws in GROUPS.values():
            for keyword, weight in kws.items():
                if keyword in text:
                    count = keyword_hits.get(keyword, 0)
                    if count < 2:
                        contribution = weight * (2.0 if count == 0 else 1.0)
                        breakdown["momentum"] += contribution
                        codes.append(f"NEWS_{keyword.replace(' ', '_').upper()}")
                    keyword_hits[keyword] = count + 1

    # --- Intelligence Layer: Squeeze ---
    if intel and intel.squeeze and INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
        sq = intel.squeeze
        if sq["state"] == "SQUEEZE_FIRE":
            breakdown["volatility"] += sq["pts"]
            codes.append("SQUEEZE_FIRE")
        elif sq["state"] == "SQUEEZE_ON":
            codes.append("SQUEEZE_ON")
        trace["context"]["squeeze"] = sq["state"]

    net = sum(breakdown.values())
    raw_score = int(min(100, max(0, 50 + net)))
    
    direction = "NEUTRAL"
    if raw_score >= tf_cfg["watch_long"]:
        direction = "LONG"
        if near_supp:
            breakdown["momentum"] += 5.0
            codes.append("SR_LEVEL_CONFIRM")
    elif raw_score <= tf_cfg["watch_short"]:
        direction = "SHORT"
        if near_resists:
            breakdown["momentum"] -= 5.0
            codes.append("SR_LEVEL_CONFIRM")

    final_score = int(min(100, max(0, 50 + sum(breakdown.values()))))
    regime = "long_signal" if final_score >= tf_cfg["trade_long"] else "short_signal" if final_score <= tf_cfg["trade_short"] else f"{reg}_bias"

    confluence = 0
    if abs(breakdown["trend_alignment"]) >= 8: confluence += 1
    if abs(breakdown["momentum"]) >= 8: confluence += 1
    if abs(breakdown["volume"]) >= 5: confluence += 1
    if abs(breakdown["htf"]) >= 8: confluence += 1
    if "RSI_DIVERGENCE" in codes: confluence += 1
    if any("ENGULFING" in c or "PIN" in c for c in codes): confluence += 1
    if "SR_LEVEL_CONFIRM" in codes: confluence += 1
    
    codes.append(f"CONFLUENCE_{confluence}")
    trace["confluence_count"] = confluence

    local_atr = atr(candles[:-1], 14) or max(1.0, px * 0.002)
    tp_cfg = TP_MULTIPLIERS.get(reg, TP_MULTIPLIERS["default"])
    inv_mult, tp1_mult, tp2_mult = tp_cfg["inv"], tp_cfg["tp1"], tp_cfg["tp2"]

    if direction == "LONG":
        best_inv = px - inv_mult * local_atr
        relevant_supports = [s for s in supports if s < px]
        if relevant_supports:
            best_inv = max(best_inv, max(relevant_supports) * 0.998)
        
        tp1 = px + tp1_mult * local_atr
        relevant_resists = [r for r in resistances if r > px]
        if relevant_resists:
            tp1 = min(tp1, min(relevant_resists))
            
        invalidation, tp2 = best_inv, px + tp2_mult * local_atr
        rr_ratio = (tp1 - px) / max(px - invalidation, 1e-6)
    elif direction == "SHORT":
        best_inv = px + inv_mult * local_atr
        relevant_resists = [r for r in resistances if r > px]
        if relevant_resists:
            best_inv = min(best_inv, min(relevant_resists) * 1.002)
            
        tp1 = px - tp1_mult * local_atr
        relevant_supports = [s for s in supports if s < px]
        if relevant_supports:
            tp1 = max(tp1, max(relevant_supports))
            
        invalidation, tp2 = best_inv, px - tp2_mult * local_atr
        rr_ratio = (px - tp1) / max(invalidation - px, 1e-6)
    else:
        invalidation = tp1 = tp2 = rr_ratio = 0.0

    if rr_ratio < tf_cfg["min_rr"] and direction != "NEUTRAL":
        blockers.append("Low R:R")
    if direction == "LONG":
        if timeframe == "5m" and t15 < 0: blockers.append("HTF_CONFLICT_15M")
        if t1h < 0: blockers.append("HTF_CONFLICT_1H")
    elif direction == "SHORT":
        if timeframe == "5m" and t15 > 0: blockers.append("HTF_CONFLICT_15M")
        if t1h > 0: blockers.append("HTF_CONFLICT_1H")

    tier, action = _tier_and_action(final_score, blockers, timeframe, confluence)
    
    # 2.4 Volume Confirmation Gate for TRADE signals
    if action == "TRADE" and len(vols) > 20:
        avg_vol = sum(vols[-21:-1]) / 20
        if vols[-1] < avg_vol:
            action = "WATCH"
            tier = "B"
            codes.append("VOLUME_GATE_DOWNGRADE")
    key = f"{symbol}:{timeframe}:{regime}:{strategy}:{int(px)}"
    trace["strategy"] = strategy
    trace["net"] = sum(breakdown.values())

    return AlertScore(
        symbol=symbol, timeframe=timeframe, regime=regime, confidence=final_score,
        tier=tier, action=action, reasons=(reasons or ["No dominant setup"])[:5],
        reason_codes=sorted(set(codes))[:10], blockers=sorted(set(blockers)),
        quality="ok" if not degraded else f"degraded:{','.join(sorted(set(degraded)))}",
        direction=direction, strategy_type=strategy,
        entry_zone=f"{px - 0.1 * local_atr:,.0f}-{px + 0.1 * local_atr:,.0f}" if direction != "NEUTRAL" else "-",
        invalidation=invalidation, tp1=tp1, tp2=tp2, rr_ratio=rr_ratio,
        session=session, score_breakdown=breakdown, lifecycle_key=key,
        last_candle_ts=int(float(candles[-1].ts)) if candles else 0,
        decision_trace=trace,
    )
