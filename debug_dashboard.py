
import sys
from pathlib import Path
BASE_DIR = Path("c:/Users/lovel/trading/btc-alerts-mvp")
sys.path.append(str(BASE_DIR))
sys.path.append(str(BASE_DIR / "scripts" / "pid-129"))

import dashboard_server
dashboard_server.BASE_DIR = BASE_DIR
dashboard_server.ALERTS_PATH = BASE_DIR / "logs" / "pid-129-alerts.jsonl"
dashboard_server.PORTFOLIO_PATH = BASE_DIR / "data" / "paper_portfolio.json"

try:
    data = dashboard_server.get_dashboard_data()
    import json
    # Print keys to verify
    print(f"Data keys: {list(data.keys())}")
    if "flows" in data:
        print(f"Flows: {data['flows']}")
    if "derivatives" in data:
        print(f"Derivatives: {data['derivatives']}")
    if "error" in data:
        print(f"Error: {data['error']}")
except Exception as e:
    import traceback
    traceback.print_exc()
