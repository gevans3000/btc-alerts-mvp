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
    if tier == "C":
        return "badge-monitor"
    return "badge-neutral"
def badge_class_for_direction(direction: str):
    if direction == "LONG":
        return "badge-good"
    if direction == "SHORT":
        return "badge-bad"
    return "badge-neutral"


def _rr_from_alert(alert):
    rr = alert.get("rr_ratio")
    if rr is not None:
        try:
            return float(rr)
        except Exception:
            return 0.0
    entry = float(alert.get("entry_price") or alert.get("entry") or 0.0)
    stop = float(alert.get("invalidation") or 0.0)
    tp1 = float(alert.get("tp1") or 0.0)
    denom = abs(entry - stop)
    return (abs(tp1 - entry) / denom) if denom > 0 else 0.0


def _alert_age_seconds(alert):
    ts = parse_dt(alert.get("timestamp"))
    if not ts:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds())


def _setup_quality_score(latest):
    one_h = latest.get("1h", {})
    fifteen = latest.get("15m", {})
    five = latest.get("5m", {})
    dirs = {"1h": get_direction(one_h), "15m": get_direction(fifteen), "5m": get_direction(five)}
    non_neutral = [d for d in dirs.values() if d != "NEUTRAL"]
    aligned = len(non_neutral) == 3 and len(set(non_neutral)) == 1
    base = 0
    if aligned:
        base += 35
    elif len(non_neutral) >= 2 and len(set(non_neutral)) == 1:
        base += 20
    else:
        base += 8

    c1 = get_confidence(one_h)
    c15 = get_confidence(fifteen)
    c5 = get_confidence(five)
    base += min(25, (c1 * 0.20 + c15 * 0.15 + c5 * 0.10))

    rr = _rr_from_alert(five)
    if rr >= 2.0:
        base += 18
    elif rr >= 1.2:
        base += 12
    elif rr >= 1.0:
        base += 6
    else:
        base -= 6

    blockers = set(get_blockers(five))
    if any(b in {"HTF_CONFLICT_15M", "HTF_CONFLICT_1H"} for b in blockers):
        base -= 16

    age_penalty = 0
    age_s = _alert_age_seconds(five)
    age_pct = percentile_used(age_s, "5m")
    if age_pct >= 90:
        age_penalty = 10
    elif age_pct >= 70:
        age_penalty = 5
    base -= age_penalty

    score = max(0, min(100, int(round(base))))
    return {
        "score": score,
        "rr": rr,
        "aligned": aligned,
        "age_pct": age_pct,
    }


def _dynamic_risk_pct(quality_score, portfolio, five_alert):
    # Base model: 0.25% floor to 1.25% cap
    risk = 0.25 + (max(0, min(quality_score, 100)) / 100.0)

    # Volatility proxy via stop distance (% of entry). Wider stops => reduce risk.
    entry = float(five_alert.get("entry_price") or five_alert.get("entry") or 0.0)
    stop = float(five_alert.get("invalidation") or 0.0)
    if entry > 0 and stop > 0:
        dist_pct = abs(entry - stop) / entry
        if dist_pct > 0.012:
            risk *= 0.75
        elif dist_pct < 0.006:
            risk *= 1.05

    dd = float((portfolio or {}).get("max_drawdown", 0.0))
    if dd >= 0.12:
        risk *= 0.5
    elif dd >= 0.08:
        risk *= 0.75

    return round(max(0.25, min(1.25, risk)), 2)
def execution_decision(latest):
    portfolio = get_portfolio() or {}
    one_h = latest.get("1h", {})
    fifteen = latest.get("15m", {})
    five = latest.get("5m", {})
    reasons = []
    if not one_h or not fifteen or not five:
        return "WAIT", "warn", ["Missing one or more BTC timeframes (5m/15m/1h)."], 0.0, 0

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

    quality = _setup_quality_score(latest)
    quality_score = quality["score"]
    if quality_score < 65:
        reasons.append(f"Setup quality {quality_score}/100 below execution threshold (65).")

    # EXECUTE only if all 3 non-neutral directions match + quality gate
    all_aligned = len(non_neutral) == 3 and aligned_count == 3
    decision = "EXECUTE" if all_aligned and quality_score >= 65 and not any("conflict" in r.lower() for r in reasons) else "WAIT"
    tone = "good" if decision == "EXECUTE" else "warn"

    risk_pct = 0.0
    if decision == "EXECUTE":
        risk_pct = _dynamic_risk_pct(quality_score, portfolio, five)
        if tier5 == "NO-TRADE":
            risk_pct = 0.0

    if not reasons:
        reasons = ["All timeframes aligned."]

    return decision, tone, reasons, risk_pct, quality_score


def percentile_used(age_seconds, tf):
    max_s = MAX_DURATION_SECONDS.get(tf, 24 * 3600)
    return (age_seconds / max_s) * 100 if max_s > 0 else 0
def render_execution_matrix(alerts):
    latest = latest_btc_by_timeframe(alerts)
    decision, tone, reasons, risk_pct, quality_score = execution_decision(latest)
    risk_html = f"<span class='pill badge-good' style='margin-left:12px;'>Suggested Risk: {risk_pct}%</span>" if risk_pct > 0 else ""
    quality_cls = "badge-good" if quality_score >= 75 else ("badge-warn" if quality_score >= 65 else "badge-bad")
    quality_html = f"<span class='pill {quality_cls}' style='margin-left:12px;'>Setup Quality: {quality_score}/100</span>"
    daily_cap_html = ""
    portfolio = get_portfolio() or {}
    balance = float(portfolio.get("balance", 10000.0))
    daily_cap = round(balance * 0.02, 2)
    daily_cap_html = f"<span class='mini' style='margin-left:8px;'>Daily risk budget cap: ${daily_cap:,.2f}</span>"
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
        blockers = ", ".join(get_blockers(a)[:2]) or "None"
        entry = float(a.get("entry_price") or a.get("entry") or 0)
        stop = float(a.get("invalidation") or 0)
        tp1_val = float(a.get("tp1") or 0)
        rr = float(a.get("rr_ratio") or 0)
        
        # Phase 23: Extract Recipe
        intel_obj = a.get("intel", {})
        recipe_list = intel_obj.get("recipes", [])
        recipe_name = recipe_list[0].get("recipe") if recipe_list else None
        recipe_label = f"<span class='pill badge-secondary' style='background:var(--secondary);'>🔮 {recipe_name}</span>" if recipe_name else ""
        
        # Risk size from recipe
        recipe_risk_size = recipe_list[0].get("risk_size") if recipe_list else None
        recipe_risk_str = f" · Risk: {recipe_risk_size:.2f} units" if recipe_risk_size else ""

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
        
        risk_label = f"<div class='mini' style='color:var(--accent);font-weight:700;'>Suggested Risk: {risk_pct}%{qty_str}{recipe_risk_str}</div>" if (risk_pct > 0 and tf == "5m") else ""
        
        cols.append(f"""
        <td>
            <div class="pill-wrap">
                <span class="pill {badge_class_for_direction(direction)}">{direction}</span>
                <span class="pill {badge_class_for_tier(tier)}">{tier}</span>
                <span class="pill badge-neutral">{conf}/100</span>
                {recipe_label}
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
                        {quality_html}
                        {risk_html}
                        {daily_cap_html}
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
    segmented = defaultdict(list)
    for t in closed:
        tf = t.get("timeframe")
        if tf in TARGET_TFS:
            grouped[tf].append(t)
            regime = str(t.get("regime") or "unknown").lower()
            session = str(t.get("session") or "unknown").lower()
            segmented[(tf, regime, session)].append(t)
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
    segment_rows = []
    best_hourly = None
    best_hourly_score = -10**9
    min_segment_sample = 8
    for (tf, regime, session), trades in sorted(segmented.items(), key=lambda x: (tf_sort_key(x[0][0]), x[0][1], x[0][2])):
        n = len(trades)
        wins = sum(1 for t in trades if str(t.get("outcome", "")).upper().startswith("WIN"))
        wr = (wins / n) * 100 if n else 0
        rs = [float(t.get("r_multiple", 0.0)) for t in trades]
        avg_r = sum(rs) / n if n else 0
        med_r = median(rs) if rs else 0.0
        lose_streak = max_losing_streak(trades)
        tone = "badge-good" if n >= min_segment_sample and avg_r > 0 else ("badge-warn" if n >= min_segment_sample else "badge-neutral")
        if tf == "1h" and n >= min_segment_sample and avg_r > best_hourly_score:
            best_hourly = (regime, session)
            best_hourly_score = avg_r
        segment_rows.append(
            f"<tr><td>{tf}</td><td>{regime}</td><td>{session}</td><td>{n}</td><td>{wr:.1f}%</td>"
            f"<td><span class='pill {tone}'>{avg_r:.2f}R</span></td><td>{med_r:.2f}R</td><td>{lose_streak}</td></tr>"
        )

    best_hourly_txt = f"{best_hourly[0]} / {best_hourly[1]}" if best_hourly else "No qualified 1h segment yet"
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
        <div style="margin-top:1rem;margin-bottom:0.5rem;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <span class="pill {'badge-good' if best_hourly else 'badge-warn'}">Best 1h Segment: {best_hourly_txt}</span>
            <span class="mini">Segment criteria: min {min_segment_sample} trades.</span>
        </div>
        <table class="matrix-table">
            <thead>
                <tr><th>TF</th><th>Regime</th><th>Session</th><th>Trades</th><th>Win Rate</th><th>Avg R</th><th>Median R</th><th>Max Losing Streak</th></tr>
            </thead>
            <tbody>
                {''.join(segment_rows) if segment_rows else "<tr><td colspan='8' class='mini'>No segmented trade records yet.</td></tr>"}
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
        icon_raw = "🟢" if aligned else "🔴" if against else "⚫"
        icon = f"<span class='pulse-dot'>{icon_raw}</span>" if icon_raw in ["🟢", "🔴"] else icon_raw
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
        
        # Phase 23: Recipe in list
        intel_obj = a.get("intel", {})
        recipe_list = intel_obj.get("recipes", [])
        recipe_name = recipe_list[0].get("recipe") if recipe_list else None
        recipe_part = f"<span class='mini' style='display:block;opacity:0.6;font-size:0.7em;'>{recipe_name}</span>" if recipe_name else ""
        
        rows_html.append(f"""
        <tr>
            <td>{tf}</td>
            <td><span class="pill {dir_cls}">{direction}</span>{recipe_part}</td>
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


def render_calibration_panel(portfolio):
    if not portfolio:
        return """
        <section class="panel">
            <h2>Confidence Calibration</h2>
            <p class="mini">No portfolio data available.</p>
        </section>
        """
    bins = [(0, 20), (21, 40), (41, 60), (61, 80), (81, 100)]
    grouped = {b: [] for b in bins}
    for t in portfolio.get("closed_trades", []):
        conf = int(t.get("confidence", 0) or 0)
        for b in bins:
            if b[0] <= conf <= b[1]:
                grouped[b].append(t)
                break

    rows = []
    last_wr = None
    monotonic = True
    for b in bins:
        trades = grouped[b]
        n = len(trades)
        wins = sum(1 for t in trades if str(t.get("outcome", "")).upper().startswith("WIN"))
        wr = (wins / n) * 100 if n else 0.0
        rs = [float(t.get("r_multiple", 0.0)) for t in trades]
        avg_r = (sum(rs) / n) if n else 0.0
        if n > 0 and last_wr is not None and wr < last_wr:
            monotonic = False
        if n > 0:
            last_wr = wr
        tone = "badge-good" if wr >= 55 else ("badge-warn" if wr >= 40 else "badge-bad")
        rows.append(
            f"<tr><td>{b[0]}-{b[1]}</td><td>{n}</td><td><span class='pill {tone}'>{wr:.1f}%</span></td><td>{avg_r:.2f}R</td></tr>"
        )

    return f"""
    <section class="panel">
        <h2>Confidence Calibration</h2>
        <div style="margin-bottom: 0.6rem;">
            <span class="pill {'badge-good' if monotonic else 'badge-warn'}">{'Calibrated trend OK' if monotonic else 'Calibration drift detected'}</span>
            <span class="mini" style="margin-left:8px;">Higher confidence bins should trend to better win rate/expectancy.</span>
        </div>
        <table class="matrix-table">
            <thead><tr><th>Confidence Bin</th><th>Trades</th><th>Realized Win Rate</th><th>Avg R</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </section>
    """


def render_no_trade_panel(alerts, portfolio):
    latest = latest_btc_by_timeframe(alerts)
    one_h = latest.get("1h", {})
    fifteen = latest.get("15m", {})
    five = latest.get("5m", {})
    quality = _setup_quality_score(latest)
    rr = _rr_from_alert(five) if five else 0.0
    c5 = get_confidence(five) if five else 0
    dir_1h = get_direction(one_h) if one_h else "NEUTRAL"
    dir_15m = get_direction(fifteen) if fifteen else "NEUTRAL"
    streak = max_losing_streak((portfolio or {}).get("closed_trades", []))
    dd = float((portfolio or {}).get("max_drawdown", 0.0))
    rules = [
        ("1h/15m direction aligned", dir_1h == dir_15m and dir_1h != "NEUTRAL"),
        ("5m confidence >= 40", c5 >= 40),
        ("Planned R:R >= 1.2", rr >= 1.2),
        ("Setup quality >= 65", quality["score"] >= 65),
        ("Max losing streak < 4", streak < 4),
        ("Max drawdown <= 12%", dd <= 0.12),
    ]
    locked = any(not ok for _, ok in rules)
    badge = "TRADE LOCKED" if locked else "TRADE ENABLED"
    cls = "badge-bad" if locked else "badge-good"
    rows = "".join(
        f"<div class='mini' style='color:{'var(--text)' if ok else '#ff4d4d'}'>{'✅' if ok else '❌'} {label}</div>" for label, ok in rules
    )
    return f"""
    <section class="panel">
        <h2>Do Not Trade Now</h2>
        <div style="margin-bottom:0.6rem;"><span class="pill {cls}">{badge}</span></div>
        {rows}
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
        execute_html = f"<button id='executeBtn' class='pill' style='padding:10px 14px;font-size:.9rem;width:100%;{bg}' onclick=\"requestExecute('latest-btc')\">{label}</button>"
    playbook_html = """
    <section class='panel'>
      <h2 style='margin:0 0 .7rem 0;'>Best Long vs Best Short (Right Now)</h2>
      <div class='mini' style='margin-bottom:.7rem;'>Operator Decision: <span id='operator-decision' class='pill badge-neutral'>WAIT</span></div>
      <div id='trap-risk' class='mini' style='margin-bottom:.7rem;color:#ffd700;'>Trap Risk: —</div>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:.8rem;'>
        <div style='border:1px solid var(--border);border-radius:10px;padding:.7rem;background:rgba(255,255,255,.02);'>
          <div style='display:flex;justify-content:space-between;align-items:center;'><span id='best-long-direction' class='pill badge-good'>LONG</span><span id='best-long-gate' class='pill badge-neutral'>—</span></div>
          <div class='mini'>Conf: <span id='best-long-confidence'>—</span> | R:R <span id='best-long-rr'>—</span> | Age <span id='best-long-age'>—</span></div>
          <div class='mini'>Entry <span id='best-long-entry'>—</span> | Stop <span id='best-long-stop'>—</span></div>
          <div class='mini'>TP1 <span id='best-long-tp1'>—</span> | TP2 <span id='best-long-tp2'>—</span></div>
          <div class='mini'>EV hint: <span id='best-long-ev'>—</span> | <span id='best-long-recipe'>—</span> <span id='best-long-timeframe'>—</span></div>
          <div id='best-long-codes' style='display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;'></div>
          <div id='best-long-blockers' class='mini' style='margin-top:6px;color:#ff7a7a;'>—</div>
        </div>
        <div style='border:1px solid var(--border);border-radius:10px;padding:.7rem;background:rgba(255,255,255,.02);'>
          <div style='display:flex;justify-content:space-between;align-items:center;'><span id='best-short-direction' class='pill badge-bad'>SHORT</span><span id='best-short-gate' class='pill badge-neutral'>—</span></div>
          <div class='mini'>Conf: <span id='best-short-confidence'>—</span> | R:R <span id='best-short-rr'>—</span> | Age <span id='best-short-age'>—</span></div>
          <div class='mini'>Entry <span id='best-short-entry'>—</span> | Stop <span id='best-short-stop'>—</span></div>
          <div class='mini'>TP1 <span id='best-short-tp1'>—</span> | TP2 <span id='best-short-tp2'>—</span></div>
          <div class='mini'>EV hint: <span id='best-short-ev'>—</span> | <span id='best-short-recipe'>—</span> <span id='best-short-timeframe'>—</span></div>
          <div id='best-short-codes' style='display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;'></div>
          <div id='best-short-blockers' class='mini' style='margin-top:6px;color:#ff7a7a;'>—</div>
        </div>
      </div>
    </section>
    """
    verdict_html = f"""
    <section class='panel'>
      <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;'>
        <h2 style='margin:0;'>Verdict Center</h2>
        <div style='display:flex;gap:4px;'>
          <button id='muteBtn' class='pill badge-neutral' onclick='toggleMute()' style='margin:0;cursor:pointer;min-width:40px;'>🔊</button>
          <button id='filterBtn' class='pill badge-neutral' onclick='toggleFilter()' style='margin:0;cursor:pointer;'>ALL</button>
        </div>
      </div>
      <div class='mini' style='margin-bottom:8px;'>Direction: <span class='pill {badge_class_for_direction(vctx['direction'])}'>{vctx['direction']}</span></div>
      <div class='mini' style='margin-bottom:8px;'>Edge (last {vctx.get('accuracy_total', 0)}): <span class='pill {"badge-good" if vctx.get("accuracy_pct", 0) >= 55 else "badge-warn" if vctx.get("accuracy_pct", 0) >= 40 else "badge-bad"}'>{vctx.get("accuracy_pct", 0):.0f}% ({vctx.get("accuracy_wins", 0)}W)</span>{" 🔥" + str(vctx.get("win_streak", 0)) if vctx.get("win_streak", 0) >= 3 else ""}</div>
      <div style='background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:12px;padding:1rem;margin-bottom:1rem;'>
        <div style='display:flex;justify-content:space-between;align-items:center;'><div><div class='mini'>Live BTC Price</div><div id='livePrice' style='font-weight:800;'>Loading...</div></div><div style='text-align:right;'><div class='mini'>Unrealized PnL</div><div id='livePnL'>—</div></div></div>
        <div style='display:flex;gap:1rem;margin-top:.6rem;'><div class='mini'>→ TP1 <span id='distTP1'>—</span></div><div class='mini'>→ STOP <span id='distStop'>—</span></div><div class='mini'>SPREAD <span id='liveSpread'>—</span></div></div>
        <div id="bs-filter-display" class="mini" style="margin-top:8px;padding:6px 10px;border-radius:8px;font-weight:700;font-size:0.78rem;text-align:center;transition:all 0.3s ease;"></div>
      </div>
      <div style='margin-bottom:1rem;'><div class='mini' style='margin-bottom:6px;'>Conviction Signals</div>{signals_html}</div>
      <div id='signal-dna-card' style='background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:12px;padding:.9rem;margin-bottom:1rem;'>
        <div class='mini' style='margin-bottom:6px;font-weight:700;letter-spacing:.04em;'>Signal DNA</div>
        <div id='toxic-warning' class='mini' style='padding:6px 10px;border-radius:8px;margin-bottom:.5rem;font-weight:700;transition:all .3s;display:none;'>—</div>
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;'>
          <div><div class='mini' style='opacity:.6;margin-bottom:3px;'>✅ Edge Codes</div><div id='dna-positive' style='display:flex;flex-wrap:wrap;gap:3px;'></div></div>
          <div><div class='mini' style='opacity:.6;margin-bottom:3px;'>⚠️ Toxic Codes</div><div id='dna-negative' style='display:flex;flex-wrap:wrap;gap:3px;'></div></div>
        </div>
      </div>
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
      <div id='rubricCard' style='background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:12px;padding:.9rem;margin-bottom:1rem;'>
        <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem;'><span class='mini'>Rubric Gate</span><span id='rubric-conviction' class='pill badge-neutral' style='transition:all .3s;'>—/6</span></div>
        <div style='display:grid;grid-template-columns:repeat(6,1fr);gap:4px;margin:.3rem 0;'>
          {''.join(f"<div id='rubric-seg-{d}' title='{d}' style='height:20px;border-radius:4px;background:rgba(255,255,255,0.06);transition:background .4s;cursor:default;'></div>" for d in ['structure','location','anchors','derivatives','momentum','volatility'])}
        </div>
        <div style='display:flex;justify-content:space-between;margin-top:.3rem;'>
          {''.join(f"<span class='mini' style='font-size:.65rem;opacity:.55;'>{d[:3].upper()}</span>" for d in ['structure','location','anchors','derivatives','momentum','volatility'])}
        </div>
        <div id='rubric-hist-edge' class='mini' style='margin-top:.5rem;opacity:.7;font-size:.72rem;'>Historical edge loading...</div>
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
    calibration_html = render_calibration_panel(portfolio)
    no_trade_html = render_no_trade_panel(alerts, portfolio)
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
        body {{
            background-color: #050507;
            background-image: 
                radial-gradient(circle at top right, rgba(0, 255, 204, 0.05), transparent 40%), 
                radial-gradient(circle at bottom left, rgba(112, 0, 255, 0.05), transparent 40%),
                linear-gradient(rgba(255, 255, 255, 0.015) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255, 255, 255, 0.015) 1px, transparent 1px);
            background-size: 100% 100%, 100% 100%, 30px 30px, 30px 30px;
            background-position: 0 0, 0 0, -1px -1px, -1px -1px;
            background-attachment: fixed;
            color: var(--text); 
            font-family: 'Outfit', sans-serif; 
            padding: 2rem; 
            max-width: 1400px; 
            margin: 0 auto;
        }}
        header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }}
        h1 {{ font-weight: 800; font-size: 2.5rem; letter-spacing: -1px; background: linear-gradient(135deg, var(--accent), var(--secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        h2 {{ margin-bottom: 1rem; font-weight: 800; font-size: 1.25rem; color: var(--accent); }}
        section {{ margin-bottom: 1.5rem; }}
        .panel, .card, .stat-card, .scorecard-section {{
            background: rgba(15, 15, 20, 0.6);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
            color: var(--text);
        }}
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
        .badge-monitor {{ background: rgba(150, 150, 150, 0.1); color: #999; border: 1px solid #666; opacity: 0.8; cursor: not-allowed; filter: grayscale(0.5); }}
        .mini {{ color: var(--text-muted); font-size: 0.82rem; margin-top: 4px; font-family: 'JetBrains Mono', monospace; }}
        .playbook {{ margin-top: 0.8rem; color: var(--text-muted); font-size: 0.92rem; }}
        .scorecard-section {{ background: var(--surface); border-radius: 18px; padding: 1.2rem; border: 1px solid var(--border); }}
        pre {{ font-family: 'JetBrains Mono', monospace; white-space: pre-wrap; font-size: 0.85rem; color: var(--text-muted); background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 12px; }}
        .live-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.8rem; margin-top: 0.8rem; }}
        @media (min-width: 768px) {{ .live-grid {{ grid-template-columns: repeat(4, 1fr); }} }}
        @media (min-width: 1100px) {{ .live-grid {{ grid-template-columns: repeat(6, 1fr); }} }}
        .bottom-panels {{ display: grid; grid-template-columns: 1fr; gap: 1.5rem; }}
        @media (min-width: 1100px) {{ .bottom-panels {{ grid-template-columns: 1fr 1fr; }} }}
        .live-value {{ 
            font-size: 1.15rem; 
            font-weight: 700; 
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
        }}
        #livePrice, #livePnL, #distTP1, #distStop, #liveSpread {{
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
            letter-spacing: -0.5px;
        }}
        #livePrice {{ font-size: 1.8rem !important; font-weight: 800; }}
        @keyframes breathePulse {{ 
            0% {{ opacity: 0.6; transform: scale(0.95); }} 
            50% {{ opacity: 1; transform: scale(1.05); }} 
            100% {{ opacity: 0.6; transform: scale(0.95); }} 
        }}
        .pulse-dot {{ 
            display: inline-block;
            animation: breathePulse 2.5s infinite ease-in-out; 
        }}
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
            <div class="stat-card"><div class="stat-label">OI Regime</div><div id="tape-oi-regime" class="live-value">—</div></div>
            <div class="stat-card"><div class="stat-label">Taker Ratio</div><div id="tape-taker" class="live-value">—</div></div>
            <div class="stat-card" style="border:1px solid rgba(112,0,255,0.3); background:rgba(112,0,255,0.05);">
                <div class="stat-label">Funding / Basis</div>
                <div id="tape-funding" class="live-value" style="color:#b580ff;">—</div>
            </div>
            <div class="stat-card" style="border:1px solid rgba(112,0,255,0.3); background:rgba(112,0,255,0.05);">
                <div class="stat-label">OI Delta (5m)</div>
                <div id="tape-oi-delta" class="live-value" style="color:#b580ff;">—</div>
            </div>
            <div class="stat-card"><div class="stat-label">DXY Macro</div><div id="tape-dxy" class="live-value">—</div></div>
            <div class="stat-card"><div class="stat-label">Sentiment</div><div id="tape-sentiment" class="live-value">—</div></div>
            <div class="stat-card"><div class="stat-label">Balance</div><div id="live-balance" class="live-value">${balance:,.2f}</div></div>
            <div class="stat-card"><div class="stat-label">Win Rate (7d)</div><div id="live-winrate" class="live-value">--</div></div>
            <div class="stat-card"><div class="stat-label">Avg R (7d)</div><div id="live-pf" class="live-value">--</div></div>
            <div class="stat-card"><div class="stat-label">Kelly %</div><div id="live-kelly" class="live-value">--</div></div>
            <div class="stat-card"><div class="stat-label">Risk Gate</div><div id="live-gate" class="live-value">--</div></div>
        </div>
    </section>
    <section id="circuit-breaker-banner" class="panel" style="display:none;border:2px solid #ff4d4d;background:rgba(255,77,77,0.15);">
        <h2 style="margin:0;color:#ff4d4d;">🛑 DO NOT TRADE — CIRCUIT BREAKER ACTIVE</h2>
        <p id="circuit-breaker-reason" style="margin:.5rem 0 0;color:#ffd2d2;">Risk controls triggered.</p>
    </section>
    {no_trade_html}
    <section class="panel" id="session-edge-panel" style="margin-bottom:1.5rem;">
      <h2 style="margin-bottom:.6rem;">Session Edge Heatmap</h2>
      <div id="hour-edge-banner" class="mini" style="padding:6px 10px;border-radius:8px;margin-bottom:.6rem;font-weight:700;font-size:.82rem;transition:all .3s;">Loading hour data...</div>
      <div style="display:grid;grid-template-columns:repeat(24,1fr);gap:3px;margin:.4rem 0;">
        {''.join(f"<div id='hour-cell-{h}' style='text-align:center;border-radius:5px;padding:4px 2px;font-size:.65rem;font-family:JetBrains Mono,monospace;font-weight:600;background:rgba(255,255,255,0.04);color:var(--text-muted);cursor:default;transition:all .3s;'>{h:02d}</div>" for h in range(24))}
      </div>
      <div class="mini" style="margin-top:.3rem;opacity:.6;">UTC hours · 🟢 Profitable ≥ +0.1R · 🔴 Unprofitable ≤ -0.1R · 🟡 Breakeven · Glowing = current hour</div>
    </section>
    <div class="layout-grid">
        {playbook_html}
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
                "container_id": "tradingview_chart",
                "studies": [
                  "Volume@tv-basicstudies",
                  "VWAP@tv-basicstudies"
                ]
              }});
              </script>
            </div>
            <!-- TradingView Widget END -->
        </section>
        <section class="panel" style="padding: 1.2rem;">
            <h2 style="margin: 0 0 0.8rem 0;">Execution Copilot</h2>
            <div id="copilot-container" style="display:flex;align-items:center;gap:1rem;">
                <div id="copilot-action-btn" class="pill badge-neutral" style="font-size:1.1rem;padding:10px 18px;white-space:nowrap;min-width:180px;text-align:center;">STANDBY</div>
                <div>
                    <div id="copilot-msg" class="mini" style="color:var(--text-muted);">No active positions</div>
                    <div id="copilot-detail" class="mini" style="color:var(--text-muted);margin-top:4px;font-family:JetBrains Mono,monospace;font-size:0.75rem;"></div>
                </div>
            </div>
        </section>
    </div>
    {execution_html}
    <div class="bottom-panels">
        <div>
            <section style="margin-bottom: 1.5rem;">
                <h2>Performance Metrics</h2>
                {p_html}
            </section>
            {edge_html}
            {calibration_html}
        </div>
        <div>
            {lifecycle_html}
            {recent_alerts_html}
        </div>
    </div>
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
      const els = {{badge:document.getElementById('connection-badge'),sync:document.getElementById('sync-label'),mid:document.getElementById('live-mid'),spread:document.getElementById('live-spread'),confluence:document.getElementById('live-confluence'),radar:document.getElementById('live-radar'),balance:document.getElementById('live-balance'),winrate:document.getElementById('live-winrate'),pf:document.getElementById('live-pf'),kelly:document.getElementById('live-kelly'),gate:document.getElementById('live-gate'),cbanner:document.getElementById('circuit-breaker-banner'),creason:document.getElementById('circuit-breaker-reason'),execBtn:document.getElementById('executeBtn')}};
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
      function requestExecute(alertId) {{
          const modal = document.getElementById('executeModal');
          if (!modal) return;
          modal.style.display = 'flex';
          const cachedStats = window._lastStats || {{}};
          const kelly = cachedStats.kelly_pct || 0.05;
          const bal = window._lastBalance || 10000;
          const maxRisk = kelly * bal;
          const metaEl = document.getElementById('executeMeta');
          metaEl.innerHTML = 'Alert: ' + alertId
              + '<br>Direction: ' + state.direction
              + '<br>Live: ' + fmtMoney(state.livePrice, 0)
              + '<br><br><div style="padding:10px;border:1px solid #ff4d4d;border-radius:8px;background:rgba(255,0,0,0.08);">'
              + '<span style="color:#ff4d4d;font-weight:bold;font-size:1rem;">MAX RISK: ' + fmtMoney(maxRisk, 2) + '</span><br>'
              + '<span class="mini" style="color:var(--text-muted);">Kelly: ' + (kelly * 100).toFixed(1) + '% · Balance: ' + fmtMoney(bal, 0) + '</span><br>'
              + '<span class="mini" style="color:#ff4d4d;">Exceeding this violates your mathematical edge.</span></div>';
          const btn = document.getElementById('confirmExecuteBtn');
          let n = 3; btn.disabled = true; btn.textContent = 'Confirm (' + n + ')';
          const t = setInterval(() => {{
              n -= 1;
              if (n <= 0) {{
                  clearInterval(t);
                  btn.disabled = false;
                  btn.textContent = 'Confirm Execute';
                  btn.onclick = () => closeExecuteModal();
              }} else {{ btn.textContent = 'Confirm (' + n + ')'; }}
          }}, 1000);
      }}
      function _pillClass(g) {{
        const v=String(g||'').toUpperCase();
        if(v==='GREEN') return 'badge-good';
        if(v==='AMBER') return 'badge-warn';
        if(v==='RED') return 'badge-bad';
        return 'badge-neutral';
      }}
      function _set(id,val) {{ const e=document.getElementById(id); if(e) e.textContent = (val===undefined||val===null||val==='') ? '—' : String(val); }}
      function updateCandidateCard(prefix, c) {{
        if(!c) {{
          ['confidence','rr','age','entry','stop','tp1','tp2','ev','recipe','timeframe','blockers'].forEach(k=>_set(prefix+'-'+k,'—'));
          const codeEl=document.getElementById(prefix+'-codes'); if(codeEl) codeEl.innerHTML='';
          const g=document.getElementById(prefix+'-gate'); if(g) {{ g.textContent='RED'; g.className='pill badge-bad'; }}
          return;
        }}
        _set(prefix+'-confidence', Number(c.confidence||0).toFixed(0));
        _set(prefix+'-rr', Number(c.rr_ratio||0).toFixed(2));
        const age=Number(c.age_seconds||0); _set(prefix+'-age', age>=60 ? (age/60).toFixed(1)+'m' : age.toFixed(0)+'s');
        _set(prefix+'-entry', c.entry_zone||'—'); _set(prefix+'-stop', c.invalidation||'—'); _set(prefix+'-tp1', c.tp1||'—'); _set(prefix+'-tp2', c.tp2||'—');
        _set(prefix+'-ev', Number(c.expectancy_hint||0).toFixed(3)); _set(prefix+'-recipe', c.recipe||'—'); _set(prefix+'-timeframe', c.timeframe||'');
        const gEl=document.getElementById(prefix+'-gate'); if(gEl) {{ gEl.textContent=(c.gate_status||'—').toUpperCase(); gEl.className='pill '+_pillClass(c.gate_status); }}
        const b=[...(c.blockers||[]),...(c.cautions||[])].slice(0,5); _set(prefix+'-blockers', b.length?b.join(' • '):'None');
        const codeEl=document.getElementById(prefix+'-codes');
        if(codeEl) codeEl.innerHTML=((c.reason_codes||[]).slice(0,5)).map(x=>"<span class='pill badge-neutral'>"+x+"</span>").join('');
      }}
      function connectWS() {{ const p=(location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws'; const ws=new WebSocket(p); ws.onopen=()=>{{els.badge.textContent='Live Feed: Online';els.badge.classList.remove('badge-stale');}}; ws.onmessage=(ev)=>{{ try {{ const data=JSON.parse(ev.data); const ob=data.orderbook||{{}}; state.livePrice=Number(ob.mid||0); state.spread=Number(ob.spread||0); updateLivePrice(); els.mid.textContent=fmtMoney(state.livePrice,2); els.spread.textContent=state.spread.toFixed(2); const po=data.portfolio||{{}}; els.balance.textContent=fmtMoney(Number(po.balance||0),2); const st=data.stats||{{}}; window._lastStats = st; window._lastBalance = Number(po.balance || 0); els.winrate.textContent=Number(st.win_rate||0).toFixed(2)+'%'; els.pf.textContent=Number(st.profit_factor||0).toFixed(2); if (els.kelly) els.kelly.textContent=(Number(st.kelly_pct||0)*100).toFixed(2)+'%';
const pf=data.profit_preflight||{{}};
updateCandidateCard('best-long', pf.best_long_candidate||null);
updateCandidateCard('best-short', pf.best_short_candidate||null);
_set('operator-decision', pf.operator_decision||'WAIT');
const od=document.getElementById('operator-decision');
if(od) {{ const t=String(pf.operator_decision||'WAIT'); od.className='pill '+(t.includes('LONG')?'badge-good':t.includes('SHORT')?'badge-bad':'badge-neutral'); }}
_set('trap-risk', pf.trap_risk_message||'Trap Risk: —');

// ── Phase 25: Overrides + Auto-Pilot Indicator ──
state.overrides = data.overrides || {{}};
const fBtn = document.getElementById('filterBtn');
const ap = data.auto_pilot || {{}};
if (fBtn) {{
    if (ap.active) {{
        fBtn.textContent = '🤖 AUTO (' + (ap.auto_muted || []).length + ' muted)';
        fBtn.className = 'pill badge-warn';
        fBtn.title = 'Auto-pilot muting: ' + (ap.auto_muted || []).join(', ') + ' | Regime: ' + (ap.regime || 'normal');
    }} else if (state.overrides.min_score) {{
        fBtn.textContent = 'FLOOR: ' + state.overrides.min_score;
        fBtn.className = 'pill badge-good';
        fBtn.title = '';
    }} else {{
        fBtn.textContent = 'ALL';
        fBtn.className = 'pill badge-neutral';
        fBtn.title = '';
    }}
}}

if (els.execBtn) {{
  const op=String(pf.operator_decision||'WAIT');
  const longGate=((pf.best_long_candidate||{{}}).gate_status||'').toUpperCase();
  const shortGate=((pf.best_short_candidate||{{}}).gate_status||'').toUpperCase();
  const gate = op.includes('LONG') ? longGate : (op.includes('SHORT') ? shortGate : 'RED');
  els.execBtn.disabled = op==='WAIT' || gate==='RED';
  els.execBtn.textContent = op==='WAIT' ? 'WAIT — GATE BLOCKED' : ('1-CLICK '+op);
  els.execBtn.style.opacity = els.execBtn.disabled ? '0.7' : '1.0';
  els.execBtn.style.cursor = els.execBtn.disabled ? 'not-allowed' : 'pointer';
  els.execBtn.style.background = gate==='GREEN' ? '' : (gate==='AMBER' ? '#996f00' : '#7a1f1f');
}}
const btcAlerts = (data.alerts||[]).filter(a=>a.symbol==='BTC');
const wsLatest=btcAlerts.slice(-1)[0]||{{}};
const wsDir=String(wsLatest.direction||state.direction).toUpperCase();
const wsTier=String(wsLatest.tier||"").toUpperCase();

const cb = data.circuit_breaker || {{}};
if (cb.active) {{
    if (els.cbanner) els.cbanner.style.display='block';
    if (els.creason) els.creason.textContent=cb.reason || 'Risk controls triggered.';
    if (els.execBtn) {{ 
        els.execBtn.disabled = true; 
        els.execBtn.textContent = '⛔ CIRCUIT BREAKER (' + (cb.reason || 'high risk') + ')'; 
        els.execBtn.style.opacity = '0.5'; 
        els.execBtn.style.cursor = 'not-allowed'; 
    }}
}} else {{
    if (els.cbanner) els.cbanner.style.display='none';
    if (els.execBtn) {{ 
        els.execBtn.disabled = false;
        els.execBtn.style.opacity = '1';
        els.execBtn.style.cursor = 'pointer';
        // ── Phase 26 Task 4.1: Restore the original label based on latest alert tier ──
        const tier = wsTier || 'NO-TRADE';
        if (tier === 'A+') {{
            els.execBtn.textContent = '🟢 EXECUTE';
            els.execBtn.style.background = '#00cc88';
        }} else if (tier === 'B') {{
            els.execBtn.textContent = '🟡 EXECUTE (WATCH)';
            els.execBtn.style.background = '#cc8800';
        }} else {{
            els.execBtn.textContent = '⚠️ EXECUTE (HIGH RISK)';
            els.execBtn.style.background = '#ff4d4d';
        }}
    }}
}}
if (wsTier === "A+" && wsLatest.timestamp && wsLatest.timestamp !== window._lastPlayedAlertTs) {{
    window._lastPlayedAlertTs = wsLatest.timestamp;
    if (!window._isMuted) {{
        const audio = document.getElementById('alert-chime');
        if (audio) audio.play().catch(e => console.log('Audio blocked:', e));
    }}
    if (Notification.permission === "granted") {{
        new Notification("A+ Trade Alert", {{ body: wsDir + ' on ' + wsLatest.timeframe }});
    }} else if (Notification.permission !== "denied") {{
        Notification.requestPermission();
    }}
}}
const wsCS=new Set(((wsLatest.decision_trace||{{}}).codes)||[]);
const alertCtx = ((wsLatest.decision_trace||{{}}).context)||{{}};
const cachedCtx = data.cached_context||{{}};
// ── Phase 26 Gap 1 Fix: Merge live alert context, fall back to cached ──
const wsCtx = Object.assign({{}}, cachedCtx, alertCtx);
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

// ── Phase 26 Task 7.2: Smart Money UI ──
const wsDeriv = wsCtx.derivatives || {{}};
const fundRate = wsDeriv.funding_rate;
const basis = wsDeriv.basis_pct;
const oiDelta = wsDeriv.oi_change_pct;

const fundEl = document.getElementById('tape-funding');
if (fundEl) {{
    if (fundRate !== undefined && basis !== undefined) {{
        const fStr = (fundRate * 100).toFixed(4) + '%';
        const bStr = basis > 0 ? '+' + basis.toFixed(2) + '%' : basis.toFixed(2) + '%';
        fundEl.textContent = fStr + ' | ' + bStr;
        if (fundRate > 0.0001) fundEl.style.color = '#ff4d4d';
        else if (fundRate < -0.0001) fundEl.style.color = '#00ffcc';
        else fundEl.style.color = '#b580ff';
    }} else {{ fundEl.textContent = '—'; }}
}}
const oiEl = document.getElementById('tape-oi-delta');
if (oiEl) {{
    if (oiDelta !== undefined) {{
        oiEl.textContent = (oiDelta > 0 ? '+' : '') + oiDelta.toFixed(2) + '%';
        if (oiDelta > 1.5) oiEl.style.color = '#00ffcc';
        else if (oiDelta < -1.5) oiEl.style.color = '#ff4d4d';
        else oiEl.style.color = '#b580ff';
    }} else {{ oiEl.textContent = '—'; }}
}}

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
let wsAl=0,wsAg=0;const wsRH=wsPD.map(([b,br,lbl])=>{{const hb=b.some(c=>wsCS.has(c));const hbr=br.some(c=>wsCS.has(c));let ic='⚫',co='var(--text-muted)';if((wsDir==='LONG'&&hb)||(wsDir==='SHORT'&&hbr)){{ic='🟢';co='var(--accent)';wsAl++;}}else if((wsDir==='LONG'&&hbr)||(wsDir==='SHORT'&&hb)){{ic='🔴';co='#ff4d4d';wsAg++;}}return "<div class='mini'>"+ic+" <span style='color:"+co+"'>"+lbl+"</span></div>";}}).join('');const wsT=wsPD.length,wsPct=Math.round((wsAl/wsT)*100),wsLbl=wsAl>=7?'STRONG':wsAl>=4?'MODERATE':'WEAK',wsClr=wsAl>=7?'var(--accent)':wsAl>=4?'#ffd700':'#ff4d4d',wsNet=wsAl-wsAg;els.gate.textContent=wsAl>=7?'GREEN':wsAl>=4?'AMBER':'RED';const rSc=document.getElementById('radarScore');if(rSc){{rSc.textContent=wsAl+'/'+wsT+' '+wsLbl;rSc.style.color=wsClr;rSc.style.borderColor=wsClr;}};const rBr=document.getElementById('radarBar');if(rBr){{rBr.style.width=wsPct+'%';rBr.style.background=wsClr;}};const rGr=document.getElementById('radarGrid');if(rGr)rGr.innerHTML=wsRH;const rNt=document.getElementById('radarNet');if(rNt){{rNt.textContent=(wsNet>=0?'+':'')+wsNet;rNt.style.color=wsNet>=0?'var(--accent)':'#ff4d4d';}};

// ── Rubric Quality Gate ──
const wsRubric=((wsLatest.decision_trace||{{}}).rubric)||{{}};
const wsRubricDetails=wsRubric.details||{{}};
const wsRubricScore=typeof wsRubric.score==='number'?wsRubric.score:(typeof wsRubric.confluence_score==='number'?wsRubric.confluence_score:-1);
['structure','location','anchors','derivatives','momentum','volatility'].forEach(dim=>{{
  const seg=document.getElementById('rubric-seg-'+dim);
  if(seg){{seg.style.background=wsRubricDetails[dim]?'var(--accent)':'rgba(255,255,255,0.06)';seg.title=dim+': '+(wsRubricDetails[dim]?'✅ ACTIVE':'⚫ INACTIVE');}}
}});
const convEl=document.getElementById('rubric-conviction');
if(convEl&&wsRubricScore>=0){{
  let rl,rc;
  if(wsRubricScore>=5){{rl='HIGH CONVICTION';rc='var(--accent)';}}
  else if(wsRubricScore===4){{rl='STANDARD';rc='#ffd700';}}
  else if(wsRubricScore===3){{rl='MARGINAL';rc='#ffa500';}}
  else{{rl='AVOID';rc='#ff4d4d';}}
  convEl.textContent=wsRubricScore+'/6 '+rl;
  convEl.style.color=rc;convEl.style.borderColor=rc;
  const rubricCard=document.getElementById('rubricCard');
  if(rubricCard){{rubricCard.style.borderColor=rc;rubricCard.style.background='rgba('+( wsRubricScore>=5?'0,255,204':wsRubricScore>=4?'255,215,0':wsRubricScore>=3?'255,165,0':'255,77,77')+',0.04)';}}
}}
const rubricStats=data.rubric_stats||{{}};
const curRubricStats=rubricStats[String(wsRubricScore)]||null;
const rubricEdgeEl=document.getElementById('rubric-hist-edge');
if(rubricEdgeEl){{
  if(curRubricStats){{rubricEdgeEl.textContent='Historical: '+(curRubricStats.wr*100).toFixed(0)+'% WR · '+(curRubricStats.avg_r>=0?'+':'')+curRubricStats.avg_r.toFixed(2)+'R avg · '+curRubricStats.count+' trades';rubricEdgeEl.style.color=curRubricStats.avg_r>0?'var(--accent)':curRubricStats.avg_r<-0.05?'#ff4d4d':'#ffd700';}}
  else{{rubricEdgeEl.textContent='No historical data for rubric '+wsRubricScore;rubricEdgeEl.style.color='var(--text-muted)';}}
}}

// ── Code Toxicity Filter ──
const codeEdge=data.code_edge||{{}};
const activeCodes=Array.from(wsCS);
const toxicCodes=activeCodes.filter(c=>{{const e=codeEdge[c];return e&&e.total>=8&&e.wr<0.40;}}).sort((a,b)=>(codeEdge[a].wr||1)-(codeEdge[b].wr||1));
const edgeCodes=activeCodes.filter(c=>{{const e=codeEdge[c];return e&&e.total>=8&&e.wr>=0.60;}}).sort((a,b)=>(codeEdge[b].wr||0)-(codeEdge[a].wr||0));
const toxicWarn=document.getElementById('toxic-warning');
if(toxicWarn){{
  if(toxicCodes.length>0){{
    const w=toxicCodes[0];const we=codeEdge[w];
    toxicWarn.innerHTML='⚠️ TOXIC: '+w+' ('+(we.wr*100).toFixed(0)+'% WR · '+we.total+' trades) — consider SKIP';
    toxicWarn.style.cssText='padding:6px 10px;border-radius:8px;margin-bottom:.5rem;font-weight:700;transition:all .3s;background:rgba(255,77,77,0.12);color:#ff4d4d;border:1px solid rgba(255,77,77,0.4);display:block;';
  }}else{{
    toxicWarn.innerHTML='✅ No toxic codes active';
    toxicWarn.style.cssText='padding:6px 10px;border-radius:8px;margin-bottom:.5rem;font-weight:700;transition:all .3s;background:rgba(0,255,204,0.06);color:var(--accent);border:1px solid rgba(0,255,204,0.2);display:block;';
  }}
}}
const dnaPos=document.getElementById('dna-positive');
if(dnaPos)dnaPos.innerHTML=edgeCodes.length?edgeCodes.slice(0,4).map(c=>{{const e=codeEdge[c];return "<span class='pill badge-good' title='"+(e.wr*100).toFixed(0)+"% WR/"+e.total+" trades'>"+c+"</span>";}}).join(''):"<span class='mini' style='opacity:.5;'>None firing</span>";
const dnaNeg=document.getElementById('dna-negative');
if(dnaNeg)dnaNeg.innerHTML=toxicCodes.length?toxicCodes.slice(0,4).map(c=>{{const e=codeEdge[c];return "<span class='pill badge-bad' title='"+(e.wr*100).toFixed(0)+"% WR/"+e.total+" trades'>"+c+"</span>";}}).join(''):"<span class='mini' style='opacity:.5;'>None active</span>";

// ── Session Edge Heatmap ──
const hourStats=data.hour_stats||{{}};
const curHour=new Date().getUTCHours();
for(let h=0;h<24;h++){{
  const cell=document.getElementById('hour-cell-'+h);
  if(!cell)continue;
  const hs=hourStats[String(h)];
  cell.style.boxShadow=h===curHour?'0 0 0 2px var(--accent)':'none';
  cell.style.fontWeight=h===curHour?'800':'600';
  if(hs&&hs.count>=3){{
    if(hs.avg_r>0.10&&hs.wr>0.55){{cell.style.background='rgba(0,255,204,0.22)';cell.style.color='#00ffcc';}}
    else if(hs.avg_r<-0.10||hs.wr<0.35){{cell.style.background='rgba(255,77,77,0.18)';cell.style.color='#ff4d4d';}}
    else{{cell.style.background='rgba(255,215,0,0.12)';cell.style.color='#ffd700';}}
    cell.title=h+':00 UTC | WR:'+(hs.wr*100).toFixed(0)+'% | AvgR:'+hs.avg_r.toFixed(2)+' | N='+hs.count;
  }}else{{cell.style.background='rgba(255,255,255,0.04)';cell.style.color='var(--text-muted)';cell.title=h+':00 UTC — <3 trades';}}
}}
const hourBanner=document.getElementById('hour-edge-banner');
if(hourBanner){{
  const chs=hourStats[String(curHour)];
  if(chs&&chs.count>=3){{
    const isG=chs.avg_r>0.10&&chs.wr>0.55,isB=chs.avg_r<-0.10||chs.wr<0.35;
    const hc=isG?'var(--accent)':(isB?'#ff4d4d':'#ffd700'),hi=isG?'🟢':(isB?'🔴':'🟡');
    hourBanner.innerHTML=hi+' Hour '+curHour+':00 UTC | WR: '+(chs.wr*100).toFixed(0)+'% · AvgR: '+(chs.avg_r>=0?'+':'')+chs.avg_r.toFixed(2)+'R · N='+chs.count;
    hourBanner.style.cssText='padding:6px 10px;border-radius:8px;margin-bottom:.6rem;font-weight:700;font-size:.82rem;color:'+hc+';background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);transition:all .3s;';
  }}else{{
    hourBanner.innerHTML='⚫ Hour '+curHour+':00 UTC — insufficient data (<3 trades)';
    hourBanner.style.cssText='padding:6px 10px;border-radius:8px;margin-bottom:.6rem;font-weight:700;font-size:.82rem;color:var(--text-muted);background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);transition:all .3s;';
  }}
}}

// ── Phase 26 Task 6.2: Data Freshness Warning ──
const dataAge = data.data_age_seconds || 0;
const syncEl = els.sync;
if (syncEl) {{
    if (dataAge > 300) {{
        syncEl.textContent = '⚠️ DATA STALE (' + Math.round(dataAge / 60) + 'm old)';
        syncEl.style.color = '#ff4d4d';
    }} else if (dataAge > 120) {{
        syncEl.textContent = 'Synced: ' + new Date().toLocaleString() + ' (⏳ ' + Math.round(dataAge) + 's ago)';
        syncEl.style.color = '#ffa500';
    }} else {{
        syncEl.textContent = 'Synced: ' + new Date().toLocaleString();
        syncEl.style.color = 'var(--text-muted)';
    }}
}}

// ── Phase 25: BS-Filter Warning ──
const bsEl = document.getElementById('bs-filter-display');
if (bsEl) {{
    const bsText = data.bs_filter || 'CLEAR';
    const bsSev = data.bs_severity || 0;
    if (bsSev === 0) {{
        bsEl.textContent = '✅ ORDER FLOW CLEAR';
        bsEl.style.background = 'rgba(0,255,204,0.06)';
        bsEl.style.color = 'var(--accent)';
        bsEl.style.border = '1px solid rgba(0,255,204,0.2)';
    }} else {{
        bsEl.textContent = bsText;
        if (bsSev >= 2) {{
            bsEl.style.background = 'rgba(255,77,77,0.15)';
            bsEl.style.color = '#ff4d4d';
            bsEl.style.border = '1px solid rgba(255,77,77,0.4)';
        }} else {{
            bsEl.style.background = 'rgba(255,165,0,0.1)';
            bsEl.style.color = '#ffa500';
            bsEl.style.border = '1px solid rgba(255,165,0,0.3)';
        }}
    }}
}}

// ── Phase 25: Execution Copilot ──
const cpAction = document.getElementById('copilot-action-btn');
const cpMsg = document.getElementById('copilot-msg');
const cpDetail = document.getElementById('copilot-detail');
if (cpAction && cpMsg) {{
    let cpText = 'STANDBY';
    let cpMessage = 'No active positions — monitoring.';
    let cpClass = 'pill badge-neutral';
    let cpExtra = '';
    const positions = (po.positions || []);
    if (positions.length > 0 && state.livePrice > 0) {{
        const pos = positions[0];
        const entry = Number(pos.entry_price) || 0;
        const dir = pos.direction || 'LONG';
        const sz = Number(pos.size_usdt) || 0;
        if (entry > 0 && sz > 0 && isFinite(entry)) {{
            const pnlPct = dir === 'LONG'
                ? ((state.livePrice - entry) / entry) * 100
                : ((entry - state.livePrice) / entry) * 100;
            const pnlDollar = (pnlPct / 100) * sz;
            cpExtra = dir + ' @ ' + fmtMoney(entry,0) + ' | PnL: ' + (pnlDollar >= 0 ? '+' : '') + '$' + Math.abs(pnlDollar).toFixed(0) + ' (' + pnlPct.toFixed(2) + '%)';
            if (pnlPct > 1.5) {{
                cpText = '💰 TAKE 50% + TRAIL';
                cpMessage = 'Massive run detected (+' + pnlPct.toFixed(2) + '%). Take partial profit and trail stop to breakeven.';
                cpClass = 'pill badge-good';
                cpAction.style.animation = 'breathePulse 1.5s infinite ease-in-out';
            }} else if (pnlPct > 0.75) {{
                cpText = '🔒 MOVE STOP → BE';
                cpMessage = 'Momentum intact (+' + pnlPct.toFixed(2) + '%). Trail stop to breakeven — risk-free trade.';
                cpClass = 'pill badge-good';
                cpAction.style.animation = '';
            }} else if (pnlPct > 0.0) {{
                cpText = '✊ HOLD';
                cpMessage = 'Position active at ' + fmtMoney(entry,0) + '. Let edge play out.';
                cpClass = 'pill badge-warn';
                cpAction.style.animation = '';
            }} else if (pnlPct > -0.75) {{
                cpText = '⚠️ PATIENCE';
                cpMessage = 'Minor heat (' + pnlPct.toFixed(2) + '%). Still within normal noise range.';
                cpClass = 'pill badge-warn';
                cpAction.style.animation = '';
            }} else {{
                cpText = '🚨 CUT LOSSES';
                cpMessage = 'Trade invalidated (' + pnlPct.toFixed(2) + '%). Market-close to protect capital.';
                cpClass = 'pill badge-bad';
                cpAction.style.animation = 'breathePulse 1s infinite ease-in-out';
            }}
        }}
    }}
    cpAction.textContent = cpText;
    cpAction.className = cpClass;
    cpMsg.textContent = cpMessage;
    if (cpDetail) cpDetail.textContent = cpExtra;
}}

}} catch (_err) {{console.error(_err);}} }}; ws.onclose=()=>{{els.badge.textContent='Live Feed: Reconnecting';els.badge.classList.add('badge-stale');setTimeout(connectWS,1500);}}; }}

      function toggleMute() {{
          window._isMuted = !window._isMuted;
          document.getElementById('muteBtn').textContent = window._isMuted ? '🔇' : '🔊';
          document.getElementById('muteBtn').classList.toggle('badge-bad', window._isMuted);
      }}
      function toggleFilter() {{
          window._isAOnly = !window._isAOnly;
          const btn = document.getElementById('filterBtn');
          btn.textContent = window._isAOnly ? 'A+ ONLY' : 'ALL';
          btn.classList.toggle('badge-good', window._isAOnly);
          // Simple visual filter for the recent signals table
          const rows = document.querySelectorAll('.matrix-table tbody tr');
          rows.forEach(r => {{
              if (window._isAOnly) {{
                  const tier = r.cells[3]?.textContent || "";
                  r.style.display = tier.includes('A+') ? '' : 'none';
              }} else {{
                  r.style.display = '';
              }}
          }});
      }}

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
