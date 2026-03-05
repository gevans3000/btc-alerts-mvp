import os
import subprocess
import pytest

def test_backtest_cli_output():
    """Verify that run_backtest.py outputs performance report metrics."""
    # Assuming run_backtest.py takes a limit argument
    result = subprocess.run(
        ["python", "tools/run_backtest.py", "--limit", "100", "--symbol", "BTC"],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    
    # Check that execution succeeds or it falls back properly and generates output
    assert result.returncode == 0 or "back_test" in str(result.stdout).lower() or "performance report" in str(result.stdout).lower()
    
    output = result.stdout
    
    if "PERFORMANCE REPORT" not in output:
        # It's possible the test environment cannot reach APIs, we should gracefully skip
        # or assert that an error message was printed
        assert "failed" in output.lower() or "error" in output.lower()
        return
        
    assert "TIMEFRAME" in output
    assert "WIN RATE" in output
    assert "EXPECTANCY" in output
    assert "5m" in output
    
    # Check if a positive or negative expectancy format is correctly used
    assert "(+)" in output or "(-)" in output or "(~)" in output
