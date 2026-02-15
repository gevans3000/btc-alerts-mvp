from dataclasses import dataclass, field
from typing import Dict

from collectors.base import BudgetManager, request_json


@dataclass
class DerivativesSnapshot:
    funding_rate: float
    oi_change_pct: float
    basis_pct: float
    source: str = "none"
    healthy: bool = True
    meta: Dict[str, str] = field(default_factory=dict)


def _safe_pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return ((new - old) / abs(old)) * 100.0


def _fetch_bybit(timeout: float) -> DerivativesSnapshot:
    ticker_payload = request_json(
        "https://api.bybit.com/v5/market/tickers",
        params={"category": "linear", "symbol": "BTCUSDT"},
        timeout=timeout,
    )
    ticker_rows = ticker_payload.get("result", {}).get("list", [])
    if not ticker_rows:
        return DerivativesSnapshot(0.0, 0.0, 0.0, source="bybit", healthy=False, meta={"provider": "bybit"})

    row = ticker_rows[0]
    mark = float(row.get("markPrice", 0.0))
    index = float(row.get("indexPrice", 0.0))
    basis_pct = ((mark - index) / index) * 100.0 if index else 0.0

    oi_payload = request_json(
        "https://api.bybit.com/v5/market/open-interest",
        params={"category": "linear", "symbol": "BTCUSDT", "intervalTime": "5min", "limit": 2},
        timeout=timeout,
    )
    oi_rows = oi_payload.get("result", {}).get("list", [])
    if len(oi_rows) < 2:
        return DerivativesSnapshot(float(row.get("fundingRate", 0.0)), 0.0, basis_pct, source="bybit", healthy=True, meta={"provider": "bybit"})

    old_oi = float(oi_rows[-1].get("openInterest", 0.0))
    new_oi = float(oi_rows[0].get("openInterest", 0.0))
    return DerivativesSnapshot(
        funding_rate=float(row.get("fundingRate", 0.0)),
        oi_change_pct=_safe_pct_change(old_oi, new_oi),
        basis_pct=basis_pct,
        source="bybit",
        healthy=True,
        meta={"provider": "bybit"},
    )


def _fetch_okx(timeout: float) -> DerivativesSnapshot:
    ticker_payload = request_json(
        "https://www.okx.com/api/v5/market/ticker",
        params={"instId": "BTC-USDT-SWAP"},
        timeout=timeout,
    )
    rows = ticker_payload.get("data", [])
    if not rows:
        return DerivativesSnapshot(0.0, 0.0, 0.0, source="okx", healthy=False, meta={"provider": "okx"})

    row = rows[0]
    mark = float(row.get("last", 0.0))
    index_payload = request_json(
        "https://www.okx.com/api/v5/market/index-tickers",
        params={"instId": "BTC-USDT"},
        timeout=timeout,
    )
    idx_rows = index_payload.get("data", [])
    index = float(idx_rows[0].get("idxPx", 0.0)) if idx_rows else 0.0

    oi_payload = request_json(
        "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history",
        params={"ccy": "BTC", "period": "5m", "limit": 2},
        timeout=timeout,
    )
    oi_rows = oi_payload.get("data", [])
    if len(oi_rows) < 2:
        return DerivativesSnapshot(0.0, 0.0, ((mark - index) / index) * 100.0 if index else 0.0, source="okx", healthy=True, meta={"provider": "okx"})

    old_oi = float(oi_rows[-1][1])
    new_oi = float(oi_rows[0][1])
    basis_pct = ((mark - index) / index) * 100.0 if index else 0.0
    return DerivativesSnapshot(0.0, _safe_pct_change(old_oi, new_oi), basis_pct, source="okx", healthy=True, meta={"provider": "okx"})


def fetch_derivatives_context(budget: BudgetManager, timeout: float = 10.0) -> DerivativesSnapshot:
    if budget.can_call("bybit"):
        try:
            budget.record_call("bybit")
            return _fetch_bybit(timeout)
        except Exception:
            pass

    if budget.can_call("okx"):
        try:
            budget.record_call("okx")
            return _fetch_okx(timeout)
        except Exception:
            pass

    return DerivativesSnapshot(0.0, 0.0, 0.0, source="none", healthy=False, meta={"provider": "none"})
