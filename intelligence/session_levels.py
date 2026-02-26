"""Session levels: PDH/PDL, session high/low, sweep detection."""
from datetime import datetime, timezone
from typing import List, Dict, Any
from utils import Candle
import logging

logger = logging.getLogger(__name__)


def _candle_dt(c: Candle) -> datetime:
    return datetime.fromtimestamp(int(float(c.ts)), tz=timezone.utc)


def _session_of(dt: datetime) -> str:
    h = dt.hour
    if 0 <= h < 8:
        return "asia"
    elif 8 <= h < 13:
        return "london"
    else:
        return "ny"


def compute_session_levels(candles: List[Candle]) -> Dict[str, Any]:
    """
    From candle history, compute:
     - PDH / PDL (prior day high/low)
     - Current session high/low (asia/london/ny)
     - Sweep flags (price wicked through then closed back)

    Returns dict with codes list and level values.
    """
    if len(candles) < 50:
        return {"pdh": 0, "pdl": 0, "session_high": 0, "session_low": 0, "codes": [], "pts": 0}

    now_dt = _candle_dt(candles[-1])
    today = now_dt.date()
    current_session = _session_of(now_dt)

    # Split candles by day
    prior_day_candles = []
    today_candles = []
    session_candles = []

    for c in candles:
        dt = _candle_dt(c)
        if dt.date() < today:
            prior_day_candles.append(c)
        elif dt.date() == today:
            today_candles.append(c)
            if _session_of(dt) == current_session:
                session_candles.append(c)

    # Only keep last full day for PDH/PDL
    if prior_day_candles:
        last_day = _candle_dt(prior_day_candles[-1]).date()
        prior_day_candles = [c for c in prior_day_candles if _candle_dt(c).date() == last_day]

    pdh = max((c.high for c in prior_day_candles), default=0)
    pdl = min((c.low for c in prior_day_candles), default=0)
    session_high = max((c.high for c in session_candles), default=0) if session_candles else 0
    session_low = min((c.low for c in session_candles), default=0) if session_candles else 0

    codes = []
    pts = 0.0
    last = candles[-1]

    # Sweep detection: wick through level but close back inside
    if pdh > 0 and last.high > pdh and last.close < pdh:
        codes.append("PDH_SWEEP_BEAR")
        pts -= 4.0
    if pdl > 0 and last.low < pdl and last.close > pdl:
        codes.append("PDL_SWEEP_BULL")
        pts += 4.0
    # Reclaim: close above PDH or below PDL
    if pdh > 0 and last.close > pdh:
        codes.append("PDH_RECLAIM_BULL")
        pts += 3.0
    if pdl > 0 and last.close < pdl:
        codes.append("PDL_BREAK_BEAR")
        pts -= 3.0

    # -- Phase 19: proximity codes for Levels probe --
    last_price = candles[-1].close
    proximity_pct = 0.003  # 0.3% = roughly $200 on BTC

    if pdl > 0 and last_price > 0:
        if last_price < pdl:
            if "PDL_BREAK_BEAR" not in codes:
                codes.append("PDL_BREAK_BEAR")
        elif abs(last_price - pdl) / last_price <= proximity_pct:
            if "PDL_SWEEP_BULL" not in codes:
                codes.append("PDL_SWEEP_BULL")
                pts += 2.0

    if pdh > 0 and last_price > 0:
        if last_price > pdh:
            if "PDH_RECLAIM_BULL" not in codes:
                codes.append("PDH_RECLAIM_BULL")
        elif abs(last_price - pdh) / last_price <= proximity_pct:
            if "PDH_SWEEP_BEAR" not in codes:
                codes.append("PDH_SWEEP_BEAR")
                pts -= 1.0

    # Session level sweep
    if session_high > 0 and last.high > session_high and last.close < session_high and len(session_candles) > 5:
        codes.append("SESSION_HIGH_SWEEP")
        pts -= 2.0
    if session_low > 0 and last.low < session_low and last.close > session_low and len(session_candles) > 5:
        codes.append("SESSION_LOW_SWEEP")
        pts += 2.0

    return {
        "pdh": round(pdh, 2), "pdl": round(pdl, 2),
        "session_high": round(session_high, 2), "session_low": round(session_low, 2),
        "session": current_session,
        "codes": codes, "pts": pts,
    }
