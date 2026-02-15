from dataclasses import dataclass

import httpx

from collectors.base import BudgetManager


@dataclass
class FlowSnapshot:
    taker_ratio: float
    long_short_ratio: float
    crowding_score: float
    healthy: bool = True


def fetch_flow_context(budget: BudgetManager, timeout: float = 10.0) -> FlowSnapshot:
    if not budget.can_call("binance"):
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False)

    try:
        budget.record_call("binance")
        taker_resp = httpx.get(
            "https://fapi.binance.com/futures/data/takerlongshortRatio",
            params={"symbol": "BTCUSDT", "period": "5m", "limit": 2},
            timeout=timeout,
        )
        taker_resp.raise_for_status()
        taker_rows = taker_resp.json()

        pos_resp = httpx.get(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
            params={"symbol": "BTCUSDT", "period": "5m", "limit": 2},
            timeout=timeout,
        )
        pos_resp.raise_for_status()
        pos_rows = pos_resp.json()

        if not taker_rows or not pos_rows:
            return FlowSnapshot(1.0, 1.0, 0.0, healthy=False)

        taker_ratio = float(taker_rows[-1].get("buySellRatio", 1.0))
        ls_ratio = float(pos_rows[-1].get("longShortRatio", 1.0))
        crowding = (taker_ratio - 1.0) * 12 + (ls_ratio - 1.0) * 10
        return FlowSnapshot(taker_ratio, ls_ratio, crowding, healthy=True)
    except Exception:
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False)
