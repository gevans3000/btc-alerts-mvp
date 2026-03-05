import json
import os
from collections import defaultdict

def generate_calibration_report():
    log_file = "logs/pid-129-alerts.jsonl"
    report_file = "reports/calibration_report.json"
    
    if not os.path.exists("reports"):
        os.makedirs("reports")

    # Bins: 0-20, 21-40, 41-60, 61-80, 81-100
    bins = [
        (0, 20),
        (21, 40),
        (41, 60),
        (61, 80),
        (81, 100)
    ]
    
    stats = {f"{b[0]}-{b[1]}": {"count": 0, "wins": 0, "total_r": 0.0} for b in bins}
    
    if not os.path.exists(log_file):
        print(f"Error: {log_file} not found.")
        return

    with open(log_file, "r") as f:
        for line in f:
            try:
                alert = json.loads(line)
                if alert.get("outcome") is None or not alert.get("resolved", False):
                    continue
                
                conf = alert.get("confidence", 0)
                r_multiple = alert.get("r_multiple", 0.0)
                
                # Find bin
                bin_key = None
                for b in bins:
                    if b[0] <= conf <= b[1]:
                        bin_key = f"{b[0]}-{b[1]}"
                        break
                
                if bin_key:
                    stats[bin_key]["count"] += 1
                    stats[bin_key]["total_r"] += r_multiple
                    if r_multiple > 0:
                        stats[bin_key]["wins"] += 1
            except (json.JSONDecodeError, KeyError):
                continue

    # Compute averages and print table
    print(f"{'Bin':<10} | {'Count':<6} | {'Win Rate':<10} | {'Avg R':<10} | {'Total R':<10}")
    print("-" * 55)
    
    report_data = {}
    for bin_key in stats:
        s = stats[bin_key]
        count = s["count"]
        win_rate = (s["wins"] / count * 100) if count > 0 else 0.0
        avg_r = (s["total_r"] / count) if count > 0 else 0.0
        total_r = s["total_r"]
        
        print(f"{bin_key:<10} | {count:<6} | {win_rate:>8.1f}% | {avg_r:>8.2f}R | {total_r:>8.2f}R")
        
        report_data[bin_key] = {
            "count": count,
            "win_rate": round(win_rate, 2),
            "avg_r": round(avg_r, 3),
            "total_r": round(total_r, 3)
        }

    with open(report_file, "w") as f:
        json.dump(report_data, f, indent=2)
    print(f"\nReport saved to {report_file}")

if __name__ == "__main__":
    generate_calibration_report()
