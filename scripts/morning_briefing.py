#!/usr/bin/env python3
"""
Morning Briefing Generator.
Reads latest alert data, intelligence layers, and performance stats.
Produces a plain-English briefing with actionable levels.

Usage: PYTHONPATH=. python scripts/morning_briefing.py
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
if not (BASE_DIR / "logs").exists():
    BASE_DIR = Path.cwd()
ALERTS_FILE = BASE_DIR / "logs" / "pid-129-alerts.jsonl"
AUDIT_FILE = BASE_DIR / "logs" / "audit.jsonl"
PORTFOLIO_FILE = BASE_DIR / "data" / "paper_portfolio.json"
OUTPUT_MD = BASE_DIR / "reports" / "morning_briefing.md"
OUTPUT_JSON = BASE_DIR / "reports" / "morning_briefing.json"


def _load_alerts(hours=24):
    """Load alerts from the last N hours."""
    if not ALERTS_FILE.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    alerts = []
    try:
        content = ALERTS_FILE.read_text(encoding="utf-8").strip()
        for line in content.split("\n"):
            if not line.strip():
                continue
            try:
                a = json.loads(line)
                ts = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    alerts.append(a)
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception:
        pass
    return alerts


def _load_latest_trace():
    """Get decision_trace from the most recent alert that has one."""
    if not ALERTS_FILE.exists():
        return {}
    try:
        lines = ALERTS_FILE.read_text(encoding="utf-8").strip().split("\n")
        for line in reversed(lines):
            try:
                a = json.loads(line)
                if "decision_trace" in a and a["decision_trace"]:
                    return a["decision_trace"]
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception:
        pass
    return {}


def _load_portfolio():
    """Load paper portfolio stats."""
    if not PORTFOLIO_FILE.exists():
        return None
    try:
        return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    except:
        return None


def _regime_emoji(regime):
    """Return emoji for regime type."""
    return {
        "trend": "📈",
        "range": "📊",
        "chop": "🌊",
        "vol_chop": "⚡",
    }.get(regime, "❓")


def _direction_sentence(direction, confidence):
    """Turn direction + confidence into English."""
    if direction == "LONG" and confidence >= 15:
        return "leaning bullish with moderate conviction"
    elif direction == "LONG":
        return "slightly bullish but low conviction"
    elif direction == "SHORT" and confidence >= 15:
        return "leaning bearish with moderate conviction"
    elif direction == "SHORT":
        return "slightly bearish but low conviction"
    return "neutral with no clear edge"


def _overnight_recap(alerts):
    """Summarize overnight activity."""
    if not alerts:
        return "No signals fired overnight."

    resolved = [a for a in alerts if a.get("resolved")]
    pending = [a for a in alerts if not a.get("resolved")]
    wins = [a for a in resolved if a.get("outcome", "").startswith("WIN")]
    losses = [a for a in resolved if a.get("outcome") == "LOSS"]

    parts = [f"{len(alerts)} signals fired overnight."]
    if resolved:
        parts.append(f"{len(wins)}W / {len(losses)}L resolved.")
    if pending:
        parts.append(f"{len(pending)} still pending.")

    # Best signal
    if alerts:
        best = max(alerts, key=lambda a: a.get("confidence", 0))
        parts.append(
            f"Best signal: {best.get('direction')} {best.get('strategy')} "
            f"on {best.get('timeframe')} (confidence {best.get('confidence')})."
        )
    return " ".join(parts)


def generate_briefing():
    """Main briefing generation logic."""
    now = datetime.now(timezone.utc)
    alerts_24h = _load_alerts(hours=24)
    alerts_7d = _load_alerts(hours=168)
    trace = _load_latest_trace()
    portfolio = _load_portfolio()
    ctx = trace.get("context", {})

    # --- Extract intelligence ---
    # Price
    price = trace.get("price", 0.0)
    if not price and alerts_24h:
        price = alerts_24h[-1].get("entry_price", 0.0)

    # Regime
    regime = trace.get("regime", "unknown")
    regime_icon = _regime_emoji(regime)

    # Squeeze
    squeeze = ctx.get("squeeze", "NONE")

    # POC
    vp = ctx.get("volume_profile", {})
    poc = vp.get("poc", 0)
    near_poc = vp.get("near_poc", False)

    # Liquidity
    liq = ctx.get("liquidity", {})
    bid_walls = liq.get("bid_walls", 0)
    ask_walls = liq.get("ask_walls", 0)

    # Macro
    macro = ctx.get("macro_correlation", {})
    dxy = macro.get("dxy", "neutral")
    gold = macro.get("gold", "neutral")

    # Confluence
    conf = ctx.get("confluence", {})
    strength = conf.get("strength", "WEAK")
    bull_count = conf.get("bullish_count", 0)
    bear_count = conf.get("bearish_count", 0)
    net = conf.get("net", 0)

    # Sentiment
    sent = ctx.get("sentiment", {})
    sent_score = sent.get("score", 0.0)

    # Direction from most recent alert
    latest_direction = "NEUTRAL"
    latest_confidence = 0
    if alerts_24h:
        latest = alerts_24h[-1]
        latest_direction = latest.get("direction", "NEUTRAL")
        latest_confidence = latest.get("confidence", 0)

    # --- Performance stats (7-day) ---
    resolved_7d = [a for a in alerts_7d if a.get("resolved")]
    wins_7d = [a for a in resolved_7d if a.get("outcome", "").startswith("WIN")]
    win_rate = (len(wins_7d) / len(resolved_7d) * 100) if resolved_7d else 0
    total_r = sum(a.get("r_multiple", 0) for a in resolved_7d)

    # --- Portfolio ---
    balance = 10000.0
    if portfolio:
        balance = portfolio.get("balance", 10000.0)
    pnl_pct = ((balance - 10000) / 10000) * 100

    # --- Build the briefing ---
    overnight = _overnight_recap(alerts_24h)
    bias_sentence = _direction_sentence(latest_direction, latest_confidence)

    # Actionable sentence
    if strength == "STRONG" and net > 0:
        action = f"Multiple bullish signals agree. Look for long entries on pullbacks to POC (${poc:,.0f}) or bid walls."
    elif strength == "STRONG" and net < 0:
        action = f"Multiple bearish signals agree. Consider shorts on rallies toward ask walls or if VWAP rejects."
    elif squeeze == "SQUEEZE_FIRE":
        action = "Squeeze just fired — expect a sharp directional move. Wait for direction confirmation before entering."
    elif squeeze == "SQUEEZE_ON":
        action = "Squeeze is building. Prepare for a breakout. Set alerts at POC and liquidity walls."
    elif regime == "chop" or regime == "vol_chop":
        action = "Market is choppy. Avoid trend trades. Only consider mean-reversion setups with tight stops."
    elif regime == "range":
        action = "Market is ranging. Fade the extremes. Buy near bid walls, sell near ask walls."
    elif regime == "trend" and latest_direction == "LONG":
        action = f"Trending bullish. Look for pullback entries on 15m/1h. Invalidation below ${poc:,.0f}."
    elif regime == "trend" and latest_direction == "SHORT":
        action = f"Trending bearish. Short on relief rallies. Invalidation above ${poc:,.0f}."
    else:
        action = "No clear edge. Stay flat and wait for confluence to develop."

    briefing_md = f"""# ☀️ Morning Briefing — {now.strftime("%A, %B %d %Y")}

**Generated:** {now.strftime("%Y-%m-%d %H:%M UTC")}

---

## 📍 Current State

- **BTC Price:** ${price:,.2f}
- **Regime:** {regime_icon} {regime.upper()}
- **Squeeze:** {squeeze}
- **System Bias:** {bias_sentence}

## 🧠 Intelligence Snapshot

| Layer | Reading |
|:------|:--------|
| POC (Price of Control) | ${poc:,.0f} ({'**AT POC**' if near_poc else 'away'}) |
| Liquidity | {bid_walls} bid walls / {ask_walls} ask walls |
| DXY | {dxy} |
| Gold | {gold} |
| Sentiment Score | {sent_score:.2f} |
| Confluence | {strength} ({bull_count}🟢 vs {bear_count}🔴, net={net:+d}) |

## 🌙 Overnight Recap

{overnight}

## 📊 7-Day Performance

- **Win Rate:** {win_rate:.0f}% ({len(wins_7d)}W / {len(resolved_7d) - len(wins_7d)}L of {len(resolved_7d)} resolved)
- **Total P&L:** {total_r:+.2f}R
- **Paper Balance:** ${balance:,.2f} ({pnl_pct:+.1f}%)

## 🎯 What To Do Today

> {action}

---
_Auto-generated by EMBER v5. Do not edit._
"""

    # JSON output for other agents
    briefing_json = {
        "generated_utc": now.isoformat(),
        "price": price,
        "regime": regime,
        "squeeze": squeeze,
        "direction": latest_direction,
        "confidence": latest_confidence,
        "poc": poc,
        "near_poc": near_poc,
        "bid_walls": bid_walls,
        "ask_walls": ask_walls,
        "dxy": dxy,
        "gold": gold,
        "confluence_strength": strength,
        "confluence_net": net,
        "sentiment_score": sent_score,
        "win_rate_7d": round(win_rate, 1),
        "total_r_7d": round(total_r, 2),
        "balance": balance,
        "action": action,
        "overnight_recap": overnight,
    }

    return briefing_md, briefing_json


def main():
    # Ensure output directory exists
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)

    briefing_md, briefing_json = generate_briefing()

    # Write markdown
    OUTPUT_MD.write_text(briefing_md, encoding="utf-8")
    print(f"Briefing written to {OUTPUT_MD}")

    # Write JSON
    OUTPUT_JSON.write_text(json.dumps(briefing_json, indent=2), encoding="utf-8")
    print(f"JSON written to {OUTPUT_JSON}")

    # Send to Telegram if configured
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        import httpx
        # Telegram has a 4096 char limit. Send the action + key stats only.
        tg_msg = (
            f"☀️ *EMBER Morning Briefing*\n\n"
            f"BTC: ${briefing_json['price']:,.0f} | {briefing_json['regime'].upper()}\n"
            f"Squeeze: {briefing_json['squeeze']}\n"
            f"Confluence: {briefing_json['confluence_strength']} "
            f"({briefing_json['confluence_net']:+d} net)\n"
            f"POC: ${briefing_json['poc']:,.0f}\n"
            f"7d: {briefing_json['win_rate_7d']:.0f}% WR | {briefing_json['total_r_7d']:+.1f}R\n\n"
            f"🎯 {briefing_json['action']}"
        )
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": tg_msg, "parse_mode": "Markdown"},
                timeout=10,
            )
            print(f"Telegram sent: {resp.status_code}")
        except Exception as e:
            print(f"Telegram failed: {e}")
    else:
        # print("Telegram not configured. Printing briefing to console:") # User might see this in chat, keeping it quiet unless verbose
        # print(briefing_md)
        pass


if __name__ == "__main__":
    main()
