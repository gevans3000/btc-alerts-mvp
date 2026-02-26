import logging
from dataclasses import dataclass, field
from typing import Dict

from collectors.base import BudgetManager, request_json

logger = logging.getLogger(__name__)


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


def _fetch_bybit(budget: BudgetManager, timeout: float) -> DerivativesSnapshot:
    budget.record_call("bybit")
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

    budget.record_call("bybit")
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


def _fetch_okx(budget: BudgetManager, timeout: float) -> DerivativesSnapshot:
    budget.record_call("okx")
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

    budget.record_call("okx")
    index_payload = request_json(
        "https://www.okx.com/api/v5/market/index-tickers",
        params={"instId": "BTC-USDT"},
        timeout=timeout,
    )
    idx_rows = index_payload.get("data", [])
    index = float(idx_rows[0].get("idxPx", 0.0)) if idx_rows else 0.0

    # Fetch REAL funding rate from OKX
    funding_rate = 0.0
    try:
        budget.record_call("okx")
        fr_payload = request_json(
            "https://www.okx.com/api/v5/public/funding-rate",
            params={"instId": "BTC-USDT-SWAP"},
            timeout=timeout,
        )
        fr_rows = fr_payload.get("data", [])
        if fr_rows:
            funding_rate = float(fr_rows[0].get("fundingRate", 0.0))
    except Exception:
        pass

    budget.record_call("okx")
    oi_payload = request_json(
        "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history",
        params={"instId": "BTC-USDT-SWAP", "period": "5m", "limit": 2},
        timeout=timeout,
    )
    oi_rows = oi_payload.get("data", [])
    basis_pct = ((mark - index) / index) * 100.0 if index else 0.0

    if len(oi_rows) < 2:
        return DerivativesSnapshot(funding_rate, 0.0, basis_pct, source="okx", healthy=True, meta={"provider": "okx"})

    old_oi = float(oi_rows[-1][1])
    new_oi = float(oi_rows[0][1])
    return DerivativesSnapshot(funding_rate, _safe_pct_change(old_oi, new_oi), basis_pct, source="okx", healthy=True, meta={"provider": "okx"})


def _fetch_bitunix(budget: BudgetManager, timeout: float) -> DerivativesSnapshot:
    """Bitunix futures API — provides mark price for basis estimate."""
    budget.record_call("bitunix")
    payload = request_json(
        "https://fapi.bitunix.com/api/v1/futures/market/tickers",
        params={"symbols": "BTCUSDT"},
        timeout=timeout,
    )
    if payload.get("code") != 0 or not payload.get("data"):
        return DerivativesSnapshot(0.0, 0.0, 0.0, source="bitunix", healthy=False, meta={"provider": "bitunix"})

    row = payload["data"][0]
    mark = float(row.get("markPrice", 0.0))
    last = float(row.get("last", row.get("lastPrice", 0.0)))
    # Bitunix doesn't expose index price separately; use mark vs last as a basis proxy
    basis_pct = ((mark - last) / last) * 100.0 if last else 0.0

    # Bitunix public API doesn't provide funding rate or OI history without auth
    return DerivativesSnapshot(
        funding_rate=0.0,
        oi_change_pct=0.0,
        basis_pct=basis_pct,
        source="bitunix",
        healthy=True,
        meta={"provider": "bitunix"},
    )


def fetch_derivatives_context(budget: BudgetManager, timeout: float = 10.0) -> DerivativesSnapshot:
    """Provider chain: Bybit → OKX → Bitunix → unhealthy fallback."""
    providers = [
        ("bybit", lambda: _fetch_bybit(budget, timeout)),
        ("okx", lambda: _fetch_okx(budget, timeout)),
        ("bitunix", lambda: _fetch_bitunix(budget, timeout)),
    ]
    for name, fetcher in providers:
        if not budget.can_call(name):
            continue
        try:
            result = fetcher()
            if result.healthy:
                return result
        except Exception as e:
            logger.warning(f"Derivatives provider {name} failed: {e}")
            if "403" in str(e):
                budget.mark_source_broken(name)
            continue

    return DerivativesSnapshot(0.0, 0.0, 0.0, source="none", healthy=False, meta={"provider": "none"})
