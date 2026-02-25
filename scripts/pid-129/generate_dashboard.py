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
    return ctx if isinstance(ctx, dict) else {}
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
        return "WAIT", "warn", ["Missing one or more BTC timeframes (5m/15m/1h)."]
    d1, d15, d5 = get_direction(one_h), get_direction(fifteen), get_direction(five)
    a5 = str(five.get("action") or "SKIP").upper()
    c5 = get_confidence(five)
    b5 = get_blockers(five)
    if d1 == "NEUTRAL" or d15 == "NEUTRAL" or d5 == "NEUTRAL":
        reasons.append("At least one timeframe is neutral.")
    if not (d1 == d15 == d5):
        reasons.append("Direction mismatch across 1h/15m/5m.")
    if any(b in {"HTF_CONFLICT_15M", "HTF_CONFLICT_1H"} for b in b5):
        reasons.append("5m has HTF conflict blocker.")
    if not (a5 == "TRADE" or (a5 == "WATCH" and c5 >= 70)):
        reasons.append("5m trigger is not TRADE or high-confidence WATCH.")
    if reasons:
        return "WAIT", "warn", reasons
    return "EXECUTE", "good", ["All timeframes aligned and 5m trigger passed."]


def build_verdict_context(alerts, portfolio):
    latest = latest_btc_by_timeframe(alerts)
    decision, tone, reasons = execution_decision(latest)
    a5 = latest.get("5m", {})
    ctx = get_context(a5)
    verdict = {
        "alert_id": str(a5.get("id") or a5.get("alert_id") or "latest-btc"),
        "direction": get_direction(a5 if a5 else {"direction": "WAIT"}) if decision == "EXECUTE" else "WAIT",
        "entry": float(a5.get("entry_price") or a5.get("entry") or 0.0),
        "tp1": float(a5.get("tp1") or 0.0),
        "invalidation": float(a5.get("invalidation") or 0.0),
        "rr_ratio": float(a5.get("rr_ratio") or 0.0),
        "ml_prob": float(a5.get("ml_prob") or a5.get("ml_probability") or get_confidence(a5) / 100.0),
        "reason_codes": (a5.get("decision_trace") or {}).get("codes", []) if isinstance(a5, dict) else [],
    }
    tf_bias = {tf: {"direction": get_direction(a)} for tf, a in latest.items()}
    directions = [v["direction"] for v in tf_bias.values() if v["direction"] != "NEUTRAL"]
    tf_aligned = len(set(directions)) == 1 and len(directions) >= 2
    stats = {"streak": 0, "max_dd": 0.0}
    if isinstance(portfolio, dict):
        stats["streak"] = -max_losing_streak(portfolio.get("closed_trades", []))
        stats["max_dd"] = float(portfolio.get("max_drawdown") or 0.0) * 100
    gate_checks = {
        "tf_aligned": {"pass": tf_aligned, "label": "Timeframes Aligned", "icon_pass": "✅", "icon_fail": "⚠️"},
        "ml_confident": {"pass": verdict["ml_prob"] * 100 >= 60, "label": "ML Confidence ≥ 60%", "icon_pass": "✅", "icon_fail": "❌"},
        "streak_ok": {"pass": stats["streak"] >= -2, "label": "Streak ≥ -2", "icon_pass": "✅", "icon_fail": "🧊"},
        "dd_ok": {"pass": stats["max_dd"] < 10, "label": "Drawdown < 10%", "icon_pass": "✅", "icon_fail": "🔴"},
        "rr_ok": {"pass": verdict["rr_ratio"] >= 1.5, "label": "R:R ≥ 1.5x", "icon_pass": "✅", "icon_fail": "⚠️"},
    }
    gate_pass_count = sum(1 for g in gate_checks.values() if g["pass"])
    gate_verdict = "GREEN" if gate_pass_count >= 4 else ("AMBER" if gate_pass_count >= 3 else "RED")
    active_codes = set(verdict["reason_codes"])
    probes = [
        ("squeeze", "Squeeze", ["SQUEEZE_FIRE"], []), ("trend", "Trend (HTF)", ["HTF_ALIGNED"], ["HTF_COUNTER"]),
        ("momentum", "Momentum", ["SENTIMENT_BULL"], ["SENTIMENT_BEAR"]), ("ml", "ML Model", ["ML_CONFIDENCE_BOOST"], ["ML_SKEPTICISM"]),
        ("funding", "Funding", ["FUNDING_EXTREME_LOW", "FUNDING_LOW"], ["FUNDING_EXTREME_HIGH", "FUNDING_HIGH"]),
        ("macro_dxy", "DXY Macro", ["DXY_FALLING_BULLISH"], ["DXY_RISING_BEARISH"]), ("macro_gold", "Gold Macro", ["GOLD_RISING_BULLISH"], ["GOLD_FALLING_BEARISH"]),
        ("fear_greed", "Fear & Greed", ["FG_EXTREME_FEAR", "FG_FEAR"], ["FG_EXTREME_GREED", "FG_GREED"]),
        ("orderbook", "Order Book", ["BID_WALL_SUPPORT"], ["ASK_WALL_RESISTANCE"]), ("deriv", "OI / Basis", ["OI_SURGE_MAJOR", "OI_SURGE_MINOR", "BASIS_BULLISH"], ["BASIS_BEARISH"]),
    ]
    alignment_results = []
    for probe_id, label, bulls, bears in probes:
        has_bull, has_bear = any(c in active_codes for c in bulls), any(c in active_codes for c in bears)
        if verdict["direction"] == "LONG":
            status = "aligned" if has_bull else ("against" if has_bear else "inactive")
        elif verdict["direction"] == "SHORT":
            status = "aligned" if has_bear else ("against" if has_bull else "inactive")
        else:
            status = "inactive"
        alignment_results.append({"id": probe_id, "label": label, "status": status})
    return {"decision": decision, "tone": tone, "reasons": reasons, "verdict": verdict, "tf_bias": tf_bias, "gate_checks": gate_checks,
            "gate_pass_count": gate_pass_count, "gate_total": len(gate_checks), "gate_verdict": gate_verdict, "alignment_results": alignment_results,
            "aligned_count": sum(1 for r in alignment_results if r["status"] == "aligned"), "against_count": sum(1 for r in alignment_results if r["status"] == "against"),
            "total_probes": len(alignment_results), "confluence_layers": ctx.get("score_breakdown") if isinstance(ctx.get("score_breakdown"), dict) else {}}
def percentile_used(age_seconds, tf):
    max_s = MAX_DURATION_SECONDS.get(tf, 24 * 3600)
    return (age_seconds / max_s) * 100 if max_s > 0 else 0
def render_execution_matrix(alerts):
    latest = latest_btc_by_timeframe(alerts)
    decision, tone, reasons = execution_decision(latest)
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
        cols.append(f"""
        <td>
            <div class="pill-wrap">
                <span class="pill {badge_class_for_direction(direction)}">{direction}</span>
                <span class="pill {badge_class_for_tier(tier)}">{tier}</span>
                <span class="pill badge-neutral">{conf}/100</span>
            </div>
            <div class="mini">Regime: {regime} · Session: {session}</div>
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
    rows = [r[2] for r in sortable]
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
    signals_html = "".join(f"<span class='pill badge-neutral'>{c}</span>" for c in vctx["verdict"]["reason_codes"][:8]) or "<span class='mini'>No active reason codes.</span>"
    gate_color = "var(--accent)" if vctx["gate_verdict"] == "GREEN" else ("#ffd700" if vctx["gate_verdict"] == "AMBER" else "#ff4d4d")
    gate_bg = "rgba(0,255,204,0.05)" if vctx["gate_verdict"] == "GREEN" else ("rgba(255,215,0,0.08)" if vctx["gate_verdict"] == "AMBER" else "rgba(255,77,77,0.08)")
    gate_rows = "".join(
        f"<div class='mini' style='color:{'var(--text)' if c['pass'] else '#ff4d4d'}'>{c['icon_pass'] if c['pass'] else c['icon_fail']} {c['label']}</div>"
        for c in vctx["gate_checks"].values()
    )
    a_count, t_probes = vctx["aligned_count"], vctx["total_probes"]
    radar_color = "var(--accent)" if a_count >= 7 else ("#ffd700" if a_count >= 4 else "#ff4d4d")
    radar_label = "STRONG" if a_count >= 7 else ("MODERATE" if a_count >= 4 else "WEAK")
    radar_rows = "".join(
        f"<div class='mini'>{'🟢' if p['status']=='aligned' else ('🔴' if p['status']=='against' else '⚫')} <span style='color:{'var(--accent)' if p['status']=='aligned' else ('#ff4d4d' if p['status']=='against' else 'var(--text-muted)')}'>{p['label']}</span></div>"
        for p in vctx["alignment_results"]
    )
    execute_html = ""
    if vctx["verdict"]["direction"] != "WAIT":
        label = "⚠️ EXECUTE (HIGH RISK)" if vctx["gate_verdict"] == "RED" else "1-CLICK EXECUTE"
        bg = "background:#ff4d4d;" if vctx["gate_verdict"] == "RED" else ""
        execute_html = f"<button id='executeBtn' class='pill' style='padding:10px 14px;font-size:.9rem;{bg}' onclick=\"requestExecute('{vctx['verdict']['alert_id']}')\">{label}</button>"
    verdict_html = f"""
    <section class='panel'>
      <h2>Verdict Center</h2>
      <div class='mini' style='margin-bottom:8px;'>Direction: <span class='pill {badge_class_for_direction(vctx['verdict']['direction'])}'>{vctx['verdict']['direction']}</span></div>
      <div style='background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:12px;padding:1rem;margin-bottom:1rem;'>
        <div style='display:flex;justify-content:space-between;align-items:center;'><div><div class='mini'>Live BTC Price</div><div id='livePrice' style='font-size:1.6rem;font-weight:800;'>Loading...</div></div><div style='text-align:right;'><div class='mini'>Unrealized PnL</div><div id='livePnL'>—</div></div></div>
        <div style='display:flex;gap:1rem;margin-top:.6rem;'><div class='mini'>→ TP1 <span id='distTP1'>—</span></div><div class='mini'>→ STOP <span id='distStop'>—</span></div><div class='mini'>SPREAD <span id='liveSpread'>—</span></div></div>
      </div>
      <div style='margin-bottom:1rem;'><div class='mini' style='margin-bottom:6px;'>Conviction Signals</div>{signals_html}</div>
      <div style='background:rgba(255,255,255,.03);border:1px solid {radar_color};border-radius:12px;padding:1rem;margin-bottom:1rem;'>
        <div style='display:flex;justify-content:space-between;'><span class='mini'>Confluence Radar</span><span class='pill' style='border:1px solid {radar_color};color:{radar_color};'>{a_count}/{t_probes} {radar_label}</span></div>
        <div style='height:6px;background:rgba(255,255,255,.08);border-radius:4px;margin:.5rem 0 .8rem;'><div style='height:100%;width:{int((a_count/t_probes)*100) if t_probes else 0}%;background:{radar_color};'></div></div>
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;'>{radar_rows}</div>
      </div>
      <div style='background:{gate_bg};border:1px solid {gate_color};border-radius:12px;padding:1rem;margin-bottom:1rem;'><div style='display:flex;justify-content:space-between;'><span class='mini'>Trade Safety</span><span class='pill' style='border:1px solid {gate_color};color:{gate_color};'>{vctx['gate_verdict']} ({vctx['gate_pass_count']}/{vctx['gate_total']})</span></div>{gate_rows}</div>
      {execute_html}
    </section>
    <div id='executeModal' style='display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:99;align-items:center;justify-content:center;'>
      <div style='background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1rem;max-width:360px;width:90%;'><h3 style='margin-bottom:.6rem;'>Confirm Execute</h3><div id='executeMeta' class='mini'></div><div style='margin-top:1rem;display:flex;gap:.5rem;justify-content:flex-end;'><button class='pill badge-neutral' onclick='closeExecuteModal()'>Cancel</button><button id='confirmExecuteBtn' class='pill badge-good' disabled>Confirm (3)</button></div></div>
    </div>
    """
    execution_html = render_execution_matrix(alerts)
    edge_html = render_edge_scoreboard(portfolio)
    lifecycle_html = render_lifecycle_panel(alerts)
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
        :root {{ --bg:#050507; --surface:#0f0f13; --card-bg:#16161c; --accent:#00ffcc; --secondary:#7000ff; --text:#fff; --text-muted:#80808a; --border:#23232e; }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ background-color: var(--bg); color: var(--text); font-family: 'Outfit', sans-serif; padding: 2rem; max-width: 1400px; margin: 0 auto; }}
        header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }}
        h1 {{ font-weight: 800; font-size: 2.5rem; letter-spacing: -1px; background: linear-gradient(135deg, var(--accent), var(--secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        h2 {{ margin-bottom: 1rem; font-weight: 800; font-size: 1.25rem; color: var(--accent); }}
        section {{ margin-bottom: 1.5rem; }}
        .panel {{ background: var(--surface); border-radius: 18px; border: 1px solid var(--border); padding: 1.2rem; }}
        .status {{ text-align: right; }}
        .badge-live {{ background: rgba(0,255,204,0.1); color: var(--accent); padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; border: 1px solid rgba(0,255,204,0.4); }}
        .badge-stale {{ background: rgba(255,77,77,0.12); color: #ff4d4d; border-color: rgba(255,77,77,0.4); }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }}
        .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 20px; padding: 1.2rem; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1rem; }}
        .stat-card {{ background: var(--surface); padding: 1rem; border-radius: 16px; border: 1px solid var(--border); }}
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
    <section class="panel"><h2>Live Tape</h2><div class="live-grid"><div class="stat-card"><div class="stat-label">BTC Mid</div><div id="live-mid" class="live-value">--</div></div><div class="stat-card"><div class="stat-label">Spread</div><div id="live-spread" class="live-value">--</div></div><div class="stat-card"><div class="stat-label">Confluence</div><div id="live-confluence" class="live-value">--</div></div><div class="stat-card"><div class="stat-label">Radar</div><div id="live-radar" class="live-value">--</div></div></div><div class="live-grid"><div class="stat-card"><div class="stat-label">Balance</div><div id="live-balance" class="live-value">${balance:,.2f}</div></div><div class="stat-card"><div class="stat-label">Win Rate</div><div id="live-winrate" class="live-value">--</div></div><div class="stat-card"><div class="stat-label">Profit Factor</div><div id="live-pf" class="live-value">--</div></div><div class="stat-card"><div class="stat-label">Risk Gate</div><div id="live-gate" class="live-value">--</div></div></div></section>
    {verdict_html}
    {execution_html}
    <section>
        <h2>Performance Metrics</h2>
        {p_html}
    </section>
    {edge_html}
    {lifecycle_html}
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
    <script>(()=>{{const els={{badge:document.getElementById('connection-badge'),sync:document.getElementById('sync-label'),mid:document.getElementById('live-mid'),spread:document.getElementById('live-spread'),confluence:document.getElementById('live-confluence'),radar:document.getElementById('live-radar'),balance:document.getElementById('live-balance'),winrate:document.getElementById('live-winrate'),pf:document.getElementById('live-pf'),gate:document.getElementById('live-gate')}};let attempt=0,lastUpdateMs=0;const wsUrl=()=>`${{window.location.protocol==='https:'?'wss:':'ws:'}}//${{window.location.hostname}}:8000/ws`,fmtMoney=n=>Number.isFinite(n)?`$${{n.toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}})}}`:'--',fmtNum=(n,d=2)=>Number.isFinite(n)?n.toFixed(d):'--',setBadge=(t,s=false)=>{{els.badge.textContent=t;els.badge.classList.toggle('badge-stale',s);}},deriveConfluence=a=>{{const t=['5m','15m','1h'],m=Object.create(null);for(const x of a||[])if(x.symbol==='BTC'&&t.includes(x.timeframe))m[x.timeframe]=x;const p=t.map(tf=>m[tf]).filter(Boolean);if(p.length<3)return'Partial';const d=p.map(x=>String(x.direction||'NEUTRAL').toUpperCase());return d.every(x=>x===d[0]&&x!=='NEUTRAL')?`${{d[0]}} aligned`:'Mixed';}},deriveRadar=a=>{{let b=0;for(const x of a||[])b+=Array.isArray(x.blockers)?x.blockers.length:0;return b?`${{b}} blockers`:'Clear';}},deriveGate=s=>{{const pf=Number(s?.profit_factor??0),avgR=Number(s?.avg_r??0);if(pf>=1.4&&avgR>0)return'OPEN';if(pf>=1.0)return'WATCH';return'LOCK';}},apply=p=>{{const ob=p?.orderbook||{{}},po=p?.portfolio||{{}},al=p?.alerts||[],st=p?.stats||{{}};els.mid.textContent=fmtMoney(Number(ob.mid));els.spread.textContent=fmtNum(Number(ob.spread),2);els.balance.textContent=fmtMoney(Number(po.balance));els.winrate.textContent=`${{fmtNum(Number(st.win_rate),2)}}%`;els.pf.textContent=fmtNum(Number(st.profit_factor),2);els.gate.textContent=deriveGate(st);els.confluence.textContent=deriveConfluence(al);els.radar.textContent=deriveRadar(al);lastUpdateMs=Date.now();els.sync.textContent=`Synced: ${{new Date().toLocaleString()}}`;setBadge('Live Feed: Online');}},connect=()=>{{const ws=new WebSocket(wsUrl());ws.onopen=()=>{{attempt=0;setBadge('Live Feed: Online');}};ws.onmessage=e=>{{try{{apply(JSON.parse(e.data));}}catch(_err){{}}}};ws.onclose=()=>{{setBadge('Live Feed: Reconnecting',true);attempt+=1;window.setTimeout(connect,Math.min(10000,1000*(2**Math.min(attempt,4))));}};ws.onerror=()=>ws.close();}};window.setInterval(()=>{{if(!lastUpdateMs||Date.now()-lastUpdateMs>8000)setBadge('Live Feed: Stale',true);}},2000);connect();}})();</script>
    <script>
      let state = {{livePrice:0,spread:0,inTrade:{'true' if bool(portfolio and portfolio.get('positions')) else 'false'},entryPrice:{vctx['verdict']['entry']},tp1Price:{vctx['verdict']['tp1']},stopPrice:{vctx['verdict']['invalidation']},direction:"{vctx['verdict']['direction']}"}};
      function updateLivePrice() {{ const el=document.getElementById('livePrice'); if(!el||!state.livePrice) return; el.innerText='$'+state.livePrice.toLocaleString(undefined,{{maximumFractionDigits:0}}); if(state.entryPrice>0&&state.tp1Price>0&&state.stopPrice>0){{const a=state.tp1Price-state.livePrice,b=state.stopPrice-state.livePrice; document.getElementById('distTP1').innerText=(a>=0?'+':'')+'$'+Math.abs(a).toFixed(0)+' ('+((a/state.livePrice)*100).toFixed(2)+'%)'; document.getElementById('distStop').innerText=(b>=0?'+':'')+'$'+Math.abs(b).toFixed(0)+' ('+((b/state.livePrice)*100).toFixed(2)+'%)';}} document.getElementById('liveSpread').innerText='$'+(state.spread||0).toFixed(1); if(state.inTrade&&state.entryPrice>0){{const m=state.direction==='LONG'?1:-1,p=(state.livePrice-state.entryPrice)*m,pct=(p/state.entryPrice)*100,pel=document.getElementById('livePnL'); pel.innerText=(p>=0?'+':'')+'$'+p.toFixed(0)+' ('+pct.toFixed(2)+'%)'; pel.style.color=p>=0?'var(--accent)':'#ff4d4d';}} if(state.entryPrice>0){{const above=state.livePrice>=state.entryPrice,fav=(state.direction==='LONG'&&above)||(state.direction==='SHORT'&&!above); el.style.color=fav?'var(--accent)':'#ff4d4d';}} }}
      function closeExecuteModal() {{ document.getElementById('executeModal').style.display='none'; }}
      function requestExecute(alertId) {{ const modal=document.getElementById('executeModal'); if(!modal) return; modal.style.display='flex'; document.getElementById('executeMeta').innerHTML='Alert: '+alertId+'<br>Direction: '+state.direction+'<br>Live: $'+(state.livePrice||0).toLocaleString(); const btn=document.getElementById('confirmExecuteBtn'); let n=3; btn.disabled=true; btn.textContent='Confirm ('+n+')'; const t=setInterval(()=>{{n-=1; if(n<=0){{clearInterval(t); btn.disabled=false; btn.textContent='Confirm Execute'; btn.onclick=()=>executeTrade(alertId);}} else {{btn.textContent='Confirm ('+n+')';}}}},1000); }}
      async function executeTrade(alertId) {{ console.log('execute', alertId); closeExecuteModal(); }}
      function connectWS() {{ const p=(location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws'; const ws=new WebSocket(p); ws.onmessage=(ev)=>{{ try {{ const data=JSON.parse(ev.data); if(data.orderbook&&data.orderbook.mid){{state.livePrice=data.orderbook.mid; state.spread=data.orderbook.spread||0;}} updateLivePrice(); }} catch(e) {{}} }}; ws.onclose=()=>setTimeout(connectWS,1500); }}
      connectWS(); updateLivePrice();
    </script>
</body>
</html>
    """
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard generated: {OUTPUT_PATH}")
if __name__ == "__main__":
    generate_html()
