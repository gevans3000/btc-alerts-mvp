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
    "sentiment_enabled": True,
    "confluence_enabled": True,
}

SENTIMENT = {
    "positive_news_keywords": [
        "bullish", "breakout", "rally", "surge", "gain", "up", "positive", "grow", "strong", "recover",
        "innovat", "adopt", "partner", "launch", "success", "advance", "boom", "explod", "soar"
    ],
    "negative_news_keywords": [
        "bearish", "dump", "crash", "fall", "down", "negative", "lose", "weak", "decline", "hack",
        "scam", "fraud", "ban", "regul", "restrict", "capitulat", "drop", "slump", "dip", "threat"
    ],
    "crypto_lexicon": {
        "btc": 0.8, "bitcoin": 0.8, "eth": 0.7, "ethereum": 0.7, "crypto": 0.6, "blockchain": 0.5,
        "hodl": 0.7, "moon": 0.8, "lambo": 0.6, "pump": 0.6, "bull": 0.6, "bear": -0.6,
        "fud": -0.7, "scam": -0.8, "hack": -0.9, "rug pull": -0.9, "liquidate": -0.7,
        "ath": 0.7, "all-time high": 0.7, "atl": -0.7, "all-time low": -0.7,
        "web3": 0.5, "defi": 0.5, "nft": 0.4, "metaverse": 0.4,
        "sharding": 0.3, "scaling": 0.3, "layer 2": 0.4, "zk-rollup": 0.5,
        "mining": 0.3, "halving": 0.6, "staking": 0.5,
        "exchange": 0.2, "wallet": 0.2, "decentralized": 0.5, "centralized": -0.3,
        "whale": 0.5, "retail": 0.2, "institutional": 0.6,
        "adoption": 0.7, "regulation": -0.5, "policy": -0.4,
        "airdrop": 0.6, "ico": 0.4, "ido": 0.4, "ieo": 0.4,
        "tokenomics": 0.3, "utility": 0.3, "governance": 0.3,
        "volatility": 0.0, "stablecoin": 0.2, "fiat": -0.2,
        "bear market": -0.8, "bull market": 0.8, "crab market": 0.0,
        "fear": -0.6, "greed": 0.6, "sentiment": 0.0
    },
    "extreme_greed_penalty_pts": 5.0,
    "greed_penalty_pts": 2.0,
    "extreme_fear_bonus_pts": 5.0,
    "fear_bonus_pts": 2.0,
    "positive_news_bonus_pts": 3.0,
    "negative_news_penalty_pts": 3.0,
}

SQUEEZE = {
    "bb_period": 20,
    "bb_std": 2.0,
    "kc_period": 20,
    "kc_atr_mult": 1.5,
    "fire_bonus_pts": 8,
    "squeeze_lookback": 14,
    "no_squeeze_lookback": 20,
    "momentum_lookback": 14,
}



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
    
    for flag, value in INTELLIGENCE_FLAGS.items():
        if not isinstance(value, bool):
            raise ValueError(f"INTELLIGENCE_FLAGS['{flag}']: must be a boolean")
