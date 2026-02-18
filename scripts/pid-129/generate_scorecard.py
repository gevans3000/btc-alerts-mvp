#!/usr/bin/env python3
"""
PID-129 BTC Alerts Daily Scorecard
Generates a daily summary of alerts, performance, and insights.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

# Paths
SERVICE_DIR = Path(__file__).resolve().parent.parent.parent
# Fallback to current working directory if structure is different
if not (SERVICE_DIR / "logs").exists():
    SERVICE_DIR = Path.cwd()
LOGS_DIR = SERVICE_DIR / "logs"
ALERTS_FILE = LOGS_DIR / "pid-129-alerts.jsonl"
AUDIT_FILE = LOGS_DIR / "audit.jsonl"
REPORTS_DIR = SERVICE_DIR / "reports"
OUTPUT_FILE = REPORTS_DIR / "pid-129-daily-scorecard.md"

def load_alerts(days=1):
    """Load alerts from JSONL file."""
    alerts = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    if not ALERTS_FILE.exists():
        return alerts

    with open(ALERTS_FILE, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    alert = json.loads(line)
                    # Parse timestamp if present
                    if 'timestamp' in alert:
                        alert['parsed_time'] = datetime.fromisoformat(alert['timestamp'].replace('Z', '+00:00'))
                    else:
                        alert['parsed_time'] = datetime.now(timezone.utc)

                    if alert['parsed_time'] >= cutoff:
                        alerts.append(alert)
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"Warning: Failed to parse alert: {e}", file=sys.stderr)

    # Sort by time
    alerts.sort(key=lambda x: x.get('parsed_time', datetime.now(timezone.utc)))
    return alerts

def load_audit(hours=24):
    """Load audit heartbeats."""
    audit = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    if not AUDIT_FILE.exists():
        return audit
    with open(AUDIT_FILE, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                    if ts >= cutoff:
                        audit.append(entry)
                except:
                    continue
    return audit

def generate_scorecard():
    """Generate daily scorecard report."""
    alerts = load_alerts(days=7) # Increase to 7 days for better stats
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Initialize counters
    stats = {
        'total_alerts': len(alerts),
        'long_alerts': 0,
        'short_alerts': 0,
        'resolved_trades': 0,
        'wins': 0,
        'losses': 0,
        'timeouts': 0,
        'total_r': 0.0,
        'high_confidence': 0,
    }

    strategies = defaultdict(int)
    resolved_outcomes = defaultdict(int)

    for alert in alerts:
        # Count by direction
        direction = alert.get('direction', 'NEUTRAL')
        if direction == 'LONG':
            stats['long_alerts'] += 1
        elif direction == 'SHORT':
            stats['short_alerts'] += 1

        # Count confidence
        confidence = alert.get('confidence', 0)
        if confidence >= 70:
            stats['high_confidence'] += 1

        # Count strategies
        strategy = alert.get('strategy', 'UNKNOWN')
        strategies[strategy] += 1

        # Outcome tracking
        if alert.get('resolved'):
            stats['resolved_trades'] += 1
            outcome = alert.get('outcome')
            resolved_outcomes[outcome] += 1
            if outcome and 'WIN' in outcome:
                stats['wins'] += 1
            elif outcome == 'LOSS':
                stats['losses'] += 1
            elif outcome == 'TIMEOUT':
                stats['timeouts'] += 1
            
            stats['total_r'] += alert.get('r_multiple', 0.0)

    # Calculate metrics
    win_rate = (stats['wins'] / stats['resolved_trades'] * 100) if stats['resolved_trades'] > 0 else 0.0
    avg_r = (stats['total_r'] / stats['resolved_trades']) if stats['resolved_trades'] > 0 else 0.0

    # Generate report
    report = f"""# PID-129 BTC Alerts Performance Scorecard

**Generated:** {today}

## Signal Summary (Last 7 Days)

- **Total Alerts:** {stats['total_alerts']}
- **Directional Split:** {stats['long_alerts']} LONG / {stats['short_alerts']} SHORT
- **High Confidence (>=70):** {stats['high_confidence']}

## Trading Performance (Paper)

- **Resolved Trades:** {stats['resolved_trades']}
- **Win Rate:** {win_rate:.1f}%
- **Total P&L (R):** {stats['total_r']:.2f}R
- **Average R per Trade:** {avg_r:.2f}R
- **Outcomes:** {dict(resolved_outcomes)}

## Strategy Breakdown

"""
    for strategy, count in sorted(strategies.items(), key=lambda x: x[1], reverse=True):
        report += f"- **{strategy}**: {count} alerts\n"

    report += "\n## Recent Alerts (Last 10)\n\n"
    report += "| Time | Direction | Strategy | Confidence | Outcome |\n"
    report += "|:---|:---|:---|:---|:---|\n"
    for alert in alerts[-10:]:
        ts = alert.get('timestamp', 'N/A')[:16].replace('T', ' ')
        outcome = alert.get('outcome') or 'PENDING'
        report += f"| {ts} | {alert.get('direction')} | {alert.get('strategy')} | {alert.get('confidence')} | {outcome} |\n"

    report += "\n## System Health (Audit Log - Last 24h)\n\n"
    audits = load_audit(24)
    if audits:
        count = len(audits)
        best_score = max([a['score'] for a in audits]) if audits else 0
        report += f"- **Cycles Completed:** {count}\n"
        report += f"- **Peak Confidence Seen:** {best_score}\n"
        report += f"- **Status:** Bot Active & Scanning\n"
    else:
        report += "- **Status:** No monitoring activity recorded in last 24h.\n"

    return report

def main():
    """Main entry point."""
    # Create reports directory if it doesn't exist
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate report
    report = generate_scorecard()

    # Write to file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"Scorecard generated: {OUTPUT_FILE}")
    print(f"Total signals: {len(load_alerts())}")
    # Print a terminal-safe version (replace unicode)
    safe_report = report.replace('≥', '>=')
    try:
        print(safe_report)
    except:
        print("Report contains characters terminal cannot display. See markdown file.")

if __name__ == "__main__":
    main()
