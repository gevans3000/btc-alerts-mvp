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
    """Provider chain: Bybit → OKX → Bitunix → unhealthy fallback."""
    from collectors.base import request_json
    import logging
    _logger = logging.getLogger(__name__)

    # Provider 1: Bybit
    if budget_manager and budget_manager.can_call("bybit"):
        try:
            budget_manager.record_call("bybit")
            payload = request_json(
                "https://api.bybit.com/v5/market/orderbook",
                params={"category": "linear", "symbol": "BTCUSDT", "limit": 200},
                timeout=5.0
            )
            result = payload.get("result", {})
            bids = [(float(p), float(q)) for p, q in result.get("b", [])]
            asks = [(float(p), float(q)) for p, q in result.get("a", [])]
            if bids and asks:
                ts_ms = payload.get("time", int(datetime.now().timestamp() * 1000))
                return OrderBookSnapshot(ts=int(ts_ms / 1000), bids=bids, asks=asks)
        except Exception as e:
            _logger.warning("Bybit orderbook failed: %s", e)
            if "403" in str(e) and budget_manager:
                budget_manager.mark_source_broken("bybit")

    # Provider 2: OKX
    if budget_manager and budget_manager.can_call("okx"):
        try:
            budget_manager.record_call("okx")
            payload = request_json(
                "https://www.okx.com/api/v5/market/books",
                params={"instId": "BTC-USDT-SWAP", "sz": "200"},
                timeout=5.0
            )
            data_list = payload.get("data", [])
            if data_list:
                book = data_list[0]
                bids = [(float(row[0]), float(row[1])) for row in book.get("bids", [])]
                asks = [(float(row[0]), float(row[1])) for row in book.get("asks", [])]
                if bids and asks:
                    ts_ms = int(book.get("ts", datetime.now().timestamp() * 1000))
                    return OrderBookSnapshot(ts=int(ts_ms / 1000), bids=bids, asks=asks)
        except Exception as e:
            _logger.warning("OKX orderbook failed: %s", e)

    # Provider 3: Bitunix
    if budget_manager and budget_manager.can_call("bitunix"):
        try:
            budget_manager.record_call("bitunix")
            payload = request_json(
                "https://fapi.bitunix.com/api/v1/futures/market/depth",
                params={"symbol": "BTCUSDT", "limit": "50"},
                timeout=5.0
            )
            if payload.get("code") == 0 and payload.get("data"):
                data = payload["data"]
                bids = [(float(row[0]), float(row[1])) for row in data.get("bids", [])]
                asks = [(float(row[0]), float(row[1])) for row in data.get("asks", [])]
                if bids and asks:
                    return OrderBookSnapshot(ts=int(datetime.now().timestamp()), bids=bids, asks=asks)
        except Exception as e:
            _logger.warning("Bitunix orderbook failed: %s", e)

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
