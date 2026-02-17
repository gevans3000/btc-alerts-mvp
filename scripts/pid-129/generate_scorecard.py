#!/usr/bin/env python3
"""
PID-129 BTC Alerts Daily Scorecard
Generates a daily summary of alerts, performance, and insights.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Paths
SERVICE_DIR = Path("/Users/superg/btc-alerts-mvp")
LOGS_DIR = SERVICE_DIR / "logs"
ALERTS_FILE = LOGS_DIR / "pid-129-alerts.jsonl"
REPORTS_DIR = SERVICE_DIR / "reports"
OUTPUT_FILE = REPORTS_DIR / "pid-129-daily-scorecard.md"

def load_alerts(days=1):
    """Load alerts from JSONL file."""
    alerts = []
    cutoff = datetime.utcnow() - timedelta(days=days)

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
                        alert['parsed_time'] = datetime.utcnow()

                    if alert['parsed_time'] >= cutoff:
                        alerts.append(alert)
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"Warning: Failed to parse alert: {e}", file=sys.stderr)

    # Sort by time
    alerts.sort(key=lambda x: x.get('parsed_time', datetime.utcnow()))
    return alerts

def generate_scorecard():
    """Generate daily scorecard report."""
    alerts = load_alerts(days=1)
    today = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Initialize counters
    stats = {
        'total_alerts': len(alerts),
        'long_alerts': 0,
        'short_alerts': 0,
        'no_trade_alerts': 0,
        'high_confidence': 0,
        'medium_confidence': 0,
        'low_confidence': 0,
        'failed_telegram': 0,
    }

    reasons = defaultdict(int)
    strategies = defaultdict(int)

    for alert in alerts:
        # Count by type
        if alert.get('bias') == 'LONG':
            stats['long_alerts'] += 1
        elif alert.get('bias') == 'SHORT':
            stats['short_alerts'] += 1
        elif alert.get('bias') == 'NO-TRADE':
            stats['no_trade_alerts'] += 1

        # Count confidence
        confidence = alert.get('confidence', 0)
        if confidence >= 70:
            stats['high_confidence'] += 1
        elif confidence >= 50:
            stats['medium_confidence'] += 1
        else:
            stats['low_confidence'] += 1

        # Count failed Telegram sends
        if alert.get('telegram_failed'):
            stats['failed_telegram'] += 1

        # Count reasons
        reason = alert.get('reason', 'UNKNOWN')
        if reason:
            reasons[reason] += 1

        # Count strategies
        strategy = alert.get('strategy', 'UNKNOWN')
        strategies[strategy] += 1

    # Calculate hit rate if we had TP tracking
    # For now, estimate based on confluence count
    # (would need proper TP tracking for accurate metrics)

    # Generate report
    report = f"""# PID-129 BTC Alerts Daily Scorecard

**Generated:** {today}

## Summary

- **Total Alerts (24h):** {stats['total_alerts']}
- **LONG Alerts:** {stats['long_alerts']} ({stats['long_alerts']/max(stats['total_alerts'],1)*100:.1f}%)
- **SHORT Alerts:** {stats['short_alerts']} ({stats['short_alerts']/max(stats['total_alerts'],1)*100:.1f}%)
- **NO-TRADE Alerts:** {stats['no_trade_alerts']} ({stats['no_trade_alerts']/max(stats['total_alerts'],1)*100:.1f}%)

## Confidence Distribution

- **High (≥70):** {stats['high_confidence']} ({stats['high_confidence']/max(stats['total_alerts'],1)*100:.1f}%)
- **Medium (50-69):** {stats['medium_confidence']} ({stats['medium_confidence']/max(stats['total_alerts'],1)*100:.1f}%)
- **Low (<50):** {stats['low_confidence']} ({stats['low_confidence']/max(stats['total_alerts'],1)*100:.1f}%)

## Strategy Breakdown

"""
    for strategy, count in sorted(strategies.items(), key=lambda x: x[1], reverse=True):
        report += f"- **{strategy}**: {count} alerts\n"

    report += "\n## Reason Code Breakdown\n\n"
    for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
        report += f"- **{reason}**: {count} alerts\n"

    report += "\n## Telegram Status\n\n"
    report += f"- **Successful Sends:** {stats['total_alerts'] - stats['failed_telegram']}\n"
    report += f"- **Failed Sends:** {stats['failed_telegram']}\n"

    report += "\n## Insights\n\n"
    # Initialize trend counters
    long_high = 0
    short_high = 0

    if stats['total_alerts'] > 0:
        # Check for false positive patterns
        long_high = sum(1 for a in alerts if a.get('bias') == 'LONG' and a.get('confidence', 0) >= 70)
        short_high = sum(1 for a in alerts if a.get('bias') == 'SHORT' and a.get('confidence', 0) >= 70)

        if long_high > short_high * 2:
            report += "⚠️ **Pattern Detected:** More high-confidence LONG signals than SHORT. Consider whether model bias is present.\n\n"
        elif short_high > long_high * 2:
            report += "⚠️ **Pattern Detected:** More high-confidence SHORT signals than LONG. Consider whether bearish skew is present.\n\n"

        if stats['low_confidence'] > stats['total_alerts'] * 0.4:
            report += "⚠️ **Pattern Detected:** More than 40% of alerts have low confidence. Consider adjusting threshold or improving signal quality.\n\n"

        if stats['no_trade_alerts'] / max(stats['total_alerts'], 1) > 0.5:
            report += "✅ **Pattern Detected:** High ratio of NO-TRADE signals. This may indicate healthy filtering.\n\n"

    report += "\n## Next Steps\n\n"
    if stats['low_confidence'] > 10:
        report += "- Review low-confidence alerts for common failure patterns\n"
    if stats['failed_telegram'] > 0:
        report += "- Investigate Telegram connection issues\n"
    if long_high > 0 and short_high > 0:
        report += "- Consider A/B testing different session weightings\n"

    # Append alert log excerpt (last 5 alerts)
    report += "\n## Recent Alerts (Last 5)\n\n"
    for alert in alerts[-5:]:
        timestamp = alert.get('parsed_time', datetime.utcnow()).strftime("%Y-%m-%d %H:%M")
        bias = alert.get('bias', 'UNKNOWN')
        confidence = alert.get('confidence', 0)
        strategy = alert.get('strategy', 'UNKNOWN')
        reason = alert.get('reason', 'N/A')[:60]  # Truncate long reasons

        report += f"**{timestamp}** | {bias} | {confidence} | {strategy}\n"
        report += f"  Reason: {reason}\n\n"

    return report

def main():
    """Main entry point."""
    # Create reports directory if it doesn't exist
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate report
    report = generate_scorecard()

    # Write to file
    with open(OUTPUT_FILE, 'w') as f:
        f.write(report)

    print(f"Scorecard generated: {OUTPUT_FILE}")
    print(f"Total alerts: {len(json.loads(load_alerts().__str__()))}")  # Simplified
    print(report)

if __name__ == "__main__":
    main()
