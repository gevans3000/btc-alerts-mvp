from typing import Dict, Any, List, Tuple
from collectors.orderbook import OrderBookSnapshot

def analyze_liquidity(orderbook: OrderBookSnapshot, depth_pct: float = 0.005) -> Dict[str, Any]:
    """Analyzes order book data for liquidity walls and imbalance."""
    if not orderbook.is_healthy or not orderbook.bids or not orderbook.asks:
        return {
            "is_healthy": False,
            "message": orderbook.message or "Order book data not healthy or empty.",
            "total_bid_volume": 0.0,
            "total_ask_volume": 0.0,
            "imbalance": 0.0,
            "walls": [],
        }

    # Current price (mid-price approximation)
    best_bid = orderbook.bids[0][0]
    best_ask = orderbook.asks[0][0]
    mid_price = (best_bid + best_ask) / 2

    total_bid_volume = 0.0
    total_ask_volume = 0.0
    walls: List[Dict[str, Any]] = []

    # Analyze bids
    for price, quantity in orderbook.bids:
        if price >= mid_price * (1 - depth_pct):
            total_bid_volume += quantity
            # Simple wall detection: if quantity is significantly larger than average
            # This needs to be refined with a dynamic threshold later
            if quantity > 100: # Placeholder threshold
                walls.append({"side": "buy", "price": price, "quantity": quantity})

    # Analyze asks
    for price, quantity in orderbook.asks:
        if price <= mid_price * (1 + depth_pct):
            total_ask_volume += quantity
            # Simple wall detection
            if quantity > 100: # Placeholder threshold
                walls.append({"side": "sell", "price": price, "quantity": quantity})

    imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume) if (total_bid_volume + total_ask_volume) > 0 else 0.0

    return {
        "is_healthy": True,
        "total_bid_volume": total_bid_volume,
        "total_ask_volume": total_ask_volume,
        "imbalance": imbalance,
        "walls": walls,
        "mid_price": mid_price
    }

# Example usage (for testing purposes)
if __name__ == "__main__":
    from collectors.orderbook import OrderBookSnapshot
    import time

    # Create a mock order book snapshot
    mock_orderbook = OrderBookSnapshot(
        source="mock",
        timestamp=time.time(),
        symbol="BTC/USD",
        bids=[(99.9, 50), (99.8, 120), (99.7, 30)],
        asks=[(100.1, 70), (100.2, 150), (100.3, 40)],
        is_healthy=True
    )

    liquidity_analysis = analyze_liquidity(mock_orderbook)
    print(f"Liquidity Analysis: {liquidity_analysis}")

    mock_orderbook_unhealthy = OrderBookSnapshot(
        source="mock",
        timestamp=time.time(),
        symbol="BTC/USD",
        bids=[],
        asks=[],
        is_healthy=False,
        message="No data"
    )
    liquidity_analysis_unhealthy = analyze_liquidity(mock_orderbook_unhealthy)
    print(f"Liquidity Analysis (unhealthy): {liquidity_analysis_unhealthy}")
