import logging
from dataclasses import dataclass

import httpx

from collectors.base import BudgetManager


@dataclass
class DerivativesSnapshot:
    funding_rate: float
    oi_change_pct: float
    basis_pct: float
    healthy: bool = True


def fetch_derivatives_context(budget: BudgetManager, timeout: float = 10.0) -> DerivativesSnapshot:
    if not budget.can_call("binance"):
        return DerivativesSnapshot(0.0, 0.0, 0.0, healthy=False)
    try:
        budget.record_call("binance")
        premium = httpx.get(
            "https://fapi.binance.com/fapi/v1/premiumIndex",
            params={"symbol": "BTCUSDT"},
            timeout=timeout,
        )
        premium.raise_for_status()
        premium_data = premium.json()

        spot = httpx.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=timeout,
        )
        spot.raise_for_status()
        spot_price = float(spot.json()["price"])

        oi = httpx.get(
            "https://fapi.binance.com/fapi/v1/openInterestHist",
            params={"symbol": "BTCUSDT", "period": "5m", "limit": 2},
            timeout=timeout,
        )
        oi.raise_for_status()
        oi_data = oi.json()

        funding_rate = float(premium_data.get("lastFundingRate", 0.0))
        mark_price = float(premium_data.get("markPrice", spot_price))
        basis_pct = ((mark_price - spot_price) / spot_price) * 100 if spot_price else 0.0

        oi_change_pct = 0.0
        if len(oi_data) >= 2:
            prev_oi = float(oi_data[0]["sumOpenInterest"])
            last_oi = float(oi_data[1]["sumOpenInterest"])
            if prev_oi > 0:
                oi_change_pct = ((last_oi - prev_oi) / prev_oi) * 100

        return DerivativesSnapshot(funding_rate, oi_change_pct, basis_pct, healthy=True)
    except Exception as exc:
        logging.error(f"Derivatives fetch failed: {exc}")
        return DerivativesSnapshot(0.0, 0.0, 0.0, healthy=False)
