"""Centralized tunables for alerts and collectors."""

REGIME = {
    "adx_trend": 24,
    "slope_trend": 0.003,
    "atr_rank_chop": 70,
    "adx_chop": 20,
}

DETECTORS = {
    "donchian_lookback": 20,
    "zscore_period": 20,
    "zscore_extreme": 1.8,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "volume_multiplier": 1.4,
}

TIMEFRAME_RULES = {
    "5m": {"min_rr": 1.35, "trade_long": 74, "trade_short": 26, "watch_long": 60, "watch_short": 40},
    "15m": {"min_rr": 1.25, "trade_long": 72, "trade_short": 28, "watch_long": 58, "watch_short": 42},
    "1h": {"min_rr": 1.15, "trade_long": 68, "trade_short": 32, "watch_long": 56, "watch_short": 44},
}

STALE_SECONDS = {"5m": 12 * 60, "15m": 35 * 60, "1h": 130 * 60}

COOLDOWN_SECONDS = {"A+": 10 * 60, "B": 20 * 60, "NO-TRADE": 20 * 60}

HTTP_RETRY = {"attempts": 3, "backoff_seconds": 0.35, "jitter_seconds": 0.2}


def validate_config() -> None:
    for tf, cfg in TIMEFRAME_RULES.items():
        if cfg["trade_long"] <= cfg["watch_long"]:
            raise ValueError(f"{tf}: trade_long must be > watch_long")
        if cfg["trade_short"] >= cfg["watch_short"]:
            raise ValueError(f"{tf}: trade_short must be < watch_short")
        if cfg["min_rr"] <= 0:
            raise ValueError(f"{tf}: min_rr must be > 0")
    for tf, seconds in STALE_SECONDS.items():
        if seconds <= 0:
            raise ValueError(f"{tf}: stale seconds must be > 0")
