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
from intelligence.recipes import detect_recipes, RecipeSignal, resolve_conflicts

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
    bollinger_bands,
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
from core.logger import logger

# Phase 20-23: calibrated for live market. Scales raw signal points (~-30 to +30)
# up to the 0-100 confidence range expected by TIMEFRAME_RULES thresholds.
SCORE_MULTIPLIER = 7.0

def _tier_and_action(score: int, blockers: List[str], timeframe: str, rubric_score: int) -> tuple[str, str]:
    """
    Tiering logic updated for Phase 22:
    - Enforces 6-point Confluence Rubric.
    - TRADE (A+) requires rubric_score >= 4.
    - WATCH (B) requires rubric_score >= 2.
    """
    cfg = TIMEFRAME_RULES.get(timeframe, TIMEFRAME_RULES["5m"])
    if blockers:
        return "NO-TRADE", "SKIP"
    
    tier = "NO-TRADE"
    action = "SKIP"

    # Preliminary tiering based on confidence score (normalized)
    if score >= cfg["trade_long"]:
        tier = "A+"
        action = "TRADE"
    elif score >= cfg["watch_long"]:
        tier = "B"
        action = "WATCH"

    # Hard Gate: Confluence Rubric (Phase 23: Tightened to 5/6 for A+, 3/6 for B)
    if tier == "A+" and rubric_score < 5:
        tier = "B"
        if rubric_score < 3:
            tier = "NO-TRADE"
            action = "SKIP"
    elif tier == "B" and rubric_score < 3:
        tier = "NO-TRADE"
        action = "SKIP"

    return tier, action

def _htf_confirms(recipe_direction: str, candles_htf: List[Candle]) -> bool:
    """
    Check if Higher-Timeframe structure doesn't contradict the recipe.
    
    Not requiring full alignment — just checking for NO active counter-signal.
    - LONG recipe: HTF must NOT have recent bearish structural shift.
    - SHORT recipe: HTF must NOT have recent bullish structural shift.
    """
    if not candles_htf or len(candles_htf) < 20:
        return True # Neutral
        
    counter_events = []
    if recipe_direction == "LONG":
        counter_events = ["BOS_BEAR", "CHOCH_BEAR"]
    elif recipe_direction == "SHORT":
        counter_events = ["BOS_BULL", "CHOCH_BULL"]
        
    try:
        # Phase 23 fix: Make HTF conflict check recency-aware (last 3 HTF candles)
        for i in range(3):
            sub_candles = candles_htf if i == 0 else candles_htf[:-i]
            if len(sub_candles) < 20:
                continue
                
            struct_htf = detect_structure(sub_candles)
            if struct_htf.get("last_event") in counter_events:
                return False
    except Exception:
        pass
        
    return True

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
    candles_4h: Optional[List[Candle]] = None,
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
        # Phase 19 FIX 4: pipe VP position codes (ABOVE_VALUE / BELOW_VALUE) into radar
        codes.extend(vp.get("codes", []))
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
        else:
            # Phase 19: normal funding = mild bullish (no extreme crowding)
            codes.append("FUNDING_LOW")
        
        oi_pct = derivatives.oi_change_pct
        if oi_pct >= 1.5: codes.append("OI_SURGE_MAJOR")
        elif oi_pct >= 0.3: codes.append("OI_SURGE_MINOR")  # Phase 19: was 0.5
        
        basis = derivatives.basis_pct
        if basis >= 0.02: codes.append("BASIS_BULLISH")      # Phase 19: was 0.05
        elif basis <= -0.02: codes.append("BASIS_BEARISH")   # Phase 19: was -0.05

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

    # --- Recipe Detection (Phase 22/23) ---
    try:
        # Detect patterns and answer the "5-Question" validation schema
        raw_signals = detect_recipes(
            candles=candles,
            struct=trace["context"].get("structure", {}),
            sweeps={"codes": codes, "sweep_low": "EQL_SWEEP_BULL" in codes, "sweep_high": "EQH_SWEEP_BEAR" in codes, 
                    "equal_lows": trace["context"].get("equal_levels", {}).get("eq_lows", []),
                    "equal_highs": trace["context"].get("equal_levels", {}).get("eq_highs", [])},
            avwap=trace["context"].get("avwap", {}),
            squeeze={"state": trace["context"].get("squeeze", "NONE")},
            atr_val=local_atr if 'local_atr' in locals() else None
        )
        
        # Phase 23: Resolve contradictions (max 1 recipe)
        recipe_signals = resolve_conflicts(raw_signals)
        
        for sig in recipe_signals:
            # Phase 23: Multi-Timeframe Confirmation
            # Check 1h if current is 5/15m, check 15m if current is 1h
            htf_candles = candles_1h if timeframe != "1h" else candles_15m
            confirmed = _htf_confirms(sig.direction, htf_candles)
            
            sig_score = sig.raw_score
            if not confirmed:
                sig_score *= 0.5
                codes.append("HTF_CONFLICT")
                reasons.append(f"Recipe {sig.recipe} downgraded (HTF Conflict)")
            
            intel.recipes.append(sig)
            codes.append(f"{sig.recipe}_RECIPE")
            breakdown["momentum"] += sig_score / SCORE_MULTIPLIER
            reasons.append(f"Recipe: {sig.recipe} ({sig.direction})")
    except Exception as e:
        logger.warning(f"Recipe detection failed: {e}")

    # --- Candidates ---
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
    # -- Phase 19 CRITICAL-1: normalize score to fill 0-100 range --
    # Raw scores typically land in -30 to +30 range.
    # Scale by 3x so a raw 15 becomes 45 (the A+ threshold for 5m).
    # This means: 5 active signals ≈ raw 15 → normalized 45 → A+ tier.
    total_score = total_score * SCORE_MULTIPLIER

    # Map ML Mock / Fallback
    # If the score is extreme, we assume high algorithmic conviction.
    # Phase 19: align ML thresholds with normalized score range
    # After 3x multiplier: 25 = raw ~8.3 = genuine multi-signal confluence
    if total_score >= 25:
        codes.append("ML_CONFIDENCE_BOOST")
    elif total_score <= -25:
        codes.append("ML_SKEPTICISM")

    # -- Phase 19 FIX 5: compute direction + auto_rr early so codes reach confluence --
    direction = "LONG" if total_score > 0 else "SHORT" if total_score < 0 else "NEUTRAL"
    try:
        auto_rr = compute_auto_rr(candles, direction)
        codes.extend(auto_rr["codes"])
        trace["context"]["auto_rr"] = {
            "rr": auto_rr["rr"], "target": auto_rr["target"],
            "stop": auto_rr["stop"], "entry": auto_rr.get("entry"),
        }
    except Exception:
        pass

    # --- Confluence Rubric (Phase 22) ---
    # Sum signals from (Structure, Location, Anchors, Derivatives, Momentum, Volatility)
    rubric_score = 0
    rubric_details = {}

    def has_any(targets: List[str]) -> bool:
        return any(t in codes for t in targets)

    # 1. Structure
    struct_signals = ["STRUCTURE_BOS_BULL", "STRUCTURE_CHOCH_BULL", "BOS_CONTINUATION_RECIPE"] if direction == "LONG" else \
                     ["STRUCTURE_BOS_BEAR", "STRUCTURE_CHOCH_BEAR", "BOS_CONTINUATION_RECIPE"]
    if has_any(struct_signals):
        rubric_score += 1
        rubric_details["structure"] = True

    # 2. Location
    loc_signals = ["NEAR_POC", "BID_WALL_SUPPORT", "EQL_SWEEP_BULL", "PDL_SWEEP_BULL"] if direction == "LONG" else \
                  ["NEAR_POC", "ASK_WALL_RESISTANCE", "EQH_SWEEP_BEAR", "PDH_SWEEP_BEAR"]
    if has_any(loc_signals):
        rubric_score += 1
        rubric_details["location"] = True

    # 3. Anchors
    anchor_signals = ["AVWAP_RECLAIM_BULL", "AVWAP_ABOVE_1SD"] if direction == "LONG" else \
                     ["AVWAP_REJECT_BEAR", "AVWAP_BELOW_1SD"]
    if has_any(anchor_signals) or "HTF_REVERSAL_RECIPE" in codes:
        rubric_score += 1
        rubric_details["anchors"] = True

    # 4. Derivatives
    deriv_signals = ["FUNDING_LOW", "OI_SURGE_MINOR", "OI_SURGE_MAJOR", "BASIS_BULLISH"] if direction == "LONG" else \
                    ["FUNDING_HIGH", "OI_SURGE_MINOR", "OI_SURGE_MAJOR", "BASIS_BEARISH"]
    if has_any(deriv_signals):
        rubric_score += 1
        rubric_details["derivatives"] = True

    # 5. Momentum
    mom_signals = ["HTF_ALIGNED", "FLOW_TAKER_BULLISH", "SENTIMENT_BULL"] if direction == "LONG" else \
                  ["HTF_COUNTER", "FLOW_TAKER_BEARISH", "SENTIMENT_BEAR"]
    if has_any(mom_signals):
        rubric_score += 1
        rubric_details["momentum"] = True

    # 6. Volatility
    vol_signals = ["SQUEEZE_FIRE", "VOL_EXPANSION_RECIPE"]
    if has_any(vol_signals):
        rubric_score += 1
        rubric_details["volatility"] = True

    trace["rubric"] = {"score": rubric_score, "details": rubric_details}
    trace["confluence_score"] = rubric_score
    
    # --- Phase 27: Strict Vetoes (DISABLED - was hurting performance) ---
    # Vetoes disabled: pre-veto had +0.170 AvgR, post-veto had -0.525 AvgR
    # Re-enable after further tuning
    pass
    # blockers.append("Phase 27 vetoes disabled for performance")

    # Exit levels
    last_price = price.price if symbol == "BTC" else candles[-1].close
    local_atr = atr(candles, 14) or (last_price * 0.02)


    tp_cfg = TP_MULTIPLIERS.get(regime_name, TP_MULTIPLIERS["default"])
    tp1_mult = tp_cfg["tp1"]
    inv_mult = tp_cfg["inv"]
    
    # Phase 23: Recipe-Aware Execution Levels
    if intel.recipes:
        # Use levels from the primary recipe
        best_sig = intel.recipes[0]
        entry_zone = best_sig.entry_zone
        invalidation = best_sig.invalidation
        tp1 = best_sig.targets.get("tp1", last_price)
        tp2 = best_sig.targets.get("tp2", last_price)
        risk_size = best_sig.risk_size
        
        # Recalculate RR using recipe execution price (use tp2 for full R:R)
        exec_px = best_sig.exec_px
        risk = abs(exec_px - invalidation)
        reward = abs(tp2 - exec_px)
        rr = reward / risk if risk > 0 else 0.0
    else:
        # Generic ATR-based fallback
        entry_zone = f"{last_price:,.0f}"
        if direction == "LONG":
            invalidation = last_price - (local_atr * inv_mult * 2.0)
            tp1 = last_price + (local_atr * tp1_mult)
            tp2 = last_price + (local_atr * tp_cfg["tp2"])
        else:
            invalidation = last_price + (local_atr * inv_mult * 2.0)
            tp1 = last_price - (local_atr * tp1_mult)
            tp2 = last_price - (local_atr * tp_cfg["tp2"])

        risk = abs(last_price - invalidation)
        reward = abs(tp2 - last_price)
        rr = reward / risk if risk > 0 else 0.0

    min_rr = tf_cfg.get("min_rr", 1.2)
    if rr < min_rr:
        blockers.append(f"R:R {rr:.2f} below {min_rr:.2f} threshold")

    # Final Action/Tier Decision (after hard R:R gate)
    tier, action = _tier_and_action(int(abs(total_score)), blockers, timeframe, rubric_score)

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
        entry_zone=entry_zone,
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
