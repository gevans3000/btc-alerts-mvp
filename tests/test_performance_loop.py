import json
import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone
from tools.paper_trader import Portfolio, Position
from tools.outcome_tracker import resolve_outcomes

@pytest.fixture
def temp_portfolio(tmp_path):
    path = tmp_path / "test_portfolio.json"
    return Portfolio(str(path))

def test_portfolio_on_alert(temp_portfolio):
    # Risk 100 on 10000 balance
    # Entry 60000, SL 59000 -> Diff 1000. 
    temp_portfolio.on_alert(
        "test-uuid", "BTC", "5m", "LONG", 60000.0, 59000.0, 62000.0, "TRADE"
    )
    assert len(temp_portfolio.positions) == 1
    pos = temp_portfolio.positions[0]
    assert pos.symbol == "BTC"
    # Size: units = 100 / 1000 = 0.1. Size USDT = 0.1 * 60000 = 6000.
    assert pos.size_usdt == 6000.0

def test_portfolio_update_win(temp_portfolio):
    temp_portfolio.on_alert(
        "test-uuid", "BTC", "5m", "LONG", 60000.0, 59000.0, 62000.0, "TRADE"
    )
    # Price hits TP1
    temp_portfolio.update(62000.0)
    assert len(temp_portfolio.positions) == 0
    assert len(temp_portfolio.closed_trades) == 1
    trade = temp_portfolio.closed_trades[0]
    assert trade.outcome == "WIN"
    assert trade.pnl_usdt == 200.0 # 0.1 units * (62000 - 60000)
    assert temp_portfolio.balance == 10200.0

def test_portfolio_update_loss(temp_portfolio):
    temp_portfolio.on_alert(
        "test-uuid", "BTC", "5m", "LONG", 60000.0, 59000.0, 62000.0, "TRADE"
    )
    # Price hits SL
    temp_portfolio.update(59000.0)
    assert len(temp_portfolio.positions) == 0
    trade = temp_portfolio.closed_trades[0]
    assert trade.outcome == "LOSS"
    assert trade.pnl_usdt == -100.0
    assert temp_portfolio.balance == 9900.0

def test_max_positions(temp_portfolio):
    for i in range(5):
        temp_portfolio.on_alert(
            f"uuid-{i}", "BTC", f"{i}m", "LONG", 60000.0, 59000.0, 62000.0, "TRADE"
        )
    assert len(temp_portfolio.positions) == 3 # Capped at 3
