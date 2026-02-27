import json
from typing import List, Optional, Dict
from engine import AlertScore
from core.logger import logger

def _format_intel_lines(score) -> str:
    """Render the 🧠 Intel: block from score.context. Returns empty string if nothing to show."""
    intel_lines = []
    if score.context.get("squeeze"):
        intel_lines.append(f"Squeeze: {score.context['squeeze']}")
    if score.context.get("sentiment"):
        s = score.context["sentiment"]
        intel_lines.append(f"Sentiment: {s['score']:.2f} ({s.get('bull_pct', 0)}% bull)")
    if score.context.get("volume_profile"):
        vp = score.context["volume_profile"]
        intel_lines.append(f"POC: ${vp['poc']:,.0f} ({'AT POC' if vp['near_poc'] else 'away'})")
    if score.context.get("liquidity"):
        liq = score.context["liquidity"]
        parts = []
        if liq.get("support"): parts.append(f"{liq['bid_walls']} bid walls")
        if liq.get("resistance"): parts.append(f"{liq['ask_walls']} ask walls")
        if parts: intel_lines.append(f"Liquidity: {', '.join(parts)}")
    if score.context.get("macro_correlation"):
        mc = score.context["macro_correlation"]
        intel_lines.append(f"Macro: DXY {mc['dxy']}, Gold {mc['gold']}")
    if score.context.get("confluence"):
        cf = score.context["confluence"]
        intel_lines.append(
            f"Confluence: {cf['strength']} ({cf['bullish_count']}🟢 vs {cf['bearish_count']}🔴)"
        )
    if intel_lines:
        return "\n🧠 Intel:\n" + "\n".join(f"  {l}" for l in intel_lines)
    return ""

def format_alert_msg(score: AlertScore, provider_context: dict) -> str:
    """Formats an AlertScore object into a readable string for notifications."""
    payload_for_display = {
        "symbol": score.symbol,
        "timeframe": score.timeframe,
        "action": score.action,
        "tier": score.tier,
        "direction": score.direction,
        "strategy_type": score.strategy_type,
        "confidence_score": score.confidence,
        "entry_zone": score.entry_zone,
        "invalidation_level": round(score.invalidation, 2),
        "tp1": round(score.tp1, 2),
        "tp2": round(score.tp2, 2),
        "rr_ratio": round(score.rr_ratio, 2),
        "context": {
            "regime": score.regime,
            "session": score.session,
            "quality": score.quality,
            "providers": provider_context,
        },
        "reason_codes": score.reason_codes,
        "score_breakdown": score.score_breakdown,
        "blockers": score.blockers,
        "decision_trace": score.decision_trace,
        "squeeze_state": provider_context.get("squeeze"),
        "sentiment": provider_context.get("sentiment"),
    }
    return f"--- ALERT ---\n*{score.symbol} {score.timeframe} {score.action} ({score.tier})*\n```{json.dumps(payload_for_display, indent=2)}```" + _format_intel_lines(score)

def print_market_overview(alerts: List[AlertScore]):
    """Prints a terminal-friendly market overview table."""
    print("\n" + "="*50)
    print("  MARKET OVERVIEW: BTC")
    print("="*50)
    print(f"  {'TIMEFRAME':<10} | {'ACTION':<10} | {'DIRECTION':<10} | {'SCORE':<5}")
    print("-" * 50)
    
    btc_alerts = [a for a in alerts if a.symbol == "BTC"]
    if btc_alerts:
        for a in btc_alerts:
            print(f"  {a.timeframe:<10} | {a.action:<10} | {a.direction:<10} | {a.confidence:<5}")
    else:
        print("  No BTC alerts computed.")
    print("="*50)

def print_best_setup(best_alert: Optional[AlertScore]):
    """Prints the details of the best identified setup."""
    if not best_alert:
        logger.info("No best BTC alert identified for summary.")
        return

    print("\n" + "="*50)
    print(f"  BEST BTC SETUP: {best_alert.symbol} ({best_alert.timeframe})")
    print("="*50)
    print(f"  • ACTION:      {best_alert.action} ({best_alert.tier})")
    print(f"  • DIRECTION:   {best_alert.direction}")
    print(f"  • CONFIDENCE:  {best_alert.confidence}/100")
    print(f"  • STRATEGY:    {best_alert.strategy_type}")
    print("-" * 50)
    if best_alert.direction != "NEUTRAL":
        print(f"  • ENTRY ZONE:  {best_alert.entry_zone}")
        print(f"  • TARGET 1:    ${best_alert.tp1:,.2f}")
        print(f"  • TARGET 2:    ${best_alert.tp2:,.2f}")
        print(f"  • STOP LOSS:   ${best_alert.invalidation:,.2f}")
        print(f"  • R:R RATIO:   {best_alert.rr_ratio:.2f}")
    else:
        print("  • No clear trade setup currently.")
    print("-" * 50)
    print(f"  • REASONS:     {', '.join(best_alert.reasons)}")
    if best_alert.blockers:
        print(f"  • BLOCKERS:    {', '.join(best_alert.blockers)}")
    print("="*50 + "\n")
    logger.info("Best BTC alert details displayed.", extra={'symbol': best_alert.symbol, 'timeframe': best_alert.timeframe, 'confidence': best_alert.confidence})

def print_timeframe_guide():
    """Prints a guide explaining the timeframes."""
    print("  TIMEFRAME GUIDE:")
    print("  • 5m:  Scalping (Fast action, 15-60 min hold)")
    print("  • 15m: Day Trading (Balanced, 1-4 hour hold)")
    print("  • 1h:  Swing Trading (Trend following, 4-24 hour hold)")
    print("\n")


def bot_schema_json(score: AlertScore) -> str:
    """
    Standardizes the alert into a machine-consumable JSON object for trading bots.
    Matches standard bot schema: (type, setup_conditions, risk_rules, execution_details).
    """
    # Extract recipe data if available
    recipe_name = "NONE"
    if score.intel and score.intel.recipes:
        recipe_name = score.intel.recipes[0].recipe

    schema = {
        "metadata": {
            "symbol": score.symbol,
            "timeframe": score.timeframe,
            "timestamp_utc": score.last_candle_ts,
            "version": "2.2.0"
        },
        "type": {
            "action": score.action,
            "tier": score.tier,
            "recipe": recipe_name,
            "strategy": score.strategy_type
        },
        "setup_conditions": {
            "direction": score.direction,
            "confidence": score.confidence,
            "reason_codes": score.reason_codes,
            "rubric_score": score.decision_trace.get("rubric", {}).get("score", 0),
            "rubric_details": score.decision_trace.get("rubric", {}).get("details", {})
        },
        "risk_rules": {
            "risk_size_units": score.intel.recipes[0].risk_size if (score.intel and score.intel.recipes) else 0.0,
            "invalidation_level": round(score.invalidation, 2),
            "targets": {
                "tp1": round(score.tp1, 2),
                "tp2": round(score.tp2, 2)
            },
            "rr_ratio": round(score.rr_ratio, 2)
        },
        "execution_details": {
            "entry_zone": score.entry_zone,
            "execution_type": score.intel.recipes[0].entry_zone if (score.intel and score.intel.recipes) else "MARKET",
            "session": score.session
        }
    }
    return json.dumps(schema, indent=2)
