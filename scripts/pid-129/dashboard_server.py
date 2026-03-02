import base64
import hashlib
import json
import os
import struct
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if not (BASE_DIR / "scripts").exists():
    BASE_DIR = Path.cwd()

# Ensure project root is in path for 'collectors' import
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

HOST = "0.0.0.0"
PORT = 8002
DASHBOARD_PATH = BASE_DIR / "dashboard.html"
ALERTS_PATH = BASE_DIR / "logs" / "pid-129-alerts.jsonl"
PORTFOLIO_PATH = BASE_DIR / "data" / "paper_portfolio.json"
OVERRIDES_PATH = BASE_DIR / "data" / "dashboard_overrides.json"

_LAST_CONTEXT = {}  # Last-known intelligence context (anti-flicker)
_LAST_REBUILD = 0.0

try:
    from collectors.price import fetch_btc_price
    from collectors.flows import fetch_flow_context
    from collectors.derivatives import fetch_derivatives_context
    _HAS_COLLECTORS = True
except ImportError:
    _HAS_COLLECTORS = False
    print("Warning: Could not import collectors. Derivatives/Price alpha may be missing.")

try:
    from config import TIMEFRAME_RULES
except Exception:
    TIMEFRAME_RULES = {}

# Module-level shared state
_STATE_LOCK = threading.Lock()
_CACHED_DATA = {}          # Latest dashboard JSON payload
_LAST_ALERT_MTIME = 0.0    # os.stat() mtime of alerts JSONL
_LAST_PORTFOLIO_MTIME = 0.0 # os.stat() mtime of portfolio JSON
_OVERRIDES = {}


def _safe_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_overrides():
    global _OVERRIDES
    if OVERRIDES_PATH.exists():
        try:
            _OVERRIDES = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _OVERRIDES = {}
    return _OVERRIDES


def _save_overrides():
    OVERRIDES_PATH.write_text(json.dumps(_OVERRIDES, indent=2), encoding="utf-8")


def _match_recipe(alert_id, alerts):
    """Find the recipe name from the alerts JSONL for a given alert_id."""
    for a in alerts:
        if a.get("alert_id") == alert_id or a.get("id") == alert_id:
            dt = a.get("decision_trace", {})
            codes = dt.get("codes", [])
            for c in codes:
                if c.endswith("_RECIPE"):
                    return c.replace("_RECIPE", "")
            return "NO_RECIPE"
    return "UNKNOWN"


def _light_alerts(alerts):
    """Create lightweight alert summaries for the WS stream."""
    light = []
    for i, a in enumerate(alerts):
        dt = a.get("decision_trace", {}).copy()
        # Phase 24: keep the full decision_trace.context for radar/key-levels.
        # Intel and raw candle data are already excluded by the specific dict keys below.
        
        light.append({
            "idx": i,
            "id": a.get("alert_id") or a.get("id"),
            "symbol": a.get("symbol"),
            "timeframe": a.get("timeframe"),
            "direction": a.get("direction"),
            "confidence": a.get("confidence"),
            "tier": a.get("tier"),
            "action": a.get("action"),
            "entry_zone": a.get("entry_zone"),
            "invalidation": a.get("invalidation"),
            "tp1": a.get("tp1"),
            "tp2": a.get("tp2"),
            "rr_ratio": a.get("rr_ratio"),
            "regime": a.get("regime"),
            "session": a.get("session"),
            "strategy_type": a.get("strategy_type"),
            "reason_codes": a.get("reason_codes", []),
            "score_breakdown": a.get("score_breakdown", {}),
            "timestamp": a.get("timestamp"),
            "price": a.get("price") or a.get("entry_price"),
            "recipe": a.get("recipe_name") or _match_recipe(a.get("alert_id") or a.get("id"), alerts),
            "decision_trace": dt,
        })
    return light


def _load_alerts(limit=50):
    if not ALERTS_PATH.exists():
        return []
    try:
        # Use a more robust way to read on Windows to avoid sharing violations
        with open(ALERTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            rows = []
            for line in lines:
                if not line.strip(): continue
                try:
                    row = json.loads(line)
                    # ── Phase 26 Gap 3: Filter junk alerts ──
                    if row.get("strategy") in (None, "TEST", "SYNTHETIC"):
                        continue
                    rows.append(row)
                except: continue
            return rows[-limit:]
    except Exception as e:
        print(f"Error loading alerts: {e}")
        return []


def _latest_price(alerts):
    for alert in reversed(alerts):
        # Look for price in various possible fields
        for key in ("price", "mark_price", "entry", "entry_price", "last_price"):
            value = alert.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    return 0.0


def _portfolio_stats(portfolio, current_price=0.0, alerts=None):
    """
    Calculate comprehensive trading analytics from paper portfolio.
    """
    closed = portfolio.get("closed_trades", []) if isinstance(portfolio, dict) else []
    
    # ── Phase 26 Gap 2 Fix: Fall back to JSONL outcomes if portfolio file is empty ──
    if not closed and alerts:
        for a in alerts:
            outcome = a.get("outcome")
            r = a.get("r_multiple")
            if outcome in ("WIN_TP1", "WIN_TP2", "LOSS", "TIMEOUT") and isinstance(r, (int, float)):
                closed.append({
                    "r_multiple": r,
                    "direction": a.get("direction", "NEUTRAL"),
                    "alert_id": a.get("alert_id") or a.get("id"),
                    "outcome": outcome,
                    "timeframe": a.get("timeframe", "UNKNOWN")
                })

    r_values = [t.get("r_multiple") for t in closed if isinstance(t.get("r_multiple"), (int, float))]
    
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r < 0]
    count = len(r_values)
    
    win_rate = (len(wins) / count * 100.0) if count else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    avg_r = (sum(r_values) / count) if count else 0.0

    # Directional Stats
    long_trades = []
    short_trades = []
    for t in closed:
        direction = t.get("direction", "NEUTRAL")
        r = t.get("r_multiple", 0)
        if direction == "LONG":
            long_trades.append(r)
        elif direction == "SHORT":
            short_trades.append(r)

    def _calc_subset(rs):
        c = len(rs)
        ws = [r for r in rs if r > 0]
        wr = (len(ws) / c * 100.0) if c else 0.0
        ar = (sum(rs) / c) if c else 0.0
        tr = sum(rs)
        return {"count": c, "wins": len(ws), "win_rate": round(wr, 1), "avg_r": round(ar, 2), "total_r": round(tr, 2)}

    long_stats = _calc_subset(long_trades)
    short_stats = _calc_subset(short_trades)

    # Recipe Stats
    recipe_performance = {}
    if alerts:
        for t in closed:
            alert_id = t.get("alert_id")
            recipe = _match_recipe(alert_id, alerts)
            if recipe not in recipe_performance:
                recipe_performance[recipe] = []
            recipe_performance[recipe].append(t.get("r_multiple", 0))

    recipe_stats = {}
    for name, rs in recipe_performance.items():
        c = len(rs)
        ws = [r for r in rs if r > 0]
        wr = (len(ws) / c * 100.0) if c else 0.0
        ar = (sum(rs) / c) if c else 0.0
        recipe_stats[name] = {"count": c, "wins": len(ws), "win_rate": round(wr, 1), "avg_r": round(ar, 2)}

    # Timeframe Stats
    tf_performance = {}
    for t in closed:
        tf = t.get("timeframe", "UNKNOWN")
        if tf not in tf_performance:
            tf_performance[tf] = []
        tf_performance[tf].append(t.get("r_multiple", 0))
    
    tf_stats = {}
    for tf, rs in tf_performance.items():
        tf_stats[tf] = _calc_subset(rs)

    # Session and Regime edge attribution (via alert metadata lookup)
    session_performance = {}
    regime_performance = {}
    if alerts:
        alert_meta = {}
        for a in alerts:
            aid = a.get("alert_id") or a.get("id")
            if aid is not None:
                alert_meta[aid] = {
                    "session": str(a.get("session") or "UNKNOWN").lower(),
                    "regime": str(a.get("regime") or "UNKNOWN").lower(),
                }

        for t in closed:
            aid = t.get("alert_id")
            meta = alert_meta.get(aid, {})
            r = t.get("r_multiple", 0)

            session = meta.get("session", "unknown")
            regime = meta.get("regime", "unknown")

            session_performance.setdefault(session, []).append(r)
            regime_performance.setdefault(regime, []).append(r)

    session_stats = {name: _calc_subset(rs) for name, rs in session_performance.items()}
    regime_stats = {name: _calc_subset(rs) for name, rs in regime_performance.items()}

    # Kelly Criterion
    # Kelly % = W - [(1 - W) / R]
    # W = win probability (decimal)
    # R = average win / average loss ratio (absolute values)
    if wins and losses:
        W = len(wins) / len(r_values)
        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))
        R = avg_win / avg_loss if avg_loss > 0 else 1.0
        kelly = W - ((1 - W) / R)
        kelly_pct = round(max(0.0, min(kelly / 4, 0.25)), 4)  # Quarter Kelly, capped at 25%
    else:
        kelly_pct = 0.0

    # Unrealized PnL
    open_positions = portfolio.get("positions", [])
    open_upnl = 0.0
    if current_price > 0:
        for pos in open_positions:
            entry = pos.get("entry_price", 0)
            size = pos.get("size_usdt", 0)
            direction = pos.get("direction", "LONG")
            if entry > 0 and size > 0:
                if direction == "LONG":
                    pnl = (current_price - entry) / entry * size
                else:
                    pnl = (entry - current_price) / entry * size
                open_upnl += pnl

    # Drawdown
    balance = portfolio.get("balance", 10000)
    peak = portfolio.get("peak_balance", balance)
    drawdown_pct = round(((peak - balance) / peak) * 100, 2) if peak > 0 else 0.0

    streak = 0
    for value in reversed(r_values):
        if value < 0:
            streak -= 1
        elif value > 0:
            streak += 1
        else:
            continue

    return {
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_r": round(avg_r, 2),
        "streak": streak,
        "total_trades": count,
        "total_r": round(sum(r_values), 2),
        "long_stats": long_stats,
        "short_stats": short_stats,
        "recipe_stats": recipe_stats,
        "tf_stats": tf_stats,
        "session_stats": session_stats,
        "regime_stats": regime_stats,
        "kelly_pct": kelly_pct,
        "open_upnl": round(open_upnl, 2),
        "drawdown_pct": drawdown_pct
    }


def _estimate_spread(alerts):
    """Extract real spread from orderbook data in latest alert, or estimate from price data."""
    # Try to get a realistic spread from orderbook liquidity context
    for alert in reversed(alerts):
        dt_ctx = (alert.get("decision_trace") or {}).get("context", {})
        liq = dt_ctx.get("liquidity", {})
        if isinstance(liq, dict) and liq.get("bid_walls", -1) >= 0:
            mid = 0
            for key in ("entry_price", "price"):
                v = alert.get(key)
                if isinstance(v, (int, float)) and v > 0:
                    mid = v
                    break
            if mid > 0:
                return max(round(mid * 0.00004, 2), 0.50)  # ~0.004% = realistic BTC perp spread (~$3.60 at $90k)
    # Fallback: estimate from price deltas across recent alerts
    prices = []
    for alert in reversed(alerts[-10:]):
        for key in ("entry_price", "price"):
            v = alert.get(key)
            if isinstance(v, (int, float)) and v > 0:
                prices.append(v)
                break
    if len(prices) >= 2:
        diffs = [abs(prices[i] - prices[i+1]) for i in range(len(prices)-1)]
        return min(max(min(diffs), 0.50), 50.0)
    return 1.0


def _compute_profit_preflight(alerts, stats, circuit_breaker, data_age_seconds, overrides, spread, flows, derivatives):
    """Find best long/short candidates and return deterministic execution playbook."""
    now = time.time()
    min_score = int(overrides.get("min_score", 65) or 65)
    taker_ratio = float((flows or {}).get("taker_ratio") or 1.0)
    crowding_score = float((flows or {}).get("crowding_score") or 0.0)
    funding_rate = float((derivatives or {}).get("funding_rate") or 0.0)
    oi_change_pct = float((derivatives or {}).get("oi_change_pct") or 0.0)

    def _parse_age_seconds(ts):
        if not ts:
            return 999999.0
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
        except Exception:
            return 999999.0

    def _tf_min_rr(tf):
        cfg = TIMEFRAME_RULES.get(str(tf), {}) if isinstance(TIMEFRAME_RULES, dict) else {}
        try:
            return float(cfg.get("min_rr", 1.2) or 1.2)
        except Exception:
            return 1.2

    def _gate_candidate(c):
        reds, ambers = [], []
        if circuit_breaker.get("active"):
            reds.append(circuit_breaker.get("reason") or "Circuit breaker active")
        if float(data_age_seconds or 0) > 120:
            reds.append(f"Data stale ({float(data_age_seconds or 0):.0f}s > 120s)")
        if float(spread or 0) > 10:
            reds.append(f"Spread too wide (${float(spread or 0):.2f} > $10)")
        elif float(spread or 0) >= 5:
            ambers.append(f"Spread caution (${float(spread or 0):.2f})")

        if c is None:
            return {"verdict": "RED", "blockers": ["No candidate"], "cautions": [], "passes": False}

        min_rr = c["min_rr"]
        if c["rr_ratio"] < min_rr:
            reds.append(f"R:R {c['rr_ratio']:.2f} below {min_rr:.2f} threshold")
        if c["confidence"] < min_score:
            reds.append(f"Confidence {c['confidence']:.0f} below min score {min_score}")
        if c["age_seconds"] > 600:
            reds.append(f"Signal stale ({c['age_seconds']:.0f}s > 600s)")

        if c["direction"] == "LONG":
            if crowding_score >= 2.0:
                ambers.append(f"Crowding risk LONG ({crowding_score:.2f})")
            if funding_rate >= 0.0005 and oi_change_pct > 0:
                ambers.append("Derivatives crowded LONG (funding high + OI up)")
            if taker_ratio < 0.75:
                ambers.append("Orderflow opposes LONG (heavy sells)")
        else:
            if crowding_score <= -2.0:
                ambers.append(f"Crowding risk SHORT ({crowding_score:.2f})")
            if funding_rate <= -0.0005 and oi_change_pct > 0:
                ambers.append("Derivatives crowded SHORT (funding very negative + OI up)")
            if taker_ratio > 1.35:
                ambers.append("Orderflow opposes SHORT (heavy buys)")

        verdict = "RED"
        passes = False
        if not reds:
            verdict = "GREEN" if len(ambers) <= 1 else "AMBER"
            passes = verdict == "GREEN"
        return {"verdict": verdict, "blockers": reds, "cautions": ambers, "passes": passes}

    def _format_candidate(c):
        if not c:
            return None
        a = c["alert"]
        gate = _gate_candidate(c)
        return {
            "id": a.get("alert_id") or a.get("id"),
            "symbol": a.get("symbol"),
            "timeframe": a.get("timeframe"),
            "direction": c["direction"],
            "confidence": round(c["confidence"], 1),
            "rr_ratio": round(c["rr_ratio"], 2),
            "age_seconds": round(c["age_seconds"], 1),
            "entry_zone": a.get("entry_zone") or a.get("entry_price") or a.get("price"),
            "invalidation": a.get("invalidation"),
            "tp1": a.get("tp1"),
            "tp2": a.get("tp2"),
            "recipe": c["recipe"],
            "expectancy_hint": c["expectancy_hint"],
            "reason_codes": c["reason_codes"],
            "gate_status": gate["verdict"],
            "blockers": gate["blockers"],
            "cautions": gate["cautions"],
            "min_rr": c["min_rr"],
        }

    candidates_by_side = {"LONG": [], "SHORT": []}
    for a in alerts:
        direction = str(a.get("direction") or "").upper()
        if direction not in candidates_by_side:
            continue
        confidence = float(a.get("confidence") or 0)
        try:
            rr = float(a.get("rr_ratio") or 0)
        except Exception:
            rr = 0.0
        age_s = _parse_age_seconds(a.get("timestamp"))
        recipe = a.get("recipe_name") or _match_recipe(a.get("alert_id") or a.get("id"), alerts)
        muted_until = (overrides.get("muted_recipes", {}) or {}).get(recipe, 0)
        if muted_until and muted_until > now:
            continue
        expectancy_hint = round((confidence / 100.0) * max(0.0, rr), 3)
        candidates_by_side[direction].append({
            "alert": a,
            "direction": direction,
            "confidence": confidence,
            "rr_ratio": rr,
            "age_seconds": age_s,
            "expectancy_hint": expectancy_hint,
            "recipe": recipe,
            "reason_codes": ((a.get("decision_trace") or {}).get("codes") or [])[:5],
            "min_rr": _tf_min_rr(a.get("timeframe")),
            "passes_confidence": confidence >= min_score,
            "passes_rr": rr >= _tf_min_rr(a.get("timeframe")),
            "passes_freshness": age_s <= 600,
        })

    for side in candidates_by_side:
        candidates_by_side[side].sort(
            key=lambda c: (
                c["passes_confidence"],
                c["passes_rr"],
                c["passes_freshness"],
                c["expectancy_hint"],
                c["confidence"],
            ),
            reverse=True,
        )

    best_long = candidates_by_side["LONG"][0] if candidates_by_side["LONG"] else None
    best_short = candidates_by_side["SHORT"][0] if candidates_by_side["SHORT"] else None
    long_out = _format_candidate(best_long)
    short_out = _format_candidate(best_short)

    execute_pool = [c for c in (long_out, short_out) if c and c.get("gate_status") == "GREEN"]
    if execute_pool:
        execute_pool.sort(key=lambda c: (c.get("expectancy_hint", 0), c.get("confidence", 0)), reverse=True)
        winner = execute_pool[0]
        operator_decision = f"EXECUTE {winner['direction']}"
    else:
        operator_decision = "WAIT"

    best_for_legacy = None
    best_internal = None
    merged = [c for c in (long_out, short_out) if c]
    merged_internal = [c for c in (best_long, best_short) if c]
    if merged:
        merged.sort(key=lambda c: (c.get("expectancy_hint", 0), c.get("confidence", 0)), reverse=True)
        best_for_legacy = merged[0]
    if merged_internal:
        merged_internal.sort(key=lambda c: (c.get("expectancy_hint", 0), c.get("confidence", 0)), reverse=True)
        best_internal = merged_internal[0]

    trap_risk_message = "Trap Risk: Normal"
    if funding_rate >= 0.0005 and oi_change_pct > 0 and crowding_score >= 2.0:
        trap_risk_message = "Trap Risk: LONG crowded (high funding + OI up + crowding high)"
    elif funding_rate <= -0.0005 and oi_change_pct > 0 and crowding_score <= -2.0:
        trap_risk_message = "Trap Risk: SHORT squeeze risk (very negative funding + OI up + crowding bearish)"

    best = best_internal
    checks = [
        {
            "name": "Circuit Breaker",
            "ok": not bool(circuit_breaker.get("active")),
            "detail": circuit_breaker.get("reason") or "Portfolio risk state clear",
        },
        {
            "name": "Data Freshness",
            "ok": float(data_age_seconds or 0) <= 60,
            "detail": f"Dashboard data age {float(data_age_seconds or 0):.0f}s",
        },
        {
            "name": "Execution Spread",
            "ok": float(spread or 0) <= 8.0,
            "detail": f"Estimated spread ${float(spread or 0):.2f}",
        },
        {
            "name": "Orderflow Bias",
            "ok": 0.7 <= float(taker_ratio or 1.0) <= 1.5,
            "detail": f"Taker ratio {float(taker_ratio or 1.0):.2f}",
        },
        {
            "name": "Candidate Available",
            "ok": best is not None,
            "detail": "Found qualifying BTC setup" if best else "No trade candidate with current filters",
        },
    ]

    if best:
        checks.extend(
            [
                {
                    "name": "Confidence Threshold",
                    "ok": best["passes_confidence"],
                    "detail": f"{best['confidence']:.0f} vs min {min_score}",
                },
                {
                    "name": "Risk/Reward",
                    "ok": best["passes_rr"],
                    "detail": f"R:R {best['rr_ratio']:.2f} (needs >= {best.get('min_rr', 1.2):.2f})",
                },
                {
                    "name": "Signal Freshness",
                    "ok": best["passes_freshness"],
                    "detail": f"Signal age {best['age_seconds']:.0f}s",
                },
            ]
        )

    ready = all(c["ok"] for c in checks)

    out_best = None
    if best:
        a = best["alert"]
        out_best = {
            "id": a.get("alert_id") or a.get("id"),
            "symbol": a.get("symbol"),
            "timeframe": a.get("timeframe"),
            "direction": a.get("direction"),
            "confidence": best["confidence"],
            "rr_ratio": best["rr_ratio"],
            "price": a.get("price") or a.get("entry_price"),
            "entry_zone": a.get("entry_zone"),
            "invalidation": a.get("invalidation"),
            "tp1": a.get("tp1"),
            "recipe": best["recipe"],
            "expectancy_hint": best["expectancy_hint"],
        }

    return {
        "ready": ready,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "best_trade": out_best,
        "candidate_count": len(candidates_by_side["LONG"]) + len(candidates_by_side["SHORT"]),
        "min_score": min_score,
        "message": "Profit lock armed: best candidate is ready" if ready else "Profit lock blocked: review failed checks",
        "best_overall": best_for_legacy,
        "best_long_candidate": long_out,
        "best_short_candidate": short_out,
        "operator_decision": operator_decision,
        "trap_risk_message": trap_risk_message,
    }



def get_dashboard_data():
    global _LAST_CONTEXT
    try:
        # Load all recent alerts for calculations, but only send limited summaries to WS
        all_recent_alerts = _load_alerts(limit=50)

        # ── Phase 25: Extract vol regime from the latest alert's decision trace ──
        vol_regime = "normal"
        for a in reversed(all_recent_alerts):
            dt_ctx = (a.get("decision_trace") or {}).get("context", {})
            vi = dt_ctx.get("volume_impulse", {})
            if isinstance(vi, dict) and vi.get("regime"):
                vol_regime = vi["regime"].lower()
                break

        # ── Phase 25: Auto-pilot dynamic muting ──
        auto_muted_recipes = {}
        now = time.time()
        auto_expiry = now + 120  # Auto-mutes last 2 minutes (re-evaluated every watcher cycle)

        if vol_regime == "expansion":
            # During expansion: suppress counter-trend / mean-reversion recipes
            for name in ("HTF_REVERSAL",):
                auto_muted_recipes[name] = auto_expiry
        elif vol_regime == "low":
            # During low-vol range: suppress trend-continuation recipes
            for name in ("BOS_CONTINUATION", "VOL_EXPANSION"):
                auto_muted_recipes[name] = auto_expiry

        overrides = _load_overrides().copy()
        
        # Merge auto-pilot mutes with manual mutes (auto does NOT overwrite longer manual mutes)
        if auto_muted_recipes:
            # We don't want to mutate the global _OVERRIDES dictionary
            merged_muted = overrides.get("muted_recipes", {}).copy()
            for recipe_name, auto_exp in auto_muted_recipes.items():
                existing_exp = merged_muted.get(recipe_name, 0)
                if auto_exp > existing_exp:
                    merged_muted[recipe_name] = auto_exp
            overrides["muted_recipes"] = merged_muted
        
        # Apply filters from overrides
        alerts = all_recent_alerts
        if overrides.get("min_score"):
            alerts = [a for a in alerts if (a.get("confidence", 0) >= overrides["min_score"])]
        if overrides.get("direction_filter"):
            alerts = [a for a in alerts if a.get("direction") == overrides["direction_filter"]]
        if overrides.get("muted_recipes"):
            now = time.time()
            valid_alerts = []
            for a in alerts:
                recipe = a.get("recipe_name") or _match_recipe(a.get("alert_id") or a.get("id"), all_recent_alerts)
                expiry = overrides["muted_recipes"].get(recipe, 0)
                if expiry < now:
                    valid_alerts.append(a)
                else:
                    # In Phase 25, we continue to filter alerts if they are muted
                    pass
            alerts = valid_alerts
        

        portfolio = _safe_json(PORTFOLIO_PATH, {"balance": 10000, "positions": [], "closed_trades": [], "max_drawdown": 0})

        # ── Phase 26: Stale Alert Hardening ──
        last_alert_time = 0.0
        if all_recent_alerts:
            try:
                ts_str = all_recent_alerts[-1].get("timestamp", "")
                if ts_str:
                    ts_clean = ts_str.split(".")[0].replace("Z", "").replace("T", " ")
                    dt_last = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
                    last_alert_time = dt_last.replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                pass

        # ── Engine heartbeat: decouple "engine alive" from "tradeable alert generated" ──
        # data/last_cycle.json is written by app.py on every run() call, even when
        # all signals are NO-TRADE.  Using it for alerts_stale means the Risk Gate
        # stays green in quiet markets where no signals meet the trade threshold.
        last_cycle_time = 0.0
        try:
            hb = _safe_json(BASE_DIR / "data" / "last_cycle.json", {})
            hb_ts = hb.get("timestamp", "")
            if hb_ts:
                hb_clean = hb_ts.split(".")[0].replace("Z", "").replace("T", " ")
                last_cycle_time = datetime.strptime(hb_clean, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            pass

        now_ts = datetime.now(timezone.utc).timestamp()
        # Liveness is based on engine heartbeat; fall back to last alert when no heartbeat yet.
        engine_time = last_cycle_time if last_cycle_time > 0 else last_alert_time
        alerts_stale = (now_ts - engine_time > 120) or (engine_time == 0)
        # data_age_seconds still reflects last tradeable alert age (useful context for operator).
        data_age_seconds = now_ts - last_alert_time if last_alert_time > 0 else 9999

        mid = _latest_price(all_recent_alerts)
        # Prefer the heartbeat price (written every cycle by app.py) over a stale alert price.
        hb_price = hb.get("btc_price") if isinstance(hb, dict) else None
        if hb_price and hb_price > 0:
            mid = hb_price
        taker_ratio = 1.0

        if not alerts_stale:
            for a in reversed(all_recent_alerts):
                codes = (a.get("decision_trace") or {}).get("codes", [])
                if "FLOW_TAKER_BULLISH" in codes:
                    taker_ratio = 1.4
                    break
                elif "FLOW_TAKER_BEARISH" in codes:
                    taker_ratio = 0.6
                    break

        budget = {"remaining": 8}
        if alerts_stale and _HAS_COLLECTORS:
            try:
                from collectors.base import BudgetManager
                budget = BudgetManager()
                price_snap = fetch_btc_price(budget)
                if price_snap.healthy and price_snap.price > 0:
                    mid = price_snap.price
                flow_snap = fetch_flow_context(budget)
                if flow_snap.healthy:
                    taker_ratio = flow_snap.taker_ratio
            except Exception:
                pass

        spread = _estimate_spread(all_recent_alerts) if mid else 0.0

        # ── Phase 26: Derivatives context ──
        flows = {"taker_ratio": round(taker_ratio, 2), "long_short_ratio": 1.0, "crowding_score": 0.0, "healthy": False, "source": "fallback"}
        if _HAS_COLLECTORS:
            try:
                flow_ctx = fetch_flow_context(budget)
                flows = {
                    "taker_ratio": flow_ctx.taker_ratio,
                    "long_short_ratio": flow_ctx.long_short_ratio,
                    "crowding_score": flow_ctx.crowding_score,
                    "source": flow_ctx.source,
                    "healthy": flow_ctx.healthy,
                }
                if flow_ctx.healthy:
                    taker_ratio = flow_ctx.taker_ratio
            except Exception:
                flows = {"taker_ratio": round(taker_ratio, 2), "long_short_ratio": 1.0, "crowding_score": 0.0, "healthy": False, "source": "error"}

        derivatives = {"funding_rate": 0.0, "oi_change_pct": 0.0, "basis_pct": 0.0, "healthy": False, "source": "none"}
        if _HAS_COLLECTORS:
            try:
                deriv_ctx = fetch_derivatives_context(budget)
                derivatives = {
                    "funding_rate": deriv_ctx.funding_rate,
                    "oi_change_pct": deriv_ctx.oi_change_pct,
                    "basis_pct": deriv_ctx.basis_pct,
                    "source": deriv_ctx.source,
                    "healthy": deriv_ctx.healthy
                }
            except Exception:
                derivatives = {"funding_rate": 0.0, "oi_change_pct": 0.0, "basis_pct": 0.0, "healthy": False, "source": "error"}

        # ── Phase 26: Cache the richest decision_trace.context for display ──
        global _LAST_CONTEXT
        for a in reversed(all_recent_alerts):
            ctx = (a.get("decision_trace") or {}).get("context", {})
            if ctx and len(ctx) > len(_LAST_CONTEXT):
                _LAST_CONTEXT = ctx
                break

        # ── Phase 25: Extract vol regime from the latest alert's decision trace ──
        vol_regime = "normal"
        for a in reversed(all_recent_alerts):
            dt_ctx = (a.get("decision_trace") or {}).get("context", {})
            vi = dt_ctx.get("volume_impulse", {})
            if isinstance(vi, dict) and vi.get("regime"):
                vol_regime = vi["regime"].lower()
                break

        # ── Phase 25: Auto-pilot dynamic muting ──
        auto_muted_recipes = {}
        now = time.time()
        auto_expiry = now + 120  # Auto-mutes last 2 minutes

        if vol_regime == "expansion":
            for name in ("HTF_REVERSAL",):
                auto_muted_recipes[name] = auto_expiry
        elif vol_regime == "low":
            for name in ("BOS_CONTINUATION", "VOL_EXPANSION"):
                auto_muted_recipes[name] = auto_expiry

        overrides = _load_overrides().copy()
        if auto_muted_recipes:
            merged_muted = overrides.get("muted_recipes", {}).copy()
            for recipe_name, auto_exp in auto_muted_recipes.items():
                existing_exp = merged_muted.get(recipe_name, 0)
                if auto_exp > existing_exp:
                    merged_muted[recipe_name] = auto_exp
            overrides["muted_recipes"] = merged_muted

        bs_filter = "CLEAR"
        bs_severity = 0  # 0=clear, 1=caution, 2=danger
        if spread > 10.0:
            bs_filter = "⚠️ THIN LIQUIDITY (Spread > $10)"
            bs_severity = 2
        elif spread > 5.0:
            bs_filter = "⚠️ WIDE SPREAD ($" + f"{spread:.1f}" + ") — Slippage risk"
            bs_severity = 1
        elif taker_ratio < 0.75:
            bs_filter = "⚠️ HEAVY SELLS — Bearish pressure"
            bs_severity = 1
        elif taker_ratio > 1.35:
            bs_filter = "⚡ HEAVY BUYS — Bullish pressure"
            bs_severity = 0

        # Load full alert history for stats (limit=50 only captures ~36 of 79 resolved trades)
        _all_alerts_for_stats = _load_alerts(limit=1000)
        stats = _portfolio_stats(portfolio, current_price=mid, alerts=_all_alerts_for_stats)

        # ── Phase 25: Drawdown Circuit Breaker ──
        dd_pct = stats.get("drawdown_pct", 0.0)
        streak = stats.get("streak", 0)
        circuit_breaker = {
            "active": dd_pct > 8.0 or streak <= -4,
            "reason": "",
            "dd_pct": dd_pct,
            "streak": streak,
        }
        if dd_pct > 8.0:
            circuit_breaker["reason"] = f"Drawdown {dd_pct:.1f}% exceeds 8% threshold"
        elif streak <= -4:
            circuit_breaker["reason"] = f"Losing streak of {abs(streak)} — stop and reassess"

        # WS-friendly lightweight alerts
        light_alerts = _light_alerts(alerts[-15:])

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "orderbook": {
                "mid": round(mid, 2),
                "spread": round(spread, 2),
                "bid": round(mid - spread/2, 2) if mid else 0,
                "ask": round(mid + spread/2, 2) if mid else 0
            },
            "portfolio": portfolio,
            "alerts": light_alerts,
            "stats": stats,
            "overrides": overrides,
            "auto_pilot": {
                "active": len(auto_muted_recipes) > 0,
                "regime": vol_regime,
                "auto_muted": list(auto_muted_recipes.keys()),
            },
            "bs_filter": bs_filter,
            "bs_severity": bs_severity,
            "flows": flows,
            "derivatives": derivatives,
            "cached_context": _LAST_CONTEXT,
            "data_age_seconds": round(data_age_seconds, 0),
            "circuit_breaker": circuit_breaker,
            "profit_preflight": _compute_profit_preflight(
                alerts=alerts,
                stats=stats,
                circuit_breaker=circuit_breaker,
                data_age_seconds=data_age_seconds,
                overrides=overrides,
                spread=spread,
                flows=flows,
                derivatives=derivatives,
            ),
            "logs": f"Heartbeat {datetime.now().strftime('%H:%M:%S')}",
        }
    except Exception as e:
        print(f"Data error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def _watcher_loop():
    global _LAST_REBUILD
    """Background thread: polls file mtimes every 1s, rebuilds cache only on change."""
    global _CACHED_DATA, _LAST_ALERT_MTIME, _LAST_PORTFOLIO_MTIME
    while True:
        try:
            changed = False
            if ALERTS_PATH.exists():
                mt = ALERTS_PATH.stat().st_mtime
                if mt != _LAST_ALERT_MTIME:
                    _LAST_ALERT_MTIME = mt
                    changed = True
            if PORTFOLIO_PATH.exists():
                mt = PORTFOLIO_PATH.stat().st_mtime
                if mt != _LAST_PORTFOLIO_MTIME:
                    _LAST_PORTFOLIO_MTIME = mt
                    changed = True
            
            # Also check overrides
            if OVERRIDES_PATH.exists():
                mt = OVERRIDES_PATH.stat().st_mtime
                # Not using mt for overrides currently, just checking every loop or on other changes
                # But let's just refresh if anything changed
            
            now = time.time()
            if changed or not _CACHED_DATA or (now - _LAST_REBUILD > 10):

                new_data = get_dashboard_data()
                with _STATE_LOCK:
                    _CACHED_DATA = new_data
                _LAST_REBUILD = now
        except Exception as e:
            print(f"Watcher error: {e}")
        time.sleep(1)


def _build_ws_frame(payload: str) -> bytes:
    data = payload.encode("utf-8")
    length = len(data)
    if length <= 125:
        header = struct.pack("!BB", 0x81, length)
    elif length <= 65535:
        header = struct.pack("!BBH", 0x81, 126, length)
    else:
        header = struct.pack("!BBQ", 0x81, 127, length)
    return header + data


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/ws":
            self._handle_websocket()
        elif self.path.startswith("/api/alert/"):
            self._serve_alert_detail()
        elif self.path == "/api/dashboard":
            with _STATE_LOCK:
                self._json_response(_CACHED_DATA)
            return
        elif self.path == "/api/alerts":
            self._serve_alerts_full()
        elif self.path == "/api/command":
            # Just show current overrides on GET /api/command
            self._json_response(_load_overrides())
        else:
            self._serve_dashboard()

    def do_POST(self):
        if self.path == "/api/command":
            self._handle_command()
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        """Handle CORS preflight for POST requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_alert_detail(self):
        """GET /api/alert/<index> — returns full un-stripped alert JSON."""
        try:
            parts = self.path.split("/")
            idx = int(parts[-1])
            alerts = _load_alerts(limit=50)
            if 0 <= idx < len(alerts):
                self._json_response(alerts[idx])
            else:
                self.send_error(404, "Alert index out of range")
        except Exception as e:
            self._json_response({"error": str(e)}, status=400)

    def _serve_alerts_full(self):
        """GET /api/alerts — returns all alerts without context stripping."""
        alerts = _load_alerts(limit=50)
        self._json_response(alerts)

    def _handle_command(self):
        """POST /api/command — handles dashboard interaction."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            cmd = json.loads(body)
            
            action = cmd.get("action")
            global _OVERRIDES
            _load_overrides() # Refresh
            
            if action == "mute_recipe":
                recipe = cmd.get("recipe")
                minutes = cmd.get("minutes", 60)
                expiry = time.time() + (minutes * 60)
                if "muted_recipes" not in _OVERRIDES:
                    _OVERRIDES["muted_recipes"] = {}
                _OVERRIDES["muted_recipes"][recipe] = expiry
                _save_overrides()
                self._json_response({"status": "success", "muted": recipe, "until": expiry})
            
            elif action == "set_min_score":
                val = int(cmd.get("value", 0))
                _OVERRIDES["min_score"] = val
                _save_overrides()
                self._json_response({"status": "success", "min_score": val})
            
            elif action == "set_direction_filter":
                direction = cmd.get("direction", "BOTH")
                if direction == "BOTH":
                    _OVERRIDES.pop("direction_filter", None)
                else:
                    _OVERRIDES["direction_filter"] = direction
                _save_overrides()
                self._json_response({"status": "success", "direction": direction})
            
            elif action == "reset_overrides":
                _OVERRIDES = {}
                _save_overrides()
                self._json_response({"status": "success", "message": "All overrides cleared"})

            elif action == "run_profit_preflight":
                with _STATE_LOCK:
                    payload = _CACHED_DATA.copy() if isinstance(_CACHED_DATA, dict) else {}
                preflight = payload.get("profit_preflight")
                if not preflight:
                    payload = get_dashboard_data()
                    preflight = payload.get("profit_preflight", {})
                self._json_response({"status": "success", "profit_preflight": preflight})
            
            else:
                self.send_error(400, f"Unknown action: {action}")
                
        except Exception as e:
            self._json_response({"error": str(e)}, status=400)

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _serve_dashboard(self):
        path = DASHBOARD_PATH if (self.path=="/" or self.path=="/dashboard.html") else None
        if not path or not path.exists():
            self.send_error(404)
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(content)

    def _handle_websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400)
            return
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")).digest()).decode("utf-8")
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        
        print(f"[*] WS connected: {self.client_address}")
        try:
            while True:
                with _STATE_LOCK:
                    payload = json.dumps(_CACHED_DATA) if _CACHED_DATA else "{}"
                self.wfile.write(_build_ws_frame(payload))
                self.wfile.flush()
                time.sleep(2)
        except:
            print(f"[*] WS disconnected: {self.client_address}")

    def log_message(self, fmt, *args):
        return


def main():
    # Seed initial data
    global _CACHED_DATA
    with _STATE_LOCK:
        _CACHED_DATA.update(get_dashboard_data())
    
    # Start watcher thread
    watcher = threading.Thread(target=_watcher_loop, daemon=True)
    watcher.start()
    
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard Server Alpha: http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
