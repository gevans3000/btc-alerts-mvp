#!/usr/bin/env python3
import json
import os
from pathlib import Path
from datetime import datetime

# Paths
BASE_DIR = Path("/Users/superg/btc-alerts-mvp")
STATE_PATH = BASE_DIR / ".mvp_alert_state.json"
SCORECARD_PATH = BASE_DIR / "reports" / "pid-129-daily-scorecard.md"
OUTPUT_PATH = BASE_DIR / "dashboard.html"

def get_state():
    if not STATE_PATH.exists(): return {}
    return json.loads(STATE_PATH.read_text())

def get_scorecard():
    if not SCORECARD_PATH.exists(): return "No scorecard found yet."
    return SCORECARD_PATH.read_text()

def generate_html():
    state = get_state()
    scorecard = get_scorecard()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format alerts for the dashboard
    alerts_html = ""
    for symbol, tfs in state.items():
        if symbol in ["lifecycle_key", "regime", "last_sent", "tp1_hit"]: continue
        for tf, data in tfs.items():
            tier = data.get("tier", "N/A")
            color = "var(--accent)" if "A+" in tier else "var(--secondary)"
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

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTC Alerts | Strategic Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0a0a0c;
            --surface: #121216;
            --accent: #00ffcc;
            --secondary: #7000ff;
            --text: #e0e0e6;
            --text-muted: #80808a;
            --border: #23232a;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg);
            color: var(--text);
            font-family: 'Outfit', sans-serif;
            line-height: 1.6;
            padding: 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 3rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1rem;
        }}

        h1 {{
            font-weight: 800;
            font-size: 2.5rem;
            background: linear-gradient(135deg, var(--accent), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .status {{
            text-align: right;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 4rem;
        }}

        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            transition: transform 0.2s, border-color 0.2s;
            position: relative;
            overflow: hidden;
        }}

        .card:hover {{
            transform: translateY(-4px);
            border-color: var(--secondary);
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 1rem;
        }}

        .symbol {{ font-weight: 700; font-size: 1.2rem; }}
        .timeframe {{
            background: var(--border);
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        .tier {{
            font-weight: 800;
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}

        .meta {{
            font-size: 0.9rem;
            color: var(--text-muted);
        }}

        .scorecard-section {{
            background: var(--surface);
            border-radius: 20px;
            padding: 2rem;
            border-left: 4px solid var(--accent);
        }}

        h2 {{ margin-bottom: 1.5rem; font-weight: 600; color: var(--accent); }}

        pre {{
            font-family: 'JetBrains Mono', monospace;
            white-space: pre-wrap;
            font-size: 0.9rem;
            color: var(--text-muted);
        }}

        .badge-live {{
            background: rgba(0, 255, 204, 0.1);
            color: var(--accent);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
    </style>
</head>
<body>
    <header>
        <div>
            <h1>EMBER OPS</h1>
            <p style="color: var(--text-muted)">PID-129 | Progressive Capability Interface</p>
        </div>
        <div class="status">
            <div class="badge-live">Live Feed</div>
            <p style="margin-top: 8px">Last Sync: {now}</p>
        </div>
    </header>

    <section>
        <h2>Active Signal State</h2>
        <div class="grid">
            {alerts_html if alerts_html else "<p>No active alerts tracked in state.</p>"}
        </div>
    </section>

    <section class="scorecard-section">
        <h2>Latest Daily Scorecard</h2>
        <pre>{scorecard}</pre>
    </section>

    <footer style="margin-top: 4rem; text-align: center; color: var(--text-muted); font-size: 0.8rem;">
        &copy; 2026 BTC Alerts MVP | OpenClaw Governance Framework
    </footer>
</body>
</html>
    """
    OUTPUT_PATH.write_text(html)
    print(f"Dashboard generated: {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_html()
