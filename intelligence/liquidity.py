"""Liquidity wall detection from order book snapshots."""
from typing import Dict, Any
from collectors.orderbook import OrderBookSnapshot, _detect_walls
from config import LIQUIDITY
import logging
logger = logging.getLogger(__name__)

def analyze_liquidity(orderbook: OrderBookSnapshot) -> Dict[str, Any]:
    if not orderbook or not orderbook.healthy:
        return {"bid_walls": 0, "ask_walls": 0, "pts": 0, "support": False, "resistance": False}
    bid_walls = _detect_walls(orderbook, "bids", LIQUIDITY["depth_pct"], LIQUIDITY["wall_threshold_btc"])
    ask_walls = _detect_walls(orderbook, "asks", LIQUIDITY["depth_pct"], LIQUIDITY["wall_threshold_btc"])
    pts = 0
    support, resistance = len(bid_walls) > 0, len(ask_walls) > 0
    if support: pts += LIQUIDITY["support_wall_pts"]
    if resistance: pts += LIQUIDITY["resistance_wall_pts"]
    return {"bid_walls": len(bid_walls), "ask_walls": len(ask_walls), "pts": pts, "support": support, "resistance": resistance}
