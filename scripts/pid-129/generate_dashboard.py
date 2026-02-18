#!/usr/bin/env python3
import json
import os
from pathlib import Path
from datetime import datetime

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# Fallback to current working directory if structure is different
if not (BASE_DIR / "logs").exists():
    BASE_DIR = Path.cwd()
STATE_PATH = BASE_DIR / ".mvp_alert_state.json"
PORTFOLIO_PATH = BASE_DIR / "data" / "paper_portfolio.json"
SCORECARD_PATH = BASE_DIR / "reports" / "pid-129-daily-scorecard.md"
OUTPUT_PATH = BASE_DIR / "dashboard.html"

def get_state():
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text())
    except: return {}

def get_portfolio():
    if not PORTFOLIO_PATH.exists(): return None
    try: return json.loads(PORTFOLIO_PATH.read_text())
    except: return None

def get_scorecard():
    if not SCORECARD_PATH.exists(): return "No scorecard found yet."
    return SCORECARD_PATH.read_text(encoding='utf-8')

def generate_svg_equity(curve):
    if not curve or len(curve) < 2:
        return ""
    
    # Simple SVG chart
    width, height = 800, 200
    points = [p['balance'] for p in curve]
    min_b, max_b = min(points), max(points)
    span = max_b - min_b if max_b > min_b else 1.0
    
    # Pad vertical range
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
        <path d="M0,{height} {" ".join(["L"+p for p in svg_points])} L{width},{height} Z" fill="url(#grad)" />
    </svg>
    """

def generate_html():
    state = get_state()
    portfolio = get_portfolio()
    scorecard = get_scorecard()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format alerts for the dashboard
    alerts_html = ""
    for symbol, tfs in state.items():
        if symbol in ["lifecycle_key", "regime", "last_sent", "tp1_hit"]: continue
        for tf, data in tfs.items():
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

    # Portfolio metrics
    p_html = "<p>No portfolio data available.</p>"
    equity_svg = ""
    if portfolio:
        balance = portfolio.get('balance', 10000)
        pnl = balance - 10000
        pnl_pct = (pnl / 10000) * 100
        pnl_color = "var(--accent)" if pnl >= 0 else "#ff4d4d"
        
        equity_svg = generate_svg_equity(portfolio.get('equity_curve', []))
        
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
        <div class="chart-container">
            {equity_svg}
        </div>
        """

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
        :root {{
            --bg: #050507;
            --surface: #0f0f13;
            --card-bg: #16161c;
            --accent: #00ffcc;
            --secondary: #7000ff;
            --text: #ffffff;
            --text-muted: #80808a;
            --border: #23232e;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg);
            color: var(--text);
            font-family: 'Outfit', sans-serif;
            padding: 2rem;
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 3rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
        }}

        h1 {{
            font-weight: 800;
            font-size: 2.5rem;
            letter-spacing: -1px;
            background: linear-gradient(135deg, var(--accent), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .status {{ text-align: right; }}
        .badge-live {{
            background: rgba(0, 255, 204, 0.1);
            color: var(--accent);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }}

        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 1.5rem;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .card:hover {{ transform: translateY(-5px); border-color: var(--accent); box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.5rem;
            margin-bottom: 1.5rem;
        }}

        .stat-card {{
            background: var(--surface);
            padding: 1.5rem;
            border-radius: 20px;
            border: 1px solid var(--border);
        }}

        .stat-label {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem; }}
        .stat-value {{ font-size: 2rem; font-weight: 800; }}
        .stat-sub {{ font-size: 0.8rem; font-family: 'JetBrains Mono', monospace; }}

        .chart-container {{
            background: var(--surface);
            padding: 1rem;
            border-radius: 20px;
            border: 1px solid var(--border);
            margin-bottom: 3rem;
        }}

        h2 {{ margin-bottom: 1.5rem; font-weight: 800; font-size: 1.5rem; color: var(--accent); }}

        .scorecard-section {{
            background: var(--surface);
            border-radius: 24px;
            padding: 2.5rem;
            border: 1px solid var(--border);
        }}

        pre {{
            font-family: 'JetBrains Mono', monospace;
            white-space: pre-wrap;
            font-size: 0.9rem;
            color: var(--text-muted);
            background: rgba(0,0,0,0.3);
            padding: 1.5rem;
            border-radius: 12px;
        }}
    </style>
</head>
<body>
    <header>
        <div>
            <h1>EMBER COMMAND</h1>
            <p style="color: var(--text-muted); font-weight: 300;">PID-129 | Self-Validating Trading Loop</p>
        </div>
        <div class="status">
            <span class="badge-live">System Active</span>
            <p style="margin-top: 10px; color: var(--text-muted); font-size: 0.8rem;">Synced: {now}</p>
        </div>
    </header>

    <section>
        <h2>Performance Metrics</h2>
        {p_html}
    </section>

    <section>
        <h2>Active Signals</h2>
        <div class="grid">
            {alerts_html if alerts_html else "<p>No active signals detected.</p>"}
        </div>
    </section>

    <section class="scorecard-section">
        <h2>Intelligence Report</h2>
        <pre>{scorecard}</pre>
    </section>

    <footer style="margin-top: 4rem; text-align: center; color: var(--text-muted); padding-bottom: 2rem;">
        &copy; 2026 EMBER Loop | BTC Alerts MVP
    </footer>
</body>
</html>
    """
    OUTPUT_PATH.write_text(html, encoding='utf-8')
    print(f"Dashboard generated: {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_html()
