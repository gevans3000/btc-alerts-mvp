from dataclasses import dataclass

import httpx

from collectors.base import BudgetManager


@dataclass
class DerivativesSnapshot:
    funding_rate: float
    oi_change_pct: float
    basis_pct: float
    source: str = "none"
    healthy: bool = True


def _safe_pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return ((new - old) / abs(old)) * 100.0


def _fetch_binance(timeout: float) -> DerivativesSnapshot:
    funding_resp = httpx.get(
        "https://fapi.binance.com/fapi/v1/premiumIndex",
        params={"symbol": "BTCUSDT"},
        timeout=timeout,
    )
    funding_resp.raise_for_status()
    funding_data = funding_resp.json()

    oi_resp = httpx.get(
        "https://fapi.binance.com/futures/data/openInterestHist",
        params={"symbol": "BTCUSDT", "period": "5m", "limit": 2},
        timeout=timeout,
    )
    oi_resp.raise_for_status()
    oi_rows = oi_resp.json()

    if len(oi_rows) < 2:
        return DerivativesSnapshot(0.0, 0.0, 0.0, source="binance", healthy=False)

    old_oi = float(oi_rows[0].get("sumOpenInterest", 0.0))
    new_oi = float(oi_rows[1].get("sumOpenInterest", 0.0))
    oi_change_pct = _safe_pct_change(old_oi, new_oi)

    mark = float(funding_data.get("markPrice", 0.0))
    index = float(funding_data.get("indexPrice", 0.0))
    basis_pct = ((mark - index) / index) * 100.0 if index else 0.0

    return DerivativesSnapshot(
        funding_rate=float(funding_data.get("lastFundingRate", 0.0)),
        oi_change_pct=oi_change_pct,
        basis_pct=basis_pct,
        source="binance",
        healthy=True,
    )


def _fetch_bybit(timeout: float) -> DerivativesSnapshot:
    ticker_resp = httpx.get(
        "https://api.bybit.com/v5/market/tickers",
        params={"category": "linear", "symbol": "BTCUSDT"},
        timeout=timeout,
    )
    ticker_resp.raise_for_status()
    ticker_rows = ticker_resp.json().get("result", {}).get("list", [])
    if not ticker_rows:
        return DerivativesSnapshot(0.0, 0.0, 0.0, source="bybit", healthy=False)

    row = ticker_rows[0]
    mark = float(row.get("markPrice", 0.0))
    index = float(row.get("indexPrice", 0.0))
    basis_pct = ((mark - index) / index) * 100.0 if index else 0.0

    kl_resp = httpx.get(
        "https://api.bybit.com/v5/market/open-interest",
        params={"category": "linear", "symbol": "BTCUSDT", "intervalTime": "5min", "limit": 2},
        timeout=timeout,
    )
    kl_resp.raise_for_status()
    oi_rows = kl_resp.json().get("result", {}).get("list", [])
    if len(oi_rows) < 2:
        return DerivativesSnapshot(float(row.get("fundingRate", 0.0)), 0.0, basis_pct, source="bybit", healthy=True)

    old_oi = float(oi_rows[-1].get("openInterest", 0.0))
    new_oi = float(oi_rows[0].get("openInterest", 0.0))

    return DerivativesSnapshot(
        funding_rate=float(row.get("fundingRate", 0.0)),
        oi_change_pct=_safe_pct_change(old_oi, new_oi),
        basis_pct=basis_pct,
        source="bybit",
        healthy=True,
    )


def fetch_derivatives_context(budget: BudgetManager, timeout: float = 10.0) -> DerivativesSnapshot:
    if budget.can_call("binance"):
        try:
            budget.record_call("binance")
            return _fetch_binance(timeout)
        except Exception:
            pass

    if budget.can_call("bybit"):
        try:
            budget.record_call("bybit")
            return _fetch_bybit(timeout)
        except Exception:
            pass

    return DerivativesSnapshot(0.0, 0.0, 0.0, source="none", healthy=False)
