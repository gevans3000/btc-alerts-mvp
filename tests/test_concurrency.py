import json
import threading
import time
import os
import pytest
from pathlib import Path
from tools.paper_trader import Portfolio
import tempfile

def test_portfolio_save_concurrency():
    with tempfile.TemporaryDirectory() as temp_dir:
        portfolio_file = Path(temp_dir) / "concurrent_portfolio.json"
        
        # Initialize portfolio
        p = Portfolio(path=str(portfolio_file))
        p.balance = 10000.0
        p.save()
        
        def worker(worker_id, increment):
            # Create a new portfolio instance per thread to simulate concurrent processes
            p_worker = Portfolio(path=str(portfolio_file))
            for _ in range(10):
                p_worker.balance += increment
                p_worker.save()
                time.sleep(0.01)
                
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i, 10))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        # Check if file is still valid JSON
        assert portfolio_file.exists()
        try:
            data = json.loads(portfolio_file.read_text())
            assert "balance" in data
            assert isinstance(data["balance"], (int, float))
        except json.JSONDecodeError:
            pytest.fail("Portfolio file corrupted by concurrent writes")
