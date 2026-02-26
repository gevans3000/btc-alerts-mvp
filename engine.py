from typing import Dict, Any, List, Optional, Tuple
from config import INTELLIGENCE_FLAGS
from intelligence import IntelligenceBundle, AlertScore
from intelligence.structure import detect_structure
from intelligence.session_levels import compute_session_levels
from intelligence.sweeps import detect_equal_levels
from intelligence.anchored_vwap import compute_anchored_vwap
from intelligence.volume_impulse import detect_volume_impulse
from intelligence.oi_classifier import classify_price_oi
from intelligence.auto_rr import compute_auto_rr

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

    # score is abs(total_score), always >= 0
    # Only gate on the LONG thresholds since score is already absolute
    if score >= cfg["trade_long"]:
        tier = "A+"
        action = "TRADE"
    elif score >= cfg["watch_long"]:
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
            if sent["composite"] > 0.15:
                breakdown["momentum"] += 4.0
                codes.append("SENTIMENT_BULL")
            elif sent["composite"] < -0.15:
                breakdown["momentum"] -= 4.0
                codes.append("SENTIMENT_BEAR")
            trace["context"]["sentiment"] = {"score": sent["composite"]}

    if intel and intel.volume_profile and INTELLIGENCE_FLAGS.get("volume_profile_enabled", True):
        vp = intel.volume_profile
        if vp.get("near_poc"):
            breakdown["momentum"] += vp["pts"]
            codes.append("NEAR_POC")
        trace["context"]["volume_profile"] = {
            "poc": vp["poc"], "vah": vp.get("vah"), "val": vp.get("val"),
            "near_poc": vp["near_poc"], "lvn_zones": vp.get("lvn_zones", []),
        }

    if intel and intel.liquidity and INTELLIGENCE_FLAGS.get("liquidity_enabled", True):
        liq = intel.liquidity
        breakdown["volume"] += liq["pts"]
        if liq["support"]: codes.append("BID_WALL_SUPPORT")
        if liq["resistance"]: codes.append("ASK_WALL_RESISTANCE")
        trace["context"]["liquidity"] = liq

    if intel and intel.macro_correlation and INTELLIGENCE_FLAGS.get("macro_correlation_enabled", True):
        mc = intel.macro_correlation
        breakdown["htf"] += mc["pts"]
        if mc["dxy_trend"] == "falling": codes.append("DXY_FALLING_BULLISH")
        elif mc["dxy_trend"] == "rising": codes.append("DXY_RISING_BEARISH")
        if mc["gold_trend"] == "rising": codes.append("GOLD_RISING_BULLISH")
        elif mc["gold_trend"] == "falling": codes.append("GOLD_FALLING_BEARISH")
        trace["context"]["macro_correlation"] = {"dxy": mc["dxy_trend"], "gold": mc["gold_trend"]}

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

    # Map HTF Bias to Radar Codes
    if htf_bias > 0: codes.append("HTF_ALIGNED")
    elif htf_bias < 0: codes.append("HTF_COUNTER")

    # Map Fear & Greed to Radar Codes
    if fg and fg.healthy:
        if fg.value <= 25: codes.append("FG_EXTREME_FEAR")
        elif fg.value <= 45: codes.append("FG_FEAR")
        elif fg.value >= 75: codes.append("FG_EXTREME_GREED")
        elif fg.value >= 55: codes.append("FG_GREED")

    # Map Derivatives to Radar Codes
    if derivatives and derivatives.healthy:
        code_fr = derivatives.funding_rate
        if code_fr <= -0.0003: codes.append("FUNDING_EXTREME_LOW")
        elif code_fr < -0.00005: codes.append("FUNDING_LOW")
        elif code_fr >= 0.0003: codes.append("FUNDING_EXTREME_HIGH")
        elif code_fr > 0.00005: codes.append("FUNDING_HIGH")
        
        oi_pct = derivatives.oi_change_pct
        if oi_pct >= 1.5: codes.append("OI_SURGE_MAJOR")
        elif oi_pct >= 0.5: codes.append("OI_SURGE_MINOR")
        
        basis = derivatives.basis_pct
        if basis >= 0.05: codes.append("BASIS_BULLISH")
        elif basis <= -0.05: codes.append("BASIS_BEARISH")

    # Map Flows to Radar Codes
    if flows and flows.healthy:
        if flows.taker_ratio >= 1.3:
            codes.append("FLOW_TAKER_BULLISH")
            breakdown["momentum"] += 3.0
        elif flows.taker_ratio <= 0.7:
            codes.append("FLOW_TAKER_BEARISH")
            breakdown["momentum"] -= 3.0
        if flows.long_short_ratio >= 1.5:
            codes.append("FLOW_LS_CROWDED_LONG")
        elif flows.long_short_ratio <= 0.67:
            codes.append("FLOW_LS_CROWDED_SHORT")

    # --- Phase 17: New Intelligence Layers ---
    # Market Structure (BOS/CHoCH)
    try:
        struct = detect_structure(candles)
        codes.extend(struct["codes"])
        breakdown["momentum"] += struct["pts"]
        trace["context"]["structure"] = {
            "trend": struct["trend"], "event": struct["last_event"],
            "last_pivot_high": struct.get("last_pivot_high"),
            "last_pivot_low": struct.get("last_pivot_low"),
        }
    except Exception:
        pass

    # Session Levels (PDH/PDL + sweep)
    try:
        sess_lvl = compute_session_levels(candles)
        codes.extend(sess_lvl["codes"])
        breakdown["htf"] += sess_lvl["pts"]
        trace["context"]["session_levels"] = {
            "pdh": sess_lvl["pdh"], "pdl": sess_lvl["pdl"],
            "session_high": sess_lvl.get("session_high"),
            "session_low": sess_lvl.get("session_low"),
        }
    except Exception:
        pass

    # Equal Highs/Lows + Sweep
    try:
        eql = detect_equal_levels(candles)
        codes.extend(eql["codes"])
        breakdown["momentum"] += eql["pts"]
        trace["context"]["equal_levels"] = {"eq_highs": len(eql["equal_highs"]), "eq_lows": len(eql["equal_lows"])}
    except Exception:
        pass

    # Anchored VWAP
    try:
        avwap = compute_anchored_vwap(candles)
        codes.extend(avwap["codes"])
        breakdown["momentum"] += avwap["pts"]
        trace["context"]["avwap"] = {"value": avwap["avwap"], "position": avwap["price_vs_avwap"]}
    except Exception:
        pass

    # Volume Impulse + Micro Volatility
    try:
        vimp = detect_volume_impulse(candles)
        codes.extend(vimp["codes"])
        breakdown["volume"] += vimp["pts"]
        trace["context"]["volume_impulse"] = {
            "rvol": vimp["rvol"], "regime": vimp["vol_regime"],
            "atr_percentile": vimp.get("atr_percentile", 50),
        }
    except Exception:
        pass

    # Price–OI Classifier (needs price change from candles + derivatives)
    if derivatives and derivatives.healthy and len(candles) >= 2:
        try:
            price_chg = ((candles[-1].close - candles[-2].close) / candles[-2].close) * 100
            oi_class = classify_price_oi(price_chg, derivatives)
            codes.extend(oi_class["codes"])
            breakdown["momentum"] += oi_class["pts"]
            trace["context"]["oi_regime"] = oi_class["regime"]
        except Exception:
            pass

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

    # Map ML Mock / Fallback
    # If the score is extreme, we assume high algorithmic conviction.
    if total_score >= 20:
        codes.append("ML_CONFIDENCE_BOOST")
    elif total_score <= -20:
        codes.append("ML_SKEPTICISM")

    # --- Confluence Heatmap ---
    if INTELLIGENCE_FLAGS.get("confluence_enabled", True):
        from intelligence.confluence import compute_confluence
        confluence_data = compute_confluence(codes, breakdown)
        trace["context"]["confluence"] = confluence_data

    confluence_count = len([c for c in codes if "REGIME" not in c and "SESSION" not in c])
    tier, action = _tier_and_action(int(abs(total_score)), blockers, timeframe, confluence_count)

    # Exit levels
    last_price = price.price if symbol == "BTC" else candles[-1].close
    local_atr = atr(candles, 14) or (last_price * 0.02)
    direction = "LONG" if pts > 0 else "SHORT" if pts < 0 else "NEUTRAL"

    # Auto R:R to nearest liquidity
    try:
        auto_rr = compute_auto_rr(candles, direction)
        codes.extend(auto_rr["codes"])
        trace["context"]["auto_rr"] = {
            "rr": auto_rr["rr"], "target": auto_rr["target"],
            "stop": auto_rr["stop"], "entry": auto_rr.get("entry"),
        }
    except Exception:
        pass
    
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

    trace["codes"] = list(set(codes))
    trace["degraded"] = degraded
    trace["blockers"] = blockers

    return AlertScore(
        symbol=symbol,
        timeframe=timeframe,
        regime=regime_name,
        confidence=min(100, max(0, int(abs(total_score)))),
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
