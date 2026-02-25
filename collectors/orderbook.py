from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any
from datetime import datetime
import math

@dataclass
class OrderBookSnapshot:
    ts: int
    bids: List[Tuple[float, float]]  # (price, amount)
    asks: List[Tuple[float, float]] # (price, amount)
    mid_price: float = field(init=False)
    healthy: bool = True

    def __post_init__(self):
        if self.bids and self.asks:
            best_bid = self.bids[0][0]
            best_ask = self.asks[0][0]
            self.mid_price = (best_bid + best_ask) / 2
        else:
            self.mid_price = 0.0 # Or handle as error
            self.healthy = False

def fetch_orderbook(budget_manager) -> OrderBookSnapshot:
    try:
        from collectors.base import request_json
        if budget_manager:
            budget_manager.record_call("bybit_ob")
        payload = request_json(
            "https://api.bybit.com/v5/market/orderbook",
            params={"category": "linear", "symbol": "BTCUSDT", "limit": 50},
            timeout=5.0
        )
        result = payload.get("result", {})
        bids = [(float(p), float(q)) for p, q in result.get("b", [])]
        asks = [(float(p), float(q)) for p, q in result.get("a", [])]
        ts_ms = payload.get("time", int(datetime.now().timestamp() * 1000))
        return OrderBookSnapshot(ts=int(ts_ms / 1000), bids=bids, asks=asks)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Orderbook fetch failed: %s", e)
        return OrderBookSnapshot(ts=int(datetime.now().timestamp()), bids=[], asks=[], healthy=False)

def _detect_walls(
    orderbook: OrderBookSnapshot,
    side: str,
    depth_pct: float,
    wall_threshold_btc: float
) -> List[Dict[str, Any]]:
    """
    Detects significant liquidity walls in the order book.
    Returns a list of detected walls.
    """
    if not orderbook.healthy:
        return []

    walls = []
    reference_price = orderbook.mid_price

    if side == "bids":
        levels = orderbook.bids
        # Iterate from best bid downwards
        levels_to_check = [lvl for lvl in levels if lvl[0] >= reference_price * (1 - depth_pct)]
    elif side == "asks":
        levels = orderbook.asks
        # Iterate from best ask upwards
        levels_to_check = [lvl for lvl in levels if lvl[0] <= reference_price * (1 + depth_pct)]
    else:
        return []

    for price, amount in levels_to_check:
        if amount >= wall_threshold_btc:
            walls.append({"price": price, "amount": amount, "side": side})
    return walls
