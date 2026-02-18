"""
Centralized tunables for alerts and collectors.
GOLDEN_BASELINE_V2 = "2026-02-17"
"""

REGIME = {
    "adx_trend": 24,
    "slope_trend": 0.003,
    "atr_rank_chop": 70,
    "adx_chop": 20,
    "adx_low": 20,
    "atr_rank_low": 30,
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

HTTP_RETRY = {"attempts": 4, "backoff_seconds": 2.0, "jitter_seconds": 1.0}

SESSION_WEIGHTS = {
    "asia": {"BREAKOUT": 0.5, "MEAN_REVERSION": 1.3, "TREND_CONTINUATION": 0.7, "VOLATILITY_EXPANSION": 0.6},
    "europe": {"BREAKOUT": 1.2, "MEAN_REVERSION": 0.9, "TREND_CONTINUATION": 1.0, "VOLATILITY_EXPANSION": 1.1},
    "us": {"BREAKOUT": 1.1, "MEAN_REVERSION": 0.8, "TREND_CONTINUATION": 1.3, "VOLATILITY_EXPANSION": 1.2},
    "weekend": {"BREAKOUT": 0.6, "MEAN_REVERSION": 1.1, "TREND_CONTINUATION": 0.7, "VOLATILITY_EXPANSION": 0.5},
    "unknown": {"BREAKOUT": 1.0, "MEAN_REVERSION": 1.0, "TREND_CONTINUATION": 1.0, "VOLATILITY_EXPANSION": 1.0},
}

CONFLUENCE_RULES = {"A+": 4, "B": 2}

TP_MULTIPLIERS = {
    "trend": {"tp1": 1.8, "tp2": 3.0, "inv": 1.1},
    "range": {"tp1": 1.2, "tp2": 2.0, "inv": 0.9},
    "vol_chop": {"tp1": 1.0, "tp2": 1.6, "inv": 0.8},
    "default": {"tp1": 1.6, "tp2": 2.8, "inv": 1.1},
}


INTELLIGENCE_FLAGS = {
    "squeeze_enabled": True,
    "volume_profile_enabled": True,
    "liquidity_enabled": True,
    "macro_correlation_enabled": True,
    "sentiment_enabled": True,
    "confluence_enabled": True,
}

SQUEEZE = {
    "bb_period": 20,
    "bb_std": 2.0,
    "kc_period": 20,
    "kc_atr_mult": 1.5,
    "fire_bonus_pts": 8,
}

VOLUME_PROFILE = {
    "num_buckets": 100, # Number of price buckets for VP calculation
    "va_percentage": 0.70, # Percentage of total volume for Value Area calculation
    "poc_proximity_penalty_pct": 0.005, # % distance from POC to incur penalty
    "va_bonus_pct": 0.002, # % distance within VA to get bonus
    "poc_penalty_pts": 5.0, # Points to deduct if far from POC
    "va_bonus_pts": 3.0, # Points to add if within VA
}

LIQUIDITY = {
    "depth_pct": 0.005,        # How far from mid-price to consider for volume (0.5%)
    "wall_threshold_btc": 10.0,  # Minimum BTC quantity to consider a "wall"
    "imbalance_threshold": 0.6,# How high of an imbalance (0.0 to 1.0) to flag
    "imbalance_bonus_pts": 5.0,
    "wall_bonus_pts": 10.0,
    "wall_penalty_pts": 5.0,
}


def validate_config() -> None:
    for k, v in LIQUIDITY.items():
        if not isinstance(v, (int, float)):
            raise ValueError(f"LIQUIDITY['{k}']: must be a number")
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
    
    for flag, value in INTELLIGENCE_FLAGS.items():
        if not isinstance(value, bool):
            raise ValueError(f"INTELLIGENCE_FLAGS['{flag}']: must be a boolean")
