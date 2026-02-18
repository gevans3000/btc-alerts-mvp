from typing import Dict, Any, List, Optional, Tuple
from config import INTELLIGENCE_FLAGS
from intelligence import IntelligenceBundle, AlertScore

from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from config import TIMEFRAME_RULES, CONFLUENCE_RULES, TP_MULTIPLIERS
from utils import (
    Candle,
    atr,
    ema as ema_calc,
    volume_delta,
    swing_levels,
)
from intelligence.market_context import (
    _session_label,
    _vix_bias,
    _trend_bias,
    _macro_risk_bias,
    _regime,
    _is_stale,
)
from intelligence.detectors import (
    _detector_candidates,
    _arbitrate_candidates,
)

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
    intel = intel or IntelligenceBundle()

    # --- Intelligence Layers ---
    if intel and intel.squeeze and INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
        sq = intel.squeeze
        if sq["state"] == "SQUEEZE_FIRE":
            breakdown["volatility"] += sq["pts"]
            codes.append("SQUEEZE_FIRE")
        elif sq["state"] == "SQUEEZE_ON":
            codes.append("SQUEEZE_ON")
        trace["context"]["squeeze"] = sq["state"]

    if intel and intel.sentiment and INTELLIGENCE_FLAGS.get("sentiment_enabled", True):
        sent = intel.sentiment
        if not sent.get("fallback", True):
            if sent["composite"] > 0.3:
                breakdown["momentum"] += 4.0
                codes.append("SENTIMENT_BULL")
            elif sent["composite"] < -0.3:
                breakdown["momentum"] -= 4.0
                codes.append("SENTIMENT_BEAR")
            trace["context"]["sentiment"] = {"score": sent["composite"]}

    if len(candles) < 40:
        degraded.append("candles")
    if _is_stale(candles, timeframe):
        degraded.append("stale")
        blockers.append("Stale market data")

    session = _session_label(candles)
    if session == "dead_zone":
        blockers.append("Market dead zone")
    if session == "weekend":
        breakdown["penalty"] -= 10.0

    # Market context
    regime_name, regime_pts, regime_codes = _regime(candles)
    breakdown["volatility"] += regime_pts
    codes.extend(regime_codes)

    # Bias
    htf_bias = _trend_bias(candles_1h if timeframe != "1h" else candles_15m)
    vix_pts, vix_reasons, vix_codes = _vix_bias(macro)
    breakdown["penalty"] += vix_pts
    codes.extend(vix_codes)

    macro_pts, macro_reasons = _macro_risk_bias(macro)
    breakdown["htf"] += macro_pts
    codes.extend(macro_reasons)

    # Candidates
    candidates, c_reasons, c_codes = _detector_candidates(candles)
    reasons.extend(c_reasons)
    codes.extend(c_codes)
    trace["candidates"] = candidates

    # Arbitration
    pts, strategy, arb_codes, arb_penalty = _arbitrate_candidates(candidates, htf_bias, session)
    breakdown["momentum"] += pts
    breakdown["penalty"] += arb_penalty
    codes.extend(arb_codes)

    # Final score
    total_score = sum(breakdown.values())
    confluence_count = len([c for c in codes if "REGIME" not in c and "SESSION" not in c])
    tier, action = _tier_and_action(int(total_score), blockers, timeframe, confluence_count)

    # Exit levels
    last_price = price.price if symbol == "BTC" else candles[-1].close
    local_atr = atr(candles, 14) or (last_price * 0.02)
    direction = "LONG" if pts > 0 else "SHORT" if pts < 0 else "NEUTRAL"
    
    tp_cfg = TP_MULTIPLIERS.get(regime_name, TP_MULTIPLIERS["default"])
    tp1_mult = tp_cfg["tp1"]
    inv_mult = tp_cfg["inv"]
    
    if direction == "LONG":
        invalidation = last_price - (local_atr * inv_mult * 2.0)
        tp1 = last_price + (local_atr * tp1_mult)
        tp2 = last_price + (local_atr * tp_cfg["tp2"])
    else:
        invalidation = last_price + (local_atr * inv_mult * 2.0)
        tp1 = last_price - (local_atr * tp1_mult)
        tp2 = last_price - (local_atr * tp_cfg["tp2"])

    risk = abs(last_price - invalidation)
    reward = abs(tp1 - last_price)
    rr = reward / risk if risk > 0 else 0.0

    return AlertScore(
        symbol=symbol,
        timeframe=timeframe,
        regime=regime_name,
        confidence=min(100, max(0, int(total_score))),
        tier=tier,
        action=action,
        reasons=reasons,
        reason_codes=list(set(codes)),
        blockers=blockers,
        quality="HIGH" if tier == "A+" else "MED",
        direction=direction,
        strategy_type=strategy,
        entry_zone=f"{last_price:,.0f}",
        invalidation=invalidation,
        tp1=tp1,
        tp2=tp2,
        rr_ratio=rr,
        session=session,
        score_breakdown=breakdown,
        lifecycle_key=f"{symbol}:{timeframe}:{strategy.lower()}:{direction}:{int(last_price/10)*10}",
        last_candle_ts=int(float(candles[-1].ts)) if candles else 0,
        intel=intel,
        decision_trace=trace
    )
