from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any
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
    # Placeholder for actual API call
    # This function would interact with a real-time order book API
    # For MVP, we will return a mock snapshot
    return OrderBookSnapshot(
        ts=int(datetime.now().timestamp()),
        bids=[(100.0 - i * 0.1, 10 + i) for i in range(10)],
        asks=[(100.0 + i * 0.1, 10 + i) for i in range(10)],
    )

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
