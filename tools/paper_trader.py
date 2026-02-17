#!/usr/bin/env python3
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("paper_trader")

@dataclass
class Position:
    alert_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: float
    size_usdt: float
    sl: float
    tp1: float
    opened_at: str
    status: str = "OPEN"

@dataclass
class ClosedTrade:
    alert_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: float
    exit_price: float
    exit_at: str
    pnl_usdt: float
    r_multiple: float
    outcome: str

class Portfolio:
    def __init__(self, path: str = "data/paper_portfolio.json"):
        self.path = Path(path)
        self.balance = 10000.0
        self.positions: List[Position] = []
        self.closed_trades: List[ClosedTrade] = []
        self.peak_balance = 10000.0
        self.max_drawdown = 0.0
        self.equity_curve: List[Dict] = [{"timestamp": datetime.now(timezone.utc).isoformat(), "balance": 10000.0}]
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.balance = data.get("balance", 10000.0)
                self.positions = [Position(**p) for p in data.get("positions", [])]
                self.closed_trades = [ClosedTrade(**t) for t in data.get("closed_trades", [])]
                self.peak_balance = data.get("peak_balance", 10000.0)
                self.max_drawdown = data.get("max_drawdown", 0.0)
                self.equity_curve = data.get("equity_curve", [{"timestamp": datetime.now(timezone.utc).isoformat(), "balance": 10000.0}])
            except Exception as e:
                logger.error(f"Failed to load portfolio: {e}")

    def save(self):
        data = {
            "balance": self.balance,
            "positions": [asdict(p) for p in self.positions],
            "closed_trades": [asdict(t) for t in self.closed_trades],
            "peak_balance": self.peak_balance,
            "max_drawdown": self.max_drawdown,
            "equity_curve": self.equity_curve
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))

    def on_alert(self, alert_id: str, symbol: str, tf: str, direction: str, price: float, sl: float, tp1: float, tier: str):
        if tier != "TRADE":
            return
        
        # Risk 1% of balance
        risk_per_trade = self.balance * 0.01
        sl_dist = abs(price - sl)
        if sl_dist == 0:
            return
        
        # Basic position sizing
        # For simplicity in paper trading: position size = risk / (sl_dist / price) ? 
        # No, just risk = (entry - sl) * units. Units = risk / abs(entry - sl).
        units = risk_per_trade / sl_dist
        size_usdt = units * price
        
        # Max 3 positions
        if len(self.positions) >= 3:
            logger.info("Max concurrent positions reached. Skipping.")
            return

        # Don't double up on same symbol/direction/tf
        for p in self.positions:
            if p.symbol == symbol and p.timeframe == tf and p.direction == direction:
                logger.info(f"Existing {direction} position on {tf} for {symbol}. Skipping.")
                return

        pos = Position(
            alert_id=alert_id,
            symbol=symbol,
            timeframe=tf,
            direction=direction,
            entry_price=price,
            size_usdt=size_usdt,
            sl=sl,
            tp1=tp1,
            opened_at=datetime.now(timezone.utc).isoformat()
        )
        self.positions.append(pos)
        logger.info(f"Opened {direction} on {symbol} {tf} @ {price}. Size: ${size_usdt:.2f}")
        self.save()

    def update(self, current_price: float):
        for p in list(self.positions):
            closed = False
            outcome = ""
            exit_price = current_price
            
            risk = abs(p.entry_price - p.sl)
            
            if p.direction == "LONG":
                if current_price >= p.tp1:
                    closed = True
                    outcome = "WIN"
                    exit_price = p.tp1
                elif current_price <= p.sl:
                    closed = True
                    outcome = "LOSS"
                    exit_price = p.sl
            else: # SHORT
                if current_price <= p.tp1:
                    closed = True
                    outcome = "WIN"
                    exit_price = p.tp1
                elif current_price >= p.sl:
                    closed = True
                    outcome = "LOSS"
                    exit_price = p.sl
            
            # Timeout (Max 48h)
            opened_at = datetime.fromisoformat(p.opened_at)
            if not closed and (datetime.now(timezone.utc) - opened_at).total_seconds() > 48 * 3600:
                closed = True
                outcome = "TIMEOUT"
            
            if closed:
                units = p.size_usdt / p.entry_price
                if p.direction == "LONG":
                    pnl = (exit_price - p.entry_price) * units
                else:
                    pnl = (p.entry_price - exit_price) * units
                
                self.balance += pnl
                r_multiple = pnl / (p.size_usdt * (risk / p.entry_price)) if risk > 0 else 0
                
                ct = ClosedTrade(
                    alert_id=p.alert_id,
                    symbol=p.symbol,
                    timeframe=p.timeframe,
                    direction=p.direction,
                    entry_price=p.entry_price,
                    exit_price=exit_price,
                    exit_at=datetime.now(timezone.utc).isoformat(),
                    pnl_usdt=pnl,
                    r_multiple=round(r_multiple, 2),
                    outcome=outcome
                )
                self.closed_trades.append(ct)
                self.positions.remove(p)
                
                # Update metrics
                if self.balance > self.peak_balance:
                    self.peak_balance = self.balance
                
                dd = (self.peak_balance - self.balance) / self.peak_balance
                if dd > self.max_drawdown:
                    self.max_drawdown = dd
                
                self.equity_curve.append({
                    "timestamp": ct.exit_at,
                    "balance": self.balance
                })
                
                logger.info(f"Closed {p.direction} on {p.symbol}: {outcome} PnL: ${pnl:.2f} ({r_multiple:.2f}R)")
                self.save()

    def get_report(self):
        total_trades = len(self.closed_trades)
        wins = sum(1 for t in self.closed_trades if t.outcome == "WIN")
        losses = sum(1 for t in self.closed_trades if t.outcome == "LOSS")
        timeouts = sum(1 for t in self.closed_trades if t.outcome == "TIMEOUT")
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        total_pnl = self.balance - 10000.0
        
        return {
            "balance": round(self.balance, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / 100, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "timeouts": timeouts,
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "open_positions": len(self.positions)
        }

if __name__ == "__main__":
    portfolio = Portfolio()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            print(json.dumps(portfolio.get_report(), indent=2))
        elif cmd == "reset":
            if os.path.exists(portfolio.path):
                os.remove(portfolio.path)
            print("Portfolio reset.")
        elif cmd == "report":
            report = portfolio.get_report()
            print("======================================")
            print("        PAPER TRADING REPORT")
            print("======================================")
            for k, v in report.items():
                print(f"{k:<20}: {v}")
            print("======================================")
