import json
import pytest
import sys
from pathlib import Path

# Add the hyphenated directory to sys.path
scripts_dir = Path(__file__).parent.parent / "scripts" / "pid-129"
sys.path.append(str(scripts_dir))

# Now we can import the module as a top-level module
import dashboard_server as ds
_load_alerts = ds._load_alerts
ALERTS_PATH = ds.ALERTS_PATH

import tempfile

def test_load_alerts_filtering_and_ordering():
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mock alerts path for testing
        mock_alerts_file = Path(temp_dir) / "test_alerts.jsonl"
        
        # Create test alerts
        alerts = [
            # A valid alert
            {"symbol": "BTC", "timeframe": "5m", "strategy": "VOL_EXPANSION", "direction": "LONG", "confidence": 85, "timestamp": "2025-03-01T12:00:00Z"},
            # An alert to be filtered (SPX)
            {"symbol": "SPX", "timeframe": "5m", "strategy": "TEST", "direction": "LONG", "confidence": 50, "timestamp": "2025-03-01T12:05:00Z"},
            # An alert to be filtered (SYNTHETIC)
            {"symbol": "BTC", "timeframe": "5m", "strategy": "SYNTHETIC", "direction": "SHORT", "confidence": 40, "timestamp": "2025-03-01T12:10:00Z"},
            # Another valid alert
            {"symbol": "BTC", "timeframe": "15m", "strategy": "HTF_REVERSAL", "direction": "SHORT", "confidence": 75, "timestamp": "2025-03-01T12:15:00Z"},
        ]
        
        with open(mock_alerts_file, "w") as f:
            for a in alerts:
                f.write(json.dumps(a) + "\n")
                
        # Hijack the ALERTS_PATH global in dashboard_server
        original_path = ds.ALERTS_PATH
        ds.ALERTS_PATH = mock_alerts_file
        
        try:
            loaded = _load_alerts(limit=50)
            
            # Should have 2 valid alerts (BTC 5m and BTC 15m)
            assert len(loaded) == 2
            assert all(a["symbol"] == "BTC" for a in loaded)
            assert all(a["strategy"] not in ("TEST", "SYNTHETIC") for a in loaded)
            
            # Check ordering (should be same as input if not explicitly sorted in _load_alerts)
            # _load_alerts appends in order of file, so loaded[0] is the first one.
            assert loaded[0]["timeframe"] == "5m"
            assert loaded[1]["timeframe"] == "15m"
            
        finally:
            ds.ALERTS_PATH = original_path

def test_load_alerts_empty_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        mock_alerts_file = Path(temp_dir) / "empty.jsonl"
        mock_alerts_file.touch()
        
        original_path = ds.ALERTS_PATH
        ds.ALERTS_PATH = mock_alerts_file
        
        try:
            loaded = _load_alerts(limit=50)
            assert loaded == []
        finally:
            ds.ALERTS_PATH = original_path
