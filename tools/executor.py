import os
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


PAPER_PORTFOLIO_PATH = Path("data/paper_portfolio.json")
EXECUTION_LOG_PATH = Path("logs/execution_log.jsonl")
DISABLED_FLAG = Path("DISABLED")
MARKET_CACHE_PATH = Path("data/market_cache.json")


def _load_portfolio() -> dict:
    if PAPER_PORTFOLIO_PATH.exists():
        return json.loads(PAPER_PORTFOLIO_PATH.read_text(encoding="utf-8"))
    return {"peak_balance": 10000, "max_drawdown": 0, "positions": [], "closed_trades": [], "balance": 10000}


def _save_portfolio(portfolio: dict) -> None:
    PAPER_PORTFOLIO_PATH.write_text(json.dumps(portfolio, indent=2), encoding="utf-8")


def _load_market_cache() -> dict:
    if MARKET_CACHE_PATH.exists():
        return json.loads(MARKET_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _get_spread_pct() -> float:
    try:
        cache = _load_market_cache()
        if cache and "orderbook" in cache:
            ob = cache["orderbook"]
            bid = ob.get("bids", [0])[0]
            ask = ob.get("asks", [0])[0]
            if bid and ask:
                return (ask - bid) / ask
    except Exception:
        pass
    return 0.0


def _execution_micro_mode() -> str:
    """
    Real micro-spread defense mode from cached orderbook:
    FAST | DEFENSIVE | BLOCKED
    """
    try:
        cache = _load_market_cache()
        ob = cache.get("orderbook", {}) if isinstance(cache, dict) else {}
        bids = ob.get("bids", []) if isinstance(ob, dict) else []
        asks = ob.get("asks", []) if isinstance(ob, dict) else []
        if not bids or not asks:
            return "BLOCKED"
        bid = float(bids[0][0])
        ask = float(asks[0][0])
        bid_sz = float(bids[0][1]) if len(bids[0]) > 1 else 0.0
        ask_sz = float(asks[0][1]) if len(asks[0]) > 1 else 0.0
        if bid <= 0 or ask <= 0 or ask < bid:
            return "BLOCKED"
        mid = (ask + bid) / 2.0
        spread_bps = ((ask - bid) / mid) * 10000.0 if mid > 0 else 999.0
        top_depth_usd = (bid * max(0.0, bid_sz)) + (ask * max(0.0, ask_sz))
        impact_bps_5k = (5000.0 / max(top_depth_usd, 1.0)) * 10000.0
        if spread_bps > 3.0 or impact_bps_5k > 80.0:
            return "BLOCKED"
        if spread_bps > 1.5 or impact_bps_5k > 35.0:
            return "DEFENSIVE"
        return "FAST"
    except Exception:
        return "BLOCKED"


def _system_disabled() -> bool:
    return DISABLED_FLAG.exists()


def _log_execution(record: dict) -> None:
    EXECUTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXECUTION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def execute_trade(alert: dict, mode: str = "PAPER") -> dict:
    """
    Takes a full alert dict from engine.py output.
    Returns: {"status": "FILLED"|"REJECTED"|"PAPER", "order_id": str, "fill_price": float, "reason": str}
    """
    direction = alert.get("direction")
    entry_price = alert.get("entry_price") or alert.get("price")
    invalidation = alert.get("invalidation")
    tp1 = alert.get("tp1")
    confidence = alert.get("confidence", 0)
    tier = alert.get("tier")
    timeframe = alert.get("timeframe", "unknown")
    
    if tier != "A+":
        return {"status": "REJECTED", "reason": "not A+", "order_id": "", "fill_price": 0.0}
    
    if _system_disabled():
        return {"status": "REJECTED", "reason": "operator off", "order_id": "", "fill_price": 0.0}
    
    portfolio = _load_portfolio()
    kelly_pct = portfolio.get("kelly_pct", 0.10)
    
    base_usdt = 100
    if kelly_pct > 0.15:
        size = base_usdt * 1.5
    elif kelly_pct < 0.05:
        size = base_usdt * 0.5
    else:
        size = base_usdt
    
    spread_pct = _get_spread_pct()
    micro_mode = _execution_micro_mode()
    if micro_mode == "BLOCKED":
        return {"status": "REJECTED", "reason": "micro-spread defense blocked", "order_id": "", "fill_price": 0.0}
    use_limit = (micro_mode == "DEFENSIVE") or (spread_pct > 0.0015)
    
    timestamp = datetime.utcnow().isoformat()
    
    if mode == "PAPER":
        position = {
            "id": f"PAPER-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "direction": direction,
            "entry_price": entry_price,
            "invalidation": invalidation,
            "tp1": tp1,
            "size_usdt": size,
            "timeframe": timeframe,
            "confidence": confidence,
            "opened_at": timestamp,
            "status": "open"
        }
        portfolio["positions"].append(position)
        _save_portfolio(portfolio)
        
        _log_execution({
            "timestamp": timestamp,
            "mode": "PAPER",
            "alert_id": alert.get("id", ""),
            "direction": direction,
            "status": "PAPER",
            "size_usdt": size,
            "entry_price": entry_price,
            "reason": "paper filled"
        })
        
        return {"status": "PAPER", "order_id": position["id"], "fill_price": entry_price, "reason": "paper filled"}
    
    broker = os.getenv("TRADE_BROKER", "bybit").lower()

    if broker == "bitunix":
        api_key = os.getenv("BITUNIX_API_KEY")
        api_secret = os.getenv("BITUNIX_API_SECRET")
    else:
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")

    if not api_key or not api_secret:
        return {"status": "REJECTED", "reason": f"no {broker} API keys", "order_id": "", "fill_price": 0.0}

    try:
        import ccxt
        if broker == "bitunix":
            exchange = ccxt.bitunix({
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            })
        else:
            exchange = ccxt.bybit({
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            })
        
        symbol = "BTC/USDT:USDT"
        side = "buy" if direction == "LONG" else "sell"
        
        if use_limit:
            order_price = entry_price * 0.9995 if direction == "LONG" else entry_price * 1.0005
            order = exchange.create_order(symbol, "limit", side, size, order_price, {"postOnly": True})
        else:
            order = exchange.create_order(symbol, "market", side, size)
        
        order_id = order.get("id")
        fill_price = order.get("average") or entry_price
        
        sl_price = invalidation
        tp_price = tp1
        
        sl_side = "sell" if direction == "LONG" else "buy"
        tp_side = "sell" if direction == "LONG" else "buy"
        
        try:
            exchange.create_order(symbol, "stop_market", sl_side, size, sl_price, {"reduceOnly": True})
        except Exception as e:
            _log_execution({"timestamp": timestamp, "error": f"SL order failed: {e}"})
        
        try:
            exchange.create_order(symbol, "take_market", tp_side, size, tp_price, {"reduceOnly": True})
        except Exception as e:
            _log_execution({"timestamp": timestamp, "error": f"TP order failed: {e}"})
        
        _log_execution({
            "timestamp": timestamp,
            "mode": "LIVE",
            "alert_id": alert.get("id", ""),
            "direction": direction,
            "status": "FILLED",
            "order_id": order_id,
            "size_usdt": size,
            "entry_price": fill_price,
            "reason": "live filled"
        })
        
        return {"status": "FILLED", "order_id": order_id, "fill_price": fill_price, "reason": "live filled"}
        
    except Exception as e:
        _log_execution({
            "timestamp": timestamp,
            "mode": "LIVE",
            "alert_id": alert.get("id", ""),
            "direction": direction,
            "status": "REJECTED",
            "error": str(e)
        })
        return {"status": "REJECTED", "reason": str(e), "order_id": "", "fill_price": 0.0}
