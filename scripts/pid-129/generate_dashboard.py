#!/usr/bin/env python3
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if not (BASE_DIR / "logs").exists():
    BASE_DIR = Path.cwd()
STATE_PATH = BASE_DIR / ".mvp_alert_state.json"
PORTFOLIO_PATH = BASE_DIR / "data" / "paper_portfolio.json"
SCORECARD_PATH = BASE_DIR / "reports" / "pid-129-daily-scorecard.md"
ALERTS_PATH = BASE_DIR / "logs" / "pid-129-alerts.jsonl"
OUTPUT_PATH = BASE_DIR / "dashboard.html"
MAX_DURATION_SECONDS = {"5m": 4 * 3600, "15m": 12 * 3600, "1h": 48 * 3600}
TARGET_TFS = ["5m", "15m", "1h"]
def _safe_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default
def get_state():
    return _safe_json(STATE_PATH, {})
def get_portfolio():
    return _safe_json(PORTFOLIO_PATH, None)
def get_scorecard():
    if not SCORECARD_PATH.exists():
        return "No scorecard found yet."
    return SCORECARD_PATH.read_text(encoding="utf-8")
def get_alerts():
    if not ALERTS_PATH.exists():
        return []
    rows = []
    for line in ALERTS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows
def parse_dt(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
def tf_sort_key(tf: str):
    order = {"5m": 1, "15m": 2, "1h": 3}
    return order.get(tf, 999)
def latest_btc_by_timeframe(alerts):
    latest = {}
    for a in alerts:
        if a.get("symbol") != "BTC":
            continue
        tf = a.get("timeframe")
        if tf not in TARGET_TFS:
            continue
        ts = parse_dt(a.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)
        cur = latest.get(tf)
        cur_ts = parse_dt(cur.get("timestamp")) if cur else None
        if cur is None or (cur_ts is not None and ts >= cur_ts) or (cur_ts is None):
            latest[tf] = a
    return latest
def get_confidence(alert):
    return int(alert.get("confidence_score") or alert.get("confidence") or 0)
def get_direction(alert):
    return str(alert.get("direction") or "NEUTRAL").upper()
def get_tier(alert):
    return str(alert.get("tier") or "NO-TRADE")
def get_blockers(alert):
    blockers = alert.get("blockers")
    return blockers if isinstance(blockers, list) else []
def get_context(alert):
    ctx = alert.get("context")
    if isinstance(ctx, dict) and ctx.get("regime"):
        return ctx
    # Pre-Phase 13 alerts: try to reconstruct from other fields
    regime = "-"
    session = "-"
    # Regime can come from decision_trace.codes
    dt_codes = set((alert.get("decision_trace") or {}).get("codes", []))
    for code in dt_codes:
        if code.startswith("REGIME_"):
            regime = code.replace("REGIME_", "").lower()
            break
    # Session from codes
    for code in dt_codes:
        if code.startswith("SESSION_"):
            session = code.replace("SESSION_", "").replace("BOOST", "").replace("PENALTY", "").strip("_").lower() or "-"
            break
    return {"regime": regime, "session": session}
def badge_class_for_tier(tier: str):
    if tier == "A+":
        return "badge-good"
    if tier == "B":
        return "badge-warn"
    return "badge-neutral"
def badge_class_for_direction(direction: str):
    if direction == "LONG":
        return "badge-good"
    if direction == "SHORT":
        return "badge-bad"
    return "badge-neutral"
def execution_decision(latest):
    one_h = latest.get("1h", {})
    fifteen = latest.get("15m", {})
    five = latest.get("5m", {})
    reasons = []
    if not one_h or not fifteen or not five:
        return "WAIT", "warn", ["Missing one or more BTC timeframes (5m/15m/1h)."], 0.0

    d1, d15, d5 = get_direction(one_h), get_direction(fifteen), get_direction(five)
    a5 = str(five.get("action") or "SKIP").upper()
    tier5 = get_tier(five)
    c5 = get_confidence(five)
    b5 = get_blockers(five)

    # -- Phase 19 CRITICAL-2: Graduated alignment scoring --
    dirs = {"1h": d1, "15m": d15, "5m": d5}
    non_neutral = {tf: d for tf, d in dirs.items() if d != "NEUTRAL"}
    aligned_count = 0
    if non_neutral:
        majority_dir = max(set(non_neutral.values()), key=list(non_neutral.values()).count)
        aligned_count = sum(1 for d in non_neutral.values() if d == majority_dir)
        # Show which TFs agree and which don't
        aligned_tfs = [tf for tf, d in dirs.items() if d == majority_dir]
        misaligned_tfs = [tf for tf, d in dirs.items() if d != majority_dir]
        if misaligned_tfs:
            reasons.append(f"{aligned_count}/3 aligned ({', '.join(aligned_tfs)} = {majority_dir}). Waiting on {', '.join(misaligned_tfs)} to flip.")
    else:
        reasons.append("All timeframes NEUTRAL — no directional bias.")

    if d1 == "NEUTRAL" or d15 == "NEUTRAL" or d5 == "NEUTRAL":
        neutral_tfs = [tf for tf, d in dirs.items() if d == "NEUTRAL"]
        reasons.append(f"Neutral on: {', '.join(neutral_tfs)}.")

    if any(b in {"HTF_CONFLICT_15M", "HTF_CONFLICT_1H"} for b in b5):
        reasons.append("5m has HTF conflict blocker.")
    if not (a5 == "TRADE" or (a5 == "WATCH" and c5 >= 70)):
        reasons.append(f"5m trigger is {a5} (confidence {c5}).")

    # EXECUTE only if all 3 non-neutral directions match
    all_aligned = len(non_neutral) == 3 and aligned_count == 3
    decision = "EXECUTE" if all_aligned and not any("conflict" in r.lower() for r in reasons) else "WAIT"
    tone = "good" if decision == "EXECUTE" else "warn"

    risk_pct = 0.0
    if decision == "EXECUTE":
        if tier5 == "A+": risk_pct = 2.0
        elif tier5 == "B": risk_pct = 0.5

    if not reasons:
        reasons = ["All timeframes aligned."]

    return decision, tone, reasons, risk_pct


def percentile_used(age_seconds, tf):
    max_s = MAX_DURATION_SECONDS.get(tf, 24 * 3600)
    return (age_seconds / max_s) * 100 if max_s > 0 else 0
def render_execution_matrix(alerts):
    latest = latest_btc_by_timeframe(alerts)
    decision, tone, reasons, risk_pct = execution_decision(latest)
    risk_html = f"<span class='pill badge-good' style='margin-left:12px;'>Suggested Risk: {risk_pct}%</span>" if risk_pct > 0 else ""
    cols = []
    for tf in TARGET_TFS:
        a = latest.get(tf)
        if not a:
            cols.append("""
            <td>
                <div class="cell-main">No data</div>
                <div class="mini">Awaiting alert log for timeframe.</div>
            </td>
            """)
            continue
        ctx = get_context(a)
        regime = ctx.get("regime", "-")
        session = ctx.get("session", "-")
        direction = get_direction(a)
        tier = get_tier(a)
        conf = get_confidence(a)
        # Phase 19 FIX 10: override tier if confidence doesn't match thresholds
        # Prevents stale alerts from showing A+ on low scores
        if tier == "A+" and conf < 45:
            tier = "B" if conf >= 25 else "NO-TRADE"
        elif tier == "B" and conf < 20:
            tier = "NO-TRADE"
        blockers = ", ".join(get_blockers(a)[:2]) or "None"
        entry = float(a.get("entry_price") or a.get("entry") or 0)
        stop = float(a.get("invalidation") or 0)
        tp1_val = float(a.get("tp1") or 0)
        rr = float(a.get("rr_ratio") or 0)
        
        qty_str = ""
        if risk_pct > 0 and entry > 0 and stop > 0 and abs(entry - stop) > 0.1:
            portfolio = get_portfolio()
            balance = portfolio.get("balance", 10000) if portfolio else 10000
            risk_amt = balance * (risk_pct / 100.0)
            qty = risk_amt / abs(entry - stop)
            qty_str = f" ({qty:.3f} BTC)"
            
        entry_str = f"${entry:,.0f}" if entry else "--"
        stop_str = f"${stop:,.0f}" if stop else "--"
        tp1_str = f"${tp1_val:,.0f}" if tp1_val else "--"
        rr_str = f"{rr:.2f}" if rr else "--"
        
        risk_label = f"<div class='mini' style='color:var(--accent);font-weight:700;'>Suggested Risk: {risk_pct}%{qty_str}</div>" if (risk_pct > 0 and tf == "5m") else ""
        
        cols.append(f"""
        <td>
            <div class="pill-wrap">
                <span class="pill {badge_class_for_direction(direction)}">{direction}</span>
                <span class="pill {badge_class_for_tier(tier)}">{tier}</span>
                <span class="pill badge-neutral">{conf}/100</span>
            </div>
            {risk_label}
            <div class="mini">Regime: {regime} · Session: {session}</div>
            <div class="mini">Entry: {entry_str} · Stop: {stop_str} · TP1: {tp1_str} · R:R {rr_str}</div>
            <div class="mini">Blockers: {blockers}</div>
        </td>
        """)
    tone_class = "badge-good" if tone == "good" else "badge-warn"
    reason_text = " ".join(f"• {r}" for r in reasons)
    return f"""
    <section class="panel">
        <h2>Execution Matrix (BTC)</h2>
        <table class="matrix-table">
            <thead>
                <tr><th>Lane</th><th>5m Trigger</th><th>15m Setup</th><th>1h Bias</th></tr>
            </thead>
            <tbody>
                <tr><td><strong>Alignment View</strong></td>{''.join(cols)}</tr>
                <tr>
                    <td><strong>Execution Decision</strong></td>
                    <td colspan="3">
                        <span class="pill {tone_class}">{decision}</span>
                        {risk_html}
                        <span class="mini" style="margin-left:8px;">{reason_text}</span>
                    </td>
                </tr>
            </tbody>
        </table>
        <p class="playbook">Playbook: <strong>1h = bias</strong> · <strong>15m = setup</strong> · <strong>5m = trigger</strong>.</p>
    </section>
    """
def max_losing_streak(trades):
    streak, max_streak = 0, 0
    for t in trades:
        if str(t.get("outcome", "")).upper() in {"LOSS", "TIMEOUT"}:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak
def render_edge_scoreboard(portfolio):
    if not portfolio:
        return """
        <section class="panel">
            <h2>Timeframe Edge Scoreboard</h2>
            <p class="mini">No portfolio data available.</p>
        </section>
        """
    closed = portfolio.get("closed_trades", [])
    grouped = defaultdict(list)
    for t in closed:
        tf = t.get("timeframe")
        if tf in TARGET_TFS:
            grouped[tf].append(t)
    rows = []
    best_tf = None
    best_score = -10**9
    min_sample = 10
    for tf in TARGET_TFS:
        trades = grouped.get(tf, [])
        n = len(trades)
        if n == 0:
            rows.append(f"<tr><td>{tf}</td><td colspan='6' class='mini'>No closed trades yet.</td></tr>")
            continue
        wins = sum(1 for t in trades if str(t.get("outcome", "")).upper().startswith("WIN"))
        wr = (wins / n) * 100
        rs = [float(t.get("r_multiple", 0.0)) for t in trades]
        avg_r = sum(rs) / n
        med_r = median(rs)
        gross_r = sum(rs)
        lose_streak = max_losing_streak(trades)
        if n >= min_sample and avg_r > best_score:
            best_score = avg_r
            best_tf = tf
        tone = "badge-good" if n >= min_sample and avg_r > 0 else ("badge-bad" if avg_r < 0 else "badge-warn")
        rows.append(
            f"<tr><td>{tf}</td><td>{n}</td><td>{wr:.1f}%</td><td><span class='pill {tone}'>{avg_r:.2f}R</span></td>"
            f"<td>{med_r:.2f}R</td><td>{gross_r:.2f}R</td><td>{lose_streak}</td></tr>"
        )
    focus = best_tf if best_tf else "No qualified timeframe yet"
    focus_tone = "badge-good" if best_tf else "badge-warn"
    return f"""
    <section class="panel">
        <h2>Timeframe Edge Scoreboard</h2>
        <div style="margin-bottom: 0.8rem;"><span class="pill {focus_tone}">Recommended Focus: {focus}</span>
        <span class="mini" style="margin-left: 8px;">Criteria: min {min_sample} trades + highest avg R.</span></div>
        <table class="matrix-table">
            <thead>
                <tr><th>TF</th><th>Trades</th><th>Win Rate</th><th>Avg R</th><th>Median R</th><th>Gross R</th><th>Max Losing Streak</th></tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </section>
    """
def render_lifecycle_panel(alerts):
    now = datetime.now(timezone.utc)
    unresolved = []
    for a in alerts:
        if a.get("symbol") != "BTC":
            continue
        tf = a.get("timeframe")
        if tf not in TARGET_TFS:
            continue
        if a.get("resolved") is True:
            continue
        # Phase 19 CRITICAL-3: skip NEUTRAL trades older than their max window
        # These are phantom positions that should have auto-closed
        alert_dir = str(a.get("direction", "")).upper()
        if alert_dir == "NEUTRAL":
            ts = parse_dt(a.get("timestamp"))
            if ts:
                age_s = max(0, (now - ts.astimezone(timezone.utc)).total_seconds())
                max_age = MAX_DURATION_SECONDS.get(tf, 4 * 3600)
                if age_s > max_age * 0.5:  # expired past 50% of window = dead trade
                    continue  # skip this, don't show in lifecycle panel
        unresolved.append(a)
    if not unresolved:
        return """
        <section class="panel">
            <h2>Active Trade Lifecycle</h2>
            <p class="mini">No unresolved BTC alerts found.</p>
        </section>
        """
    rows = []
    sortable = []
    for a in unresolved:
        tf = a.get("timeframe")
        ts = parse_dt(a.get("timestamp"))
        if not ts:
            continue
        age_s = max(0, (now - ts.astimezone(timezone.utc)).total_seconds())
        used = percentile_used(age_s, tf)
        rr = a.get("rr_ratio")
        if rr is None:
            entry = float(a.get("entry_price") or 0.0)
            inv = float(a.get("invalidation") or 0.0)
            tp1 = float(a.get("tp1") or 0.0)
            denom = abs(entry - inv)
            rr = (abs(tp1 - entry) / denom) if denom > 0 else 0.0
        blockers = get_blockers(a)
        has_htf_conflict = any(b in {"HTF_CONFLICT_15M", "HTF_CONFLICT_1H"} for b in blockers)
        flags = []
        urgency = 0
        if used >= 80:
            flags.append("Late setup")
            urgency += 3
        elif used >= 60:
            flags.append("Aging setup")
            urgency += 2
        else:
            flags.append("Fresh setup")
            urgency += 1
        if has_htf_conflict:
            flags.append("Conflict risk")
            urgency += 3
        if rr < 1.2:
            flags.append("Low R:R")
            urgency += 2
        tone = "badge-bad" if urgency >= 5 else ("badge-warn" if urgency >= 3 else "badge-good")
        age_str = f"{age_s/60:.0f}m" if age_s < 3600 else f"{age_s/3600:.1f}h"
        row_html = (
            f"<tr><td>{tf}</td><td>{a.get('direction', '-')}</td><td>{age_str}</td><td>{used:.0f}%</td>"
            f"<td>{float(rr):.2f}</td><td>{', '.join(blockers[:2]) or 'None'}</td>"
            f"<td><span class='pill {tone}'>{' · '.join(flags)}</span></td></tr>"
        )
        sortable.append((urgency, tf_sort_key(tf), row_html))
    sortable.sort(key=lambda x: (-x[0], x[1]))
    rows = [r[2] for r in sortable][:10]
    return f"""
    <section class="panel">
        <h2>Active Trade Lifecycle</h2>
        <table class="matrix-table">
            <thead>
                <tr><th>TF</th><th>Direction</th><th>Age</th><th>Time Used</th><th>Planned R:R</th><th>Blockers</th><th>Management Priority</th></tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </section>
    """
def generate_svg_equity(curve):
    if not curve or len(curve) < 2:
        return ""
    width, height = 800, 200
    points = [p["balance"] for p in curve]
    min_b, max_b = min(points), max(points)
    span = max_b - min_b if max_b > min_b else 1.0
    min_b -= span * 0.1
    max_b += span * 0.1
    span = max_b - min_b
    svg_points = []
    for i, p in enumerate(points):
        x = (i / (len(points) - 1)) * width
        y = height - ((p - min_b) / span) * height
        svg_points.append(f"{x},{y}")
    polyline = " ".join(svg_points)
    return f"""
    <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="width: 100%; height: 150px;">
        <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:var(--accent);stop-opacity:0.2" />
                <stop offset="100%" style="stop-color:var(--accent);stop-opacity:0" />
            </linearGradient>
        </defs>
        <polyline points="{polyline}" fill="none" stroke="var(--accent)" stroke-width="3" />
        <path d="M0,{height} {' '.join(['L' + p for p in svg_points])} L{width},{height} Z" fill="url(#grad)" />
    </svg>
    """


def _latest_btc_alert(alerts):
    for a in reversed(alerts):
        if a.get("symbol") == "BTC":
            return a
    return {}


def build_verdict_context(alerts, portfolio):
    alert = _latest_btc_alert(alerts)
    direction = str(alert.get("direction") or "NEUTRAL").upper()
    entry = float(alert.get("entry_price") or alert.get("entry") or 0)
    tp1 = float(alert.get("tp1") or 0)
    stop = float(alert.get("invalidation") or 0)
    confidence = int(alert.get("confidence_score") or alert.get("confidence") or 0)
    active_codes = set(((alert.get("decision_trace") or {}).get("codes") or []))
    checks = [
        ("TF Alignment", "HTF_COUNTER" not in active_codes),
        ("ML Conviction", confidence >= 40),
        ("R:R >= 1.2", abs(tp1 - entry) / max(abs(entry - stop), 1e-9) >= 1.2 if entry and tp1 and stop else False),
        ("Max DD <= 12%", float((portfolio or {}).get("max_drawdown", 0)) <= 0.12),
        ("No HTF conflict", not any(c in active_codes for c in ["HTF_CONFLICT_15M", "HTF_CONFLICT_1H"])),
    ]
    passed = sum(1 for _, ok in checks if ok)
    gate = "GREEN" if passed >= 4 else ("AMBER" if passed >= 3 else "RED")
    probes = [
        ("Squeeze", ["SQUEEZE_FIRE", "SQUEEZE_ON"], []), ("Trend (HTF)", ["HTF_ALIGNED"], ["HTF_COUNTER"]),
        ("Momentum", ["SENTIMENT_BULL", "FLOW_TAKER_BULLISH", "VOLUME_IMPULSE_BULL"], ["SENTIMENT_BEAR", "FLOW_TAKER_BEARISH", "VOLUME_IMPULSE_BEAR"]), ("ML Model", ["ML_CONFIDENCE_BOOST"], ["ML_SKEPTICISM"]),
        ("Funding", ["FUNDING_EXTREME_LOW", "FUNDING_LOW"], ["FUNDING_EXTREME_HIGH", "FUNDING_HIGH"]),
        ("DXY Macro", ["DXY_FALLING_BULLISH"], ["DXY_RISING_BEARISH"]), ("Gold Macro", ["GOLD_RISING_BULLISH"], ["GOLD_FALLING_BEARISH"]),
        ("Fear & Greed", ["FG_EXTREME_FEAR", "FG_FEAR"], ["FG_EXTREME_GREED", "FG_GREED"]),
        ("Order Book", ["BID_WALL_SUPPORT"], ["ASK_WALL_RESISTANCE"]), ("OI / Basis", ["OI_SURGE_MAJOR", "OI_SURGE_MINOR", "BASIS_BULLISH", "OI_NEW_LONGS"], ["BASIS_BEARISH", "OI_NEW_SHORTS"]),
        ("Structure", ["STRUCTURE_BOS_BULL", "STRUCTURE_CHOCH_BULL"], ["STRUCTURE_BOS_BEAR", "STRUCTURE_CHOCH_BEAR"]),
        ("Levels", ["PDL_SWEEP_BULL", "EQL_SWEEP_BULL", "SESSION_LOW_SWEEP", "PDH_RECLAIM_BULL"], ["PDH_SWEEP_BEAR", "EQH_SWEEP_BEAR", "SESSION_HIGH_SWEEP", "PDL_BREAK_BEAR"]),
        ("AVWAP", ["AVWAP_RECLAIM_BULL"], ["AVWAP_REJECT_BEAR"]),
        ("VP Status", ["ABOVE_VALUE"], ["BELOW_VALUE"]),
        ("Auto R:R", ["AUTO_RR_EXCELLENT"], ["AUTO_RR_POOR"]),
    ]
    rows = []
    # Build diagnostic info from decision_trace context
    dt_context = (alert.get("decision_trace") or {}).get("context", {})
    for label, bulls, bears in probes:
        has_bull, has_bear = any(c in active_codes for c in bulls), any(c in active_codes for c in bears)
        aligned = (direction == "LONG" and has_bull) or (direction == "SHORT" and has_bear)
        against = (direction == "LONG" and has_bear) or (direction == "SHORT" and has_bull)
        icon = "🟢" if aligned else "🔴" if against else "⚫"
        color = "var(--accent)" if aligned else "#ff4d4d" if against else "var(--text-muted)"
        
        # Generate diagnostic tooltip showing WHY the probe is in its current state
        diag = ""
        if icon == "⚫":
            # Show what codes WOULD activate this probe
            all_codes = bulls + bears
            diag = f"Needs: {' or '.join(all_codes[:3])}"
        elif icon == "🟢":
            matched = [c for c in (bulls + bears) if c in active_codes]
            diag = f"Active: {', '.join(matched[:2])}"
        elif icon == "🔴":
            matched = [c for c in (bulls + bears) if c in active_codes]
            diag = f"Against: {', '.join(matched[:2])}"
        
        # Add context-specific diagnostics for key probes
        if label == "Squeeze" and icon == "⚫":
            sq = dt_context.get("squeeze", {})
            if isinstance(sq, dict):
                diag = f"Squeeze={sq.get('state', 'off')}"
            elif isinstance(sq, str):
                diag = f"Squeeze={sq}"
            else:
                diag = "No squeeze data"
        elif label == "VP Status" and icon == "⚫":
            vp = dt_context.get("volume_profile", {})
            if isinstance(vp, dict) and vp.get("poc"):
                diag = f"POC=${vp['poc']:,.0f}, price near value area"
            else:
                diag = "No VP data in trace"
        elif label == "Structure" and icon == "⚫":
            st = dt_context.get("structure", {})
            if isinstance(st, dict):
                diag = f"Trend={st.get('trend', 'neutral')}, no BOS/CHoCH"
            else:
                diag = "No structure data"
        elif label == "Levels" and icon == "⚫":
            sl = dt_context.get("session_levels", {})
            if isinstance(sl, dict) and sl.get("pdh"):
                diag = f"PDH=${sl.get('pdh',0):,.0f} PDL=${sl.get('pdl',0):,.0f} — not near"
            else:
                diag = "No level data"
        elif label == "AVWAP" and icon == "⚫":
            av = dt_context.get("avwap", {})
            if isinstance(av, dict) and av.get("avwap"):
                diag = f"AVWAP=${av['avwap']:,.0f}, pos={av.get('price_vs_avwap','?')}"
            else:
                diag = "No AVWAP data"
        elif label == "Auto R:R" and icon == "⚫":
            rr = dt_context.get("auto_rr", {})
            if isinstance(rr, dict) and rr.get("rr"):
                diag = f"R:R={rr['rr']:.2f} (needs EXCELLENT=2.0+ or POOR<1.2)"
            else:
                diag = "No auto R:R computed"
        
        rows.append((label, icon, color, diag))
    aligned_count = sum(1 for _, icon, _, _ in rows if icon == "🟢")
    against_count = sum(1 for _, icon, _, _ in rows if icon == "🔴")
    # Phase 20 FIX 4: Calculate system accuracy from resolved trades
    resolved_btc = [a for a in alerts if a.get("symbol") == "BTC" and a.get("resolved")]
    recent_resolved = resolved_btc[-20:]
    if recent_resolved:
        wins = sum(1 for a in recent_resolved if str(a.get("outcome", "")).upper().startswith("WIN"))
        total_resolved = len(recent_resolved)
        accuracy_pct = (wins / total_resolved) * 100 if total_resolved > 0 else 0.0
        win_streak = 0
        for a in reversed(recent_resolved):
            if str(a.get("outcome", "")).upper().startswith("WIN"):
                win_streak += 1
            else:
                break
    else:
        wins, total_resolved, accuracy_pct, win_streak = 0, 0, 0.0, 0
    return {"direction": direction, "entry": entry, "tp1": tp1, "stop": stop, "checks": checks, "gate": gate, "rows": rows, "aligned": aligned_count, "against": against_count, "total": len(rows), "accuracy_pct": accuracy_pct, "accuracy_wins": wins, "accuracy_total": total_resolved, "win_streak": win_streak}
def render_recent_alerts(alerts):
    """Show the last 10 BTC alerts with direction, confidence, and age."""
    now = datetime.now(timezone.utc)
    btc_alerts = [a for a in alerts if a.get("symbol") == "BTC"][-10:]
    if not btc_alerts:
        return """
        <section class="panel">
            <h2>📡 Recent Signals</h2>
            <p class="mini" style="padding:16px;">No BTC alerts logged yet. Waiting for first engine cycle to complete.</p>
        </section>
        """
    rows_html = []
    for a in reversed(btc_alerts):
        tf = a.get("timeframe", "-")
        direction = str(a.get("direction", "NEUTRAL")).upper()
        conf = int(a.get("confidence_score") or a.get("confidence") or 0)
        tier = str(a.get("tier", "-"))
        ts = parse_dt(a.get("timestamp"))
        age_str = "-"
        if ts:
            age_s = max(0, (now - ts.astimezone(timezone.utc)).total_seconds())
            if age_s < 60:
                age_str = f"{age_s:.0f}s"
            elif age_s < 3600:
                age_str = f"{age_s/60:.0f}m"
            else:
                age_str = f"{age_s/3600:.1f}h"
        outcome = a.get("outcome") or ("RESOLVED" if a.get("resolved") else "OPEN")
        
        dir_cls = "badge-good" if direction == "LONG" else ("badge-bad" if direction == "SHORT" else "badge-neutral")
        tier_cls = "badge-good" if tier == "A+" else ("badge-warn" if tier == "B" else "badge-neutral")
        
        # Color outcome
        if "WIN" in str(outcome).upper():
            out_cls = "badge-good"
        elif "LOSS" in str(outcome).upper():
            out_cls = "badge-bad"
        elif outcome == "OPEN":
            out_cls = "badge-warn"
        else:
            out_cls = "badge-neutral"
        
        # Count active codes
        dt_codes = (a.get("decision_trace") or {}).get("codes", [])
        code_count = len([c for c in dt_codes if not c.startswith("REGIME_") and not c.startswith("SESSION_")])
        
        rows_html.append(f"""
        <tr>
            <td>{tf}</td>
            <td><span class="pill {dir_cls}">{direction}</span></td>
            <td>{conf}</td>
            <td><span class="pill {tier_cls}">{tier}</span></td>
            <td>{code_count}</td>
            <td>{age_str}</td>
            <td><span class="pill {out_cls}">{outcome}</span></td>
        </tr>""")
    return f"""
    <section class="panel">
        <h2>📡 Recent Signals (Last 10)</h2>
        <table class="matrix-table">
            <thead>
                <tr><th>TF</th><th>Dir</th><th>Conf</th><th>Tier</th><th>Codes</th><th>Age</th><th>Status</th></tr>
            </thead>
            <tbody>{''.join(rows_html)}</tbody>
        </table>
    </section>
    """

def generate_html():
    state = get_state()
    portfolio = get_portfolio()
    scorecard = get_scorecard()
    alerts = get_alerts()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alerts_html = ""
    for symbol, tfs in state.items():
        if symbol in ["lifecycle_key", "regime", "last_sent", "tp1_hit"]:
            continue
        for tf, data in sorted(tfs.items(), key=lambda x: tf_sort_key(x[0])):
            tier = data.get("tier", "N/A")
            color = "var(--accent)" if "A+" in tier else ("var(--secondary)" if "B" in tier else "var(--text-muted)")
            alerts_html += f"""
            <div class="card">
                <div class="card-header">
                    <span class="symbol">{symbol}</span>
                    <span class="timeframe">{tf}</span>
                </div>
                <div class="tier" style="color: {color}">{tier}</div>
                <div class="meta">
                    <p>Last Signal: {datetime.fromtimestamp(data.get('last_candle_ts', 0)).strftime('%H:%M')}</p>
                    <p>TP1 Hit: {'✅' if data.get('tp1_hit') else '❌'}</p>
                </div>
            </div>
            """
    p_html = "<p>No portfolio data available.</p>"
    if portfolio:
        balance = portfolio.get("balance", 10000)
        pnl = balance - 10000
        pnl_pct = (pnl / 10000) * 100
        pnl_color = "var(--accent)" if pnl >= 0 else "#ff4d4d"
        equity_svg = generate_svg_equity(portfolio.get("equity_curve", []))
        p_html = f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Virtual Balance</div>
                <div class="stat-value" style="color: {pnl_color}">${balance:,.2f}</div>
                <div class="stat-sub">{pnl_pct:+.2f}% from start</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Max Drawdown</div>
                <div class="stat-value">{portfolio.get('max_drawdown', 0)*100:.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Open / Closed</div>
                <div class="stat-value">{len(portfolio.get('positions', []))} / {len(portfolio.get('closed_trades', []))}</div>
            </div>
        </div>
        <div class="chart-container">{equity_svg}</div>
        """
    vctx = build_verdict_context(alerts, portfolio)
    latest_codes = ((_latest_btc_alert(alerts).get("decision_trace") or {}).get("codes") or [])[:8]
    signals_html = "".join(f"<span class='pill badge-neutral'>{c}</span>" for c in latest_codes) or "<span class='mini'>No active reason codes.</span>"
    gate_color = "var(--accent)" if vctx["gate"] == "GREEN" else ("#ffd700" if vctx["gate"] == "AMBER" else "#ff4d4d")
    gate_bg = "rgba(0,255,204,0.05)" if vctx["gate"] == "GREEN" else ("rgba(255,215,0,0.08)" if vctx["gate"] == "AMBER" else "rgba(255,77,77,0.08)")
    gate_rows = "".join(
        f"<div class='mini' style='color:{'var(--text)' if ok else '#ff4d4d'}'>{'✅' if ok else '❌'} {label}</div>"
        for label, ok in vctx["checks"]
    )
    a_count = vctx["aligned"]
    ag_count = vctx.get("against", 0)
    t_probes = vctx["total"]
    net_score = a_count - ag_count
    radar_color = "var(--accent)" if a_count >= 7 else ("#ffd700" if a_count >= 4 else "#ff4d4d")
    radar_label = "STRONG" if a_count >= 7 else ("MODERATE" if a_count >= 4 else "WEAK")
    net_color = "var(--accent)" if net_score >= 0 else "#ff4d4d"
    inactive_count = t_probes - a_count - ag_count
    radar_rows = "".join(
        f"<div class='mini' title='{diag}'>{icon} <span style='color:{color}'>{label}</span> <span class='mini' style='opacity:0.5; font-size:0.7em;'>({diag})</span></div>"
        for label, icon, color, diag in vctx["rows"]
    )
    execute_html = ""
    if vctx["direction"] in {"LONG", "SHORT"}:
        label = "⚠️ EXECUTE (HIGH RISK)" if vctx["gate"] == "RED" else "1-CLICK EXECUTE"
        bg = "background:#ff4d4d;" if vctx["gate"] == "RED" else ""
        execute_html = f"<button id='executeBtn' class='pill' style='padding:10px 14px;font-size:.9rem;{bg}' onclick=\"requestExecute('latest-btc')\">{label}</button>"
    verdict_html = f"""
    <section class='panel'>
      <h2>Verdict Center</h2>
      <div class='mini' style='margin-bottom:8px;'>Direction: <span class='pill {badge_class_for_direction(vctx['direction'])}'>{vctx['direction']}</span></div>
      <div class='mini' style='margin-bottom:8px;'>Edge (last {vctx.get('accuracy_total', 0)}): <span class='pill {"badge-good" if vctx.get("accuracy_pct", 0) >= 55 else "badge-warn" if vctx.get("accuracy_pct", 0) >= 40 else "badge-bad"}'>{vctx.get("accuracy_pct", 0):.0f}% ({vctx.get("accuracy_wins", 0)}W)</span>{" 🔥" + str(vctx.get("win_streak", 0)) if vctx.get("win_streak", 0) >= 3 else ""}</div>
      <div style='background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:12px;padding:1rem;margin-bottom:1rem;'>
        <div style='display:flex;justify-content:space-between;align-items:center;'><div><div class='mini'>Live BTC Price</div><div id='livePrice' style='font-size:1.6rem;font-weight:800;'>Loading...</div></div><div style='text-align:right;'><div class='mini'>Unrealized PnL</div><div id='livePnL'>—</div></div></div>
        <div style='display:flex;gap:1rem;margin-top:.6rem;'><div class='mini'>→ TP1 <span id='distTP1'>—</span></div><div class='mini'>→ STOP <span id='distStop'>—</span></div><div class='mini'>SPREAD <span id='liveSpread'>—</span></div></div>
      </div>
      <div style='margin-bottom:1rem;'><div class='mini' style='margin-bottom:6px;'>Conviction Signals</div>{signals_html}</div>
      <div id='keyLevelsCard' style='background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:12px;padding:1rem;margin-bottom:1rem;'>
        <div class='mini' style='margin-bottom:6px;'>Key Levels</div>
        <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px 12px;font-family:JetBrains Mono,monospace;font-size:.78rem;'>
          <div>PDH: <span id='key-pdh' style='color:#ffd700;'>—</span></div>
          <div>PDL: <span id='key-pdl' style='color:#ffd700;'>—</span></div>
          <div>POC: <span id='key-poc' style='color:#00ffcc;'>—</span></div>
          <div>VAH: <span id='key-vah' style='color:#4488ff;'>—</span></div>
          <div>VAL: <span id='key-val' style='color:#4488ff;'>—</span></div>
          <div>AVWAP: <span id='key-avwap'>—</span> <span id='key-avwap-side' style='font-size:.68rem;'>—</span></div>
          <div>Structure: <span id='key-struct-event'>—</span></div>
          <div>Pivot H: <span id='key-pivot-high'>—</span></div>
          <div>Pivot L: <span id='key-pivot-low'>—</span></div>
          <div>Bid Walls: <span id='key-bid-walls' style='color:#00ff88;'>—</span></div>
          <div>Ask Walls: <span id='key-ask-walls' style='color:#ff4444;'>—</span></div>
          <div>Liquidity: <span id='key-liq-targets' style='color:#ffa500;'>—</span></div>
        </div>
      </div>
      <div id='radarCard' style='background:rgba(255,255,255,.03);border:1px solid {radar_color};border-radius:12px;padding:1rem;margin-bottom:1rem;'>
        <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:.3rem;'><span class='mini'>Confluence Radar</span><span id='radarScore' class='pill' style='border:1px solid {radar_color};color:{radar_color};'>{a_count}/{t_probes} {radar_label}</span></div>
        <div style='height:6px;background:rgba(255,255,255,.08);border-radius:4px;margin:.5rem 0 .8rem;overflow:hidden;'><div id='radarBar' style='height:100%;width:{int((a_count/t_probes)*100) if t_probes else 0}%;background:{radar_color};transition:width 0.4s ease;'></div></div>
        <div id='radarGrid' style='display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;'>{radar_rows}</div>
        <div style='margin-top:.5rem;border-top:1px solid rgba(255,255,255,.06);padding-top:.4rem;font-size:.7rem;font-family:JetBrains Mono,monospace;color:var(--text-muted);'>Net: <span id='radarNet' style='color:{net_color};font-weight:700;'>{net_score:+d}</span> &nbsp;🟢 {a_count} &nbsp;🔴 {ag_count} &nbsp;⚫ {inactive_count}</div>
      </div>
      <div style='background:{gate_bg};border:1px solid {gate_color};border-radius:12px;padding:1rem;margin-bottom:1rem;'><div style='display:flex;justify-content:space-between;'><span class='mini'>Trade Safety</span><span class='pill' style='border:1px solid {gate_color};color:{gate_color};'>{vctx['gate']}</span></div>{gate_rows}</div>
      {execute_html}
    </section>
    <div id='executeModal' style='display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:99;align-items:center;justify-content:center;'>
      <div style='background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1rem;max-width:360px;width:90%;'><h3 style='margin-bottom:.6rem;'>Confirm Execute</h3><div id='executeMeta' class='mini'></div><div style='margin-top:1rem;display:flex;gap:.5rem;justify-content:flex-end;'><button class='pill badge-neutral' onclick='closeExecuteModal()'>Cancel</button><button id='confirmExecuteBtn' class='pill badge-good' disabled>Confirm (3)</button></div></div>
    </div>
    """
    execution_html = render_execution_matrix(alerts)
    edge_html = render_edge_scoreboard(portfolio)
    lifecycle_html = render_lifecycle_panel(alerts)
    recent_alerts_html = render_recent_alerts(alerts)
    balance = (portfolio or {}).get("balance", 10000)
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="60">
    <title>BTC Alerts | Strategic Command</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg:#050507; --surface:#111116; --card-bg:#1a1a24; --accent:#00ffcc; --secondary:#7000ff; --text:#f1f1f1; --text-muted:#a1a1aa; --border:#2a2a36; }}
        @keyframes pulseGreen {{ 0% {{ background-color: rgba(0, 255, 204, 0.4); }} 100% {{ background-color: transparent; }} }}
        @keyframes pulseRed {{ 0% {{ background-color: rgba(255, 77, 77, 0.4); }} 100% {{ background-color: transparent; }} }}
        .pulse-up {{ animation: pulseGreen 0.8s ease-out; }}
        .pulse-down {{ animation: pulseRed 0.8s ease-out; }}
        .layout-grid {{ display: grid; grid-template-columns: 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }}
        @media (min-width: 1100px) {{ .layout-grid {{ grid-template-columns: 350px 1fr; }} }}
        @media (min-width: 1400px) {{ .layout-grid {{ grid-template-columns: 420px 1fr; }} }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ background-image: radial-gradient(circle at top right, rgba(0, 255, 204, 0.05), transparent 40%), radial-gradient(circle at bottom left, rgba(112, 0, 255, 0.05), transparent 40%); background-color: #050507; background-attachment: fixed; color: var(--text); font-family: 'Outfit', sans-serif; padding: 2rem; max-width: 1400px; margin: 0 auto; }}
        header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }}
        h1 {{ font-weight: 800; font-size: 2.5rem; letter-spacing: -1px; background: linear-gradient(135deg, var(--accent), var(--secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        h2 {{ margin-bottom: 1rem; font-weight: 800; font-size: 1.25rem; color: var(--accent); }}
        section {{ margin-bottom: 1.5rem; }}
        .panel, .card, .stat-card, .scorecard-section {{ background: rgba(30, 30, 40, 0.75); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.1); box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3); color: var(--text); }}
        .panel {{ border-radius: 18px; padding: 1.2rem; }}
        .status {{ text-align: right; }}
        .badge-live {{ background: rgba(0,255,204,0.1); color: var(--accent); padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; border: 1px solid rgba(0,255,204,0.4); }}
        .badge-stale {{ background: rgba(255,77,77,0.12); color: #ff4d4d; border-color: rgba(255,77,77,0.4); }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }}
        .card {{ border-radius: 20px; padding: 1.2rem; background: var(--card-bg); }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; margin-bottom: 1rem; }}
        .stat-card {{ padding: 1rem; border-radius: 16px; }}
        .stat-label {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem; }}
        .stat-value {{ font-size: 1.8rem; font-weight: 800; }}
        .stat-sub {{ font-size: 0.8rem; font-family: 'JetBrains Mono', monospace; }}
        .chart-container {{ background: var(--surface); padding: 1rem; border-radius: 20px; border: 1px solid var(--border); }}
        .matrix-table {{ width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 12px; }}
        .matrix-table th, .matrix-table td {{ border: 1px solid var(--border); padding: 0.65rem; vertical-align: top; }}
        .matrix-table th {{ color: var(--text-muted); text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.04em; text-align: left; }}
        .pill {{ display: inline-block; border-radius: 999px; padding: 3px 10px; font-size: 0.75rem; font-weight: 700; margin-right: 6px; margin-bottom: 4px; }}
        .badge-good {{ background: rgba(0,255,204,0.15); color: #00ffcc; border: 1px solid rgba(0,255,204,0.5); }}
        .badge-warn {{ background: rgba(255,215,0,0.12); color: #ffd700; border: 1px solid rgba(255,215,0,0.45); }}
        .badge-bad {{ background: rgba(255,77,77,0.12); color: #ff4d4d; border: 1px solid rgba(255,77,77,0.45); }}
        .badge-neutral {{ background: rgba(128,128,138,0.12); color: var(--text-muted); border: 1px solid rgba(128,128,138,0.35); }}
        .mini {{ color: var(--text-muted); font-size: 0.82rem; margin-top: 4px; font-family: 'JetBrains Mono', monospace; }}
        .playbook {{ margin-top: 0.8rem; color: var(--text-muted); font-size: 0.92rem; }}
        .scorecard-section {{ background: var(--surface); border-radius: 18px; padding: 1.2rem; border: 1px solid var(--border); }}
        pre {{ font-family: 'JetBrains Mono', monospace; white-space: pre-wrap; font-size: 0.85rem; color: var(--text-muted); background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 12px; }}
        .live-grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 0.8rem; margin-top: 0.8rem; }}
        .live-value {{ font-size: 1.15rem; font-weight: 700; }}
    </style>
</head>
    <body>
    <audio id="alert-chime" src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" preload="auto"></audio>
    <header>
        <div>
            <h1>EMBER COMMAND</h1>
            <p style="color: var(--text-muted); font-weight: 300;">PID-129 | Self-Validating Trading Loop</p>
        </div>
        <div class="status">
            <span id="connection-badge" class="badge-live">Live Feed: Connecting</span>
            <p id="sync-label" style="margin-top: 10px; color: var(--text-muted); font-size: 0.8rem;">Synced: {now}</p>
        </div>
    </header>
    <section class="panel">
        <h2>Live Tape & Context</h2>
        <div class="live-grid">
            <div class="stat-card"><div class="stat-label">BTC Mid</div><div id="live-mid" class="live-value">--</div></div>
            <div class="stat-card"><div class="stat-label">Spread</div><div id="live-spread" class="live-value">--</div></div>
            <div class="stat-card"><div class="stat-label">RVol</div><div id="tape-rvol" class="live-value">—</div></div>
            <div class="stat-card"><div class="stat-label">Vol Regime</div><div id="tape-vol-regime" class="live-value">—</div></div>
        </div>
        <div class="live-grid">
            <div class="stat-card"><div class="stat-label">OI Regime</div><div id="tape-oi-regime" class="live-value">—</div></div>
            <div class="stat-card"><div class="stat-label">Taker Ratio</div><div id="tape-taker" class="live-value">—</div></div>
            <div class="stat-card"><div class="stat-label">DXY Macro</div><div id="tape-dxy" class="live-value">—</div></div>
            <div class="stat-card"><div class="stat-label">Sentiment</div><div id="tape-sentiment" class="live-value">—</div></div>
        </div>
        <div class="live-grid">
            <div class="stat-card"><div class="stat-label">Balance</div><div id="live-balance" class="live-value">${balance:,.2f}</div></div>
            <div class="stat-card"><div class="stat-label">Win Rate (7d)</div><div id="live-winrate" class="live-value">--</div></div>
            <div class="stat-card"><div class="stat-label">Avg R (7d)</div><div id="live-pf" class="live-value">--</div></div>
            <div class="stat-card"><div class="stat-label">Risk Gate</div><div id="live-gate" class="live-value">--</div></div>
    </section>
    <div class="layout-grid">
        {verdict_html}
        <section class="panel" style="display: flex; flex-direction: column; padding: 0; overflow: hidden; min-height: 500px;">
            <div style="padding: 1.2rem; padding-bottom: 0;">
                <h2 style="margin: 0;">Live Charting</h2>
            </div>
            <!-- TradingView Widget BEGIN -->
            <div class="tradingview-widget-container" style="flex-grow: 1; height: 100%; width: 100%; padding: 1.2rem;">
              <div id="tradingview_chart" style="height: 100%; width: 100%;"></div>
              <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
              <script type="text/javascript">
              new TradingView.widget({{
                "autosize": true,
                "symbol": "BINANCE:BTCUSDT.P",
                "interval": "5",
                "timezone": "Etc/UTC",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "backgroundColor": "rgba(22, 22, 28, 0)",
                "gridColor": "#23232e",
                "hide_top_toolbar": false,
                "save_image": false,
                "container_id": "tradingview_chart"
              }});
              </script>
            </div>
            <!-- TradingView Widget END -->
        </section>
    </div>
    {execution_html}
    <section>
        <h2>Performance Metrics</h2>
        {p_html}
    </section>
    {edge_html}
    {lifecycle_html}
    {recent_alerts_html}
    <section>
        <h2>Active Signals</h2>
        <div class="grid">{alerts_html if alerts_html else '<p class="mini">No active signals detected.</p>'}</div>
    </section>
    <section class="scorecard-section">
        <h2>Intelligence Report</h2>
        <pre>{scorecard}</pre>
    </section>
    <footer style="margin-top: 2rem; text-align: center; color: var(--text-muted); padding-bottom: 2rem;">
        &copy; 2026 EMBER Loop | BTC Alerts MVP
    </footer>
    <dialog id="execModal" style="max-width:420px;border:1px solid var(--border);border-radius:14px;background:var(--surface);color:var(--text);padding:1rem;">
      <h3 style="margin-bottom:.5rem;">Confirm Execution</h3><p class="mini" id="execCountdown">Arming confirmation...</p>
      <div style="display:flex;gap:.5rem;margin-top:1rem;"><button id="cancelExec" class="pill badge-neutral" style="border:0;cursor:pointer;">Cancel</button><button id="confirmExec" class="pill badge-good" style="border:0;cursor:pointer;" disabled>Confirm</button></div>
    </dialog>
    <script>
      let state = {{livePrice:0,spread:0,inTrade:{'true' if bool(portfolio and portfolio.get('positions')) else 'false'},entryPrice:{vctx['entry']},tp1Price:{vctx['tp1']},stopPrice:{vctx['stop']},direction:"{vctx['direction']}"}};
      const els = {{badge:document.getElementById('connection-badge'),sync:document.getElementById('sync-label'),mid:document.getElementById('live-mid'),spread:document.getElementById('live-spread'),confluence:document.getElementById('live-confluence'),radar:document.getElementById('live-radar'),balance:document.getElementById('live-balance'),winrate:document.getElementById('live-winrate'),pf:document.getElementById('live-pf'),gate:document.getElementById('live-gate')}};
      function fmtMoney(n,d=0) {{ return Number.isFinite(n) ? '$' + n.toLocaleString(undefined,{{minimumFractionDigits:d,maximumFractionDigits:d}}) : '--'; }}
      function deriveConfluence(alerts) {{ const t=['5m','15m','1h'],m=Object.create(null); for (const a of (alerts||[])) if (a.symbol==='BTC' && t.includes(a.timeframe)) m[a.timeframe]=a; const p=t.map(tf=>m[tf]).filter(Boolean); if (p.length<3) return 'Partial'; const d=p.map(x=>String(x.direction||'NEUTRAL').toUpperCase()); return d.every(x=>x===d[0]&&x!=='NEUTRAL') ? d[0] + ' aligned' : 'Mixed'; }}
      function updateLivePrice() {{
        if(!state.livePrice) return;
        const priceEl=document.getElementById('livePrice');
        if(priceEl) {{
          const oldPrice = parseFloat(priceEl.textContent.replace(/[$,]/g, ''));
          priceEl.textContent=fmtMoney(state.livePrice,0);
          if (!isNaN(oldPrice)) {{
              if (state.livePrice > oldPrice) {{
                  priceEl.classList.remove('pulse-down');
                  void priceEl.offsetWidth;
                  priceEl.classList.add('pulse-up');
              }} else if (state.livePrice < oldPrice) {{
                  priceEl.classList.remove('pulse-up');
                  void priceEl.offsetWidth;
                  priceEl.classList.add('pulse-down');
              }}
          }}
        }}
        const spreadEl=document.getElementById('liveSpread');
        if(spreadEl) spreadEl.textContent='$'+state.spread.toFixed(1);
        if(state.entryPrice>0&&state.tp1Price>0&&state.stopPrice>0){{
          const toTp=state.direction==='SHORT' ? state.livePrice-state.tp1Price : state.tp1Price-state.livePrice;
          const toStop=state.direction==='SHORT' ? state.stopPrice-state.livePrice : state.livePrice-state.stopPrice;
          document.getElementById('distTP1').textContent=(toTp>=0?'+':'-')+'$'+Math.abs(toTp).toFixed(0)+' ('+((toTp/state.livePrice)*100).toFixed(2)+'%)';
          document.getElementById('distStop').textContent=(toStop>=0?'+':'-')+'$'+Math.abs(toStop).toFixed(0)+' ('+((toStop/state.livePrice)*100).toFixed(2)+'%)';
        }}
        if(state.inTrade && state.entryPrice>0){{
          const mult=state.direction==='SHORT'?-1:1;
          const pnl=(state.livePrice-state.entryPrice)*mult;
          const pnlEl=document.getElementById('livePnL');
          if(pnlEl){{pnlEl.textContent=(pnl>=0?'+':'-')+'$'+Math.abs(pnl).toFixed(0); pnlEl.style.color=pnl>=0?'var(--accent)':'#ff4d4d';}}
        }}
      }}
      function closeExecuteModal() {{ const m=document.getElementById('executeModal'); if(m) m.style.display='none'; }}
      function requestExecute(alertId) {{ const modal=document.getElementById('executeModal'); if(!modal) return; modal.style.display='flex'; document.getElementById('executeMeta').innerHTML='Alert: '+alertId+'<br>Direction: '+state.direction+'<br>Live: '+fmtMoney(state.livePrice,0); const btn=document.getElementById('confirmExecuteBtn'); let n=3; btn.disabled=true; btn.textContent='Confirm ('+n+')'; const t=setInterval(()=>{{n-=1; if(n<=0){{clearInterval(t); btn.disabled=false; btn.textContent='Confirm Execute'; btn.onclick=()=>closeExecuteModal();}} else {{btn.textContent='Confirm ('+n+')';}}}},1000); }}
      function connectWS() {{ const p=(location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws'; const ws=new WebSocket(p); ws.onopen=()=>{{els.badge.textContent='Live Feed: Online';els.badge.classList.remove('badge-stale');}}; ws.onmessage=(ev)=>{{ try {{ const data=JSON.parse(ev.data); const ob=data.orderbook||{{}}; state.livePrice=Number(ob.mid||0); state.spread=Number(ob.spread||0); updateLivePrice(); els.mid.textContent=fmtMoney(state.livePrice,2); els.spread.textContent=state.spread.toFixed(2); const po=data.portfolio||{{}}; els.balance.textContent=fmtMoney(Number(po.balance||0),2); const st=data.stats||{{}}; els.winrate.textContent=Number(st.win_rate||0).toFixed(2)+'%'; els.pf.textContent=Number(st.profit_factor||0).toFixed(2);
const btcAlerts = (data.alerts||[]).filter(a=>a.symbol==='BTC');
const wsLatest=btcAlerts.slice(-1)[0]||{{}};
const wsDir=String(wsLatest.direction||state.direction).toUpperCase();
const wsTier=String(wsLatest.tier||"").toUpperCase();
if (wsTier === "A+" && wsLatest.timestamp && wsLatest.timestamp !== window._lastPlayedAlertTs) {{
    window._lastPlayedAlertTs = wsLatest.timestamp;
    const audio = document.getElementById('alert-chime');
    if (audio) audio.play().catch(e => console.log('Audio blocked:', e));
    if (Notification.permission === "granted") {{
        new Notification("A+ Trade Alert", {{ body: `${{wsDir}} on ${{wsLatest.timeframe}}` }});
    }} else if (Notification.permission !== "denied") {{
        Notification.requestPermission();
    }}
}}
const wsCS=new Set(((wsLatest.decision_trace||{{}}).codes)||[]);
const wsCtx = ((wsLatest.decision_trace||{{}}).context)||{{}};
const wsSL = wsCtx.session_levels||{{}};
const wsVP = wsCtx.volume_profile||{{}};
const wsAV = wsCtx.avwap||{{}};
const wsST = wsCtx.structure||{{}};
const wsVI = wsCtx.volume_impulse||{{}};
const wsMC = wsCtx.macro_correlation||{{}};
const wsSN = wsCtx.sentiment||{{}};
const wsLQ = wsCtx.liquidity||{{}};
const wsOR = wsCtx.oi_regime||'—';

const _el = (id,v) => {{ const e=document.getElementById(id); if(e) e.textContent=v; }};
_el('tape-oi-regime', wsOR.toUpperCase());
_el('tape-dxy', (wsMC.dxy || '—').toUpperCase());
_el('tape-sentiment', wsSN.score ? wsSN.score.toFixed(2) : '—');
const taker = (data.flows||{{}}).taker_ratio;
_el('tape-taker', taker ? taker.toFixed(2) : '—');

_el('key-pdh', wsSL.pdh ? '$'+Number(wsSL.pdh).toLocaleString() : '—');
_el('key-pdl', wsSL.pdl ? '$'+Number(wsSL.pdl).toLocaleString() : '—');
_el('key-poc', wsVP.poc ? '$'+Number(wsVP.poc).toLocaleString() : '—');
_el('key-vah', wsVP.vah ? '$'+Number(wsVP.vah).toLocaleString() : '—');
_el('key-val', wsVP.val ? '$'+Number(wsVP.val).toLocaleString() : '—');
_el('key-avwap', wsAV.value ? '$'+Number(wsAV.value).toLocaleString() : '—');
_el('key-avwap-side', wsAV.position || '—');
const asE = document.getElementById('key-avwap-side');
if(asE && wsAV.position) {{ asE.style.color = wsAV.position==='ABOVE' ? '#00ff88' : wsAV.position==='BELOW' ? '#ff4444' : '#ffffff'; }}
_el('key-struct-event', wsST.event || wsST.trend || '—');
const seE = document.getElementById('key-struct-event');
if(seE && (wsST.event||wsST.trend)) {{ const t = (wsST.event||wsST.trend).toUpperCase(); seE.style.color = t.includes('BULL') ? '#00ff88' : t.includes('BEAR') ? '#ff4444' : '#ffffff'; }}
_el('key-pivot-high', wsST.last_pivot_high ? '$'+Number(wsST.last_pivot_high).toLocaleString() : '—');
_el('key-pivot-low', wsST.last_pivot_low ? '$'+Number(wsST.last_pivot_low).toLocaleString() : '—');
_el('key-bid-walls', wsLQ.bid_walls !== undefined ? wsLQ.bid_walls : '—');
_el('key-ask-walls', wsLQ.ask_walls !== undefined ? wsLQ.ask_walls : '—');
const eql = wsCtx.equal_levels||{{}};
_el('key-liq-targets', eql.eq_highs > 0 ? 'EQH' : eql.eq_lows > 0 ? 'EQL' : 'None');

const rvE = document.getElementById('tape-rvol');
if(rvE) {{ rvE.textContent = wsVI.rvol ? wsVI.rvol+'x' : '—'; rvE.style.color = wsVI.rvol>=2.0 ? '#00ff88' : wsVI.rvol>=1.2 ? '#ffa500' : '#ffffff'; }}
const vrE = document.getElementById('tape-vol-regime');
if(vrE) {{ vrE.textContent = (wsVI.regime||'—').toUpperCase(); vrE.style.color = wsVI.regime==='expansion' ? '#ff6b00' : wsVI.regime==='low' ? '#4488ff' : '#ffffff'; 
  if(wsCS.has('ATR_EXPANSION_ONSET')) {{ vrE.textContent += ' ⚡'; vrE.style.color = '#ff6b00'; }}
}}

const wsPD=[[['SQUEEZE_FIRE','SQUEEZE_ON'],[],'Squeeze'],[['HTF_ALIGNED'],['HTF_COUNTER'],'Trend (HTF)'],[['SENTIMENT_BULL','FLOW_TAKER_BULLISH','VOLUME_IMPULSE_BULL'],['SENTIMENT_BEAR','FLOW_TAKER_BEARISH','VOLUME_IMPULSE_BEAR'],'Momentum'],[['ML_CONFIDENCE_BOOST'],['ML_SKEPTICISM'],'ML Model'],[['FUNDING_EXTREME_LOW','FUNDING_LOW'],['FUNDING_EXTREME_HIGH','FUNDING_HIGH'],'Funding'],[['DXY_FALLING_BULLISH'],['DXY_RISING_BEARISH'],'DXY Macro'],[['GOLD_RISING_BULLISH'],['GOLD_FALLING_BEARISH'],'Gold Macro'],[['FG_EXTREME_FEAR','FG_FEAR'],['FG_EXTREME_GREED','FG_GREED'],'Fear & Greed'],[['BID_WALL_SUPPORT'],['ASK_WALL_RESISTANCE'],'Order Book'],[['OI_SURGE_MAJOR','OI_SURGE_MINOR','BASIS_BULLISH','OI_NEW_LONGS'],['BASIS_BEARISH','OI_NEW_SHORTS'],'OI / Basis'],[['STRUCTURE_BOS_BULL','STRUCTURE_CHOCH_BULL'],['STRUCTURE_BOS_BEAR','STRUCTURE_CHOCH_BEAR'],'Structure'],[['PDL_SWEEP_BULL','EQL_SWEEP_BULL','SESSION_LOW_SWEEP','PDH_RECLAIM_BULL'],['PDH_SWEEP_BEAR','EQH_SWEEP_BEAR','SESSION_HIGH_SWEEP','PDL_BREAK_BEAR'],'Levels'],[['AVWAP_RECLAIM_BULL'],['AVWAP_REJECT_BEAR'],'AVWAP'],[['ABOVE_VALUE'],['BELOW_VALUE'],'VP Status'],[['AUTO_RR_EXCELLENT'],['AUTO_RR_POOR'],'Auto R:R']];
let wsAl=0,wsAg=0;const wsRH=wsPD.map(([b,br,lbl])=>{{const hb=b.some(c=>wsCS.has(c));const hbr=br.some(c=>wsCS.has(c));let ic='⚫',co='var(--text-muted)';if((wsDir==='LONG'&&hb)||(wsDir==='SHORT'&&hbr)){{ic='🟢';co='var(--accent)';wsAl++;}}else if((wsDir==='LONG'&&hbr)||(wsDir==='SHORT'&&hb)){{ic='🔴';co='#ff4d4d';wsAg++;}}return "<div class='mini'>"+ic+" <span style='color:"+co+"'>"+lbl+"</span></div>";}}).join('');const wsT=wsPD.length,wsPct=Math.round((wsAl/wsT)*100),wsLbl=wsAl>=7?'STRONG':wsAl>=4?'MODERATE':'WEAK',wsClr=wsAl>=7?'var(--accent)':wsAl>=4?'#ffd700':'#ff4d4d',wsNet=wsAl-wsAg;els.gate.textContent=wsAl>=7?'GREEN':wsAl>=4?'AMBER':'RED';const rSc=document.getElementById('radarScore');if(rSc){{rSc.textContent=wsAl+'/'+wsT+' '+wsLbl;rSc.style.color=wsClr;rSc.style.borderColor=wsClr;}};const rBr=document.getElementById('radarBar');if(rBr){{rBr.style.width=wsPct+'%';rBr.style.background=wsClr;}};const rGr=document.getElementById('radarGrid');if(rGr)rGr.innerHTML=wsRH;const rNt=document.getElementById('radarNet');if(rNt){{rNt.textContent=(wsNet>=0?'+':'')+wsNet;rNt.style.color=wsNet>=0?'var(--accent)':'#ff4d4d';}}; els.sync.textContent='Synced: '+new Date().toLocaleString(); }} catch (_err) {{console.error(_err);}} }}; ws.onclose=()=>{{els.badge.textContent='Live Feed: Reconnecting';els.badge.classList.add('badge-stale');setTimeout(connectWS,1500);}}; }}

      connectWS();
      updateLivePrice();
    </script>
</body>
</html>
    """
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard generated: {OUTPUT_PATH}")
if __name__ == "__main__":
    generate_html()
