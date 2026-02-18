from typing import List, Dict, Any
from collectors.orderbook import OrderBookSnapshot, _detect_walls
from config import LIQUIDITY

def analyze_liquidity(
    orderbook: OrderBookSnapshot,
) -> Dict[str, Any]:
    """
    Analyzes order book liquidity, detects walls, and calculates imbalance.
    Returns a dictionary with liquidity insights.
    """
    if not orderbook.healthy:
        return {"healthy": False, "imbalance": 0.0, "bid_walls": [], "ask_walls": [], "pts": 0.0}

    total_bid_volume = sum([amount for price, amount in orderbook.bids])
    total_ask_volume = sum([amount for price, amount in orderbook.asks])

    imbalance = 0.0
    if (total_bid_volume + total_ask_volume) > 0:
        imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume)
    
    # Detect walls
    bid_walls = _detect_walls(
        orderbook, 
        side="bids", 
        depth_pct=LIQUIDITY["depth_pct"],
        wall_threshold_btc=LIQUIDITY["wall_threshold_btc"]
    )
    ask_walls = _detect_walls(
        orderbook, 
        side="asks", 
        depth_pct=LIQUIDITY["depth_pct"],
        wall_threshold_btc=LIQUIDITY["wall_threshold_btc"]
    )

    # Assign points based on liquidity analysis
    pts = 0.0
    if abs(imbalance) > LIQUIDITY["imbalance_threshold"]:
        pts += LIQUIDITY["imbalance_bonus_pts"] * (1 if imbalance > 0 else -1)
    
    if bid_walls and not ask_walls:
        pts += LIQUIDITY["wall_bonus_pts"] # Strong bid wall, no ask walls: bullish
    elif ask_walls and not bid_walls:
        pts -= LIQUIDITY["wall_bonus_pts"] # Strong ask wall, no bid walls: bearish
    elif bid_walls and ask_walls:
        pts -= LIQUIDITY["wall_penalty_pts"] # Walls on both sides: indecision/chop

    return {
        "healthy": True,
        "imbalance": round(imbalance, 3),
        "bid_walls": bid_walls,
        "ask_walls": ask_walls,
        "pts": pts
    }
