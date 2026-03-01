
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

# Import the module dynamically from scripts/pid-129
import importlib.util
spec = importlib.util.spec_from_file_location("dashboard_server", "scripts/pid-129/dashboard_server.py")
dashboard_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard_server)

import json
data = dashboard_server.get_dashboard_data()
with open("test_payload.json", "w") as f:
    json.dump({
        "flows": data.get("flows"),
        "derivatives": data.get("derivatives")
    }, f, indent=2)
