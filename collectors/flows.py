from dataclasses import dataclass, field
from typing import Dict

from collectors.base import BudgetManager, request_json


@dataclass
class FlowSnapshot:
    taker_ratio: float
    long_short_ratio: float
    crowding_score: float
    healthy: bool = True
    source: str = "none"
    meta: Dict[str, str] = field(default_factory=dict)


def _fetch_bybit_flow(timeout: float) -> FlowSnapshot:
    payload = request_json(
        "https://api.bybit.com/v5/market/account-ratio",
        params={"category": "linear", "symbol": "BTCUSDT", "period": "5min", "limit": 2},
        timeout=timeout,
    )
    rows = payload.get("result", {}).get("list", [])
    if not rows:
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="bybit", meta={"provider": "bybit"})

    row = rows[0]
    buy_ratio = float(row.get("buyRatio", 0.5))
    sell_ratio = float(row.get("sellRatio", 0.5))
    long_ratio = float(row.get("longAccount", 0.5))
    short_ratio = float(row.get("shortAccount", 0.5))
    taker_ratio = buy_ratio / max(sell_ratio, 1e-6)
    ls_ratio = long_ratio / max(short_ratio, 1e-6)
    crowding = (taker_ratio - 1.0) * 12 + (ls_ratio - 1.0) * 10
    return FlowSnapshot(taker_ratio, ls_ratio, crowding, healthy=True, source="bybit", meta={"provider": "bybit"})


def _fetch_bybit_flow(timeout: float) -> FlowSnapshot:
    resp = httpx.get(
        "https://api.bybit.com/v5/market/account-ratio",
        params={"category": "linear", "symbol": "BTCUSDT", "period": "5min", "limit": 2},
        timeout=timeout,
    )
    resp.raise_for_status()
    rows = resp.json().get("result", {}).get("list", [])
    if not rows:
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False)

    row = rows[0]
    buy_ratio = float(row.get("buyRatio", 0.5))
    sell_ratio = float(row.get("sellRatio", 0.5))
    long_ratio = float(row.get("longAccount", 0.5))
    short_ratio = float(row.get("shortAccount", 0.5))
    taker_ratio = buy_ratio / max(sell_ratio, 1e-6)
    ls_ratio = long_ratio / max(short_ratio, 1e-6)
    crowding = (taker_ratio - 1.0) * 12 + (ls_ratio - 1.0) * 10
    return FlowSnapshot(taker_ratio, ls_ratio, crowding, healthy=True)


def fetch_flow_context(budget: BudgetManager, timeout: float = 10.0) -> FlowSnapshot:
    if not budget.can_call("bybit"):
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="none", meta={"provider": "none"})
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False)

    try:
        budget.record_call("bybit")
        return _fetch_bybit_flow(timeout)
    except Exception:
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="bybit", meta={"provider": "bybit"})
