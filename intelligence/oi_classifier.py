"""Price–OI relationship classifier."""
from typing import Dict, Any
from collectors.derivatives import DerivativesSnapshot
import logging

logger = logging.getLogger(__name__)


def classify_price_oi(price_change_pct: float, derivatives: DerivativesSnapshot) -> Dict[str, Any]:
    """
    Classify relationship between price change and OI change.

    4 regimes:
    - price↑ + OI↑  = NEW_LONGS (bullish continuation)
    - price↑ + OI↓  = SHORT_COVERING (weak rally, may reverse)
    - price↓ + OI↑  = NEW_SHORTS (bearish continuation)
    - price↓ + OI↓  = LONG_LIQUIDATION (capitulation, may reverse)

    Returns: {"regime": str, "codes": [], "pts": float}
    """
    if not derivatives or not derivatives.healthy:
        return {"regime": "UNKNOWN", "codes": [], "pts": 0}

    oi_pct = derivatives.oi_change_pct
    codes = []
    pts = 0.0

    # Thresholds: meaningful moves only
    price_up = price_change_pct > 0.1
    price_down = price_change_pct < -0.1
    oi_up = oi_pct > 0.3
    oi_down = oi_pct < -0.3

    if price_up and oi_up:
        regime = "NEW_LONGS"
        codes.append("OI_NEW_LONGS")
        pts = 3.0
    elif price_up and oi_down:
        regime = "SHORT_COVERING"
        codes.append("OI_SHORT_COVERING")
        pts = -1.0  # Weak rally
    elif price_down and oi_up:
        regime = "NEW_SHORTS"
        codes.append("OI_NEW_SHORTS")
        pts = -3.0
    elif price_down and oi_down:
        regime = "LONG_LIQUIDATION"
        codes.append("OI_LONG_LIQUIDATION")
        pts = 1.0  # Capitulation = potential reversal
    else:
        regime = "NEUTRAL"

    return {"regime": regime, "codes": codes, "pts": pts}
