from dataclasses import dataclass
from typing import List
from utils import Candle, ema as ema_calc, rsi, bollinger_bands
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline

GROUPS = {
    "policy": {"trump": 0.0, "bitcoin reserve": 0.7, "tariff": -0.4, "regulation": -0.3},
    "macro": {"rate hike": -0.4, "rate cut": 0.4, "fed": -0.1},
    "market": {"etf": 0.2, "hack": -0.6, "adoption": 0.4}
}

@dataclass
class AlertScore:
    regime: str
    confidence: int
    reasons: List[str]
    trump_hits: str
    quality: str

def compute_score(price: PriceSnapshot, candles: List[Candle], fg: FearGreedSnapshot, news: List[Headline]) -> AlertScore:
    bias, reasons, degraded = 0.0, [], []
    
    # 1. Technical Analysis (Scalping Focus)
    if not candles or len(candles) < 21:
        degraded.append("candles")
    else:
        # Use completed candles only (exclude the currently open candle)
        # assuming the fetcher returns the latest live candle at the end
        completed_candles = candles[:-1]
        closes = [c.close for c in completed_candles]
        volumes = [c.volume for c in completed_candles]
        current_price = price.price
        
        # RSI (14)
        r = rsi(closes, 14)
        if r:
            if r < 30: bias += 20; reasons.append(f"Oversold RSI ({r:.1f})")
            elif r > 70: bias -= 20; reasons.append(f"Overbought RSI ({r:.1f})")
            elif r < 40: bias += 5
            elif r > 60: bias -= 5

        # Bollinger Bands (20, 2)
        bb = bollinger_bands(closes, 20, 2)
        if bb:
            upper, mid, lower = bb
            if current_price < lower: bias += 15; reasons.append("Price below Lower BB (Oversold)")
            elif current_price > upper: bias -= 15; reasons.append("Price above Upper BB (Overbought)")
            
            # BB Squeeze / Trend confirmation
            if current_price > mid and r and r > 50: bias += 5

        # EMA Trend (Short term) - 9 vs 21
        e_s, e_l = ema_calc(closes, 9), ema_calc(closes, 21)
        if e_s and e_l:
            if e_s > e_l: bias += 10; reasons.append("Bullish EMA 9/21")
            else: bias -= 10; reasons.append("Bearish EMA 9/21")

        # Volume Spike
        if len(volumes) > 20:
            avg_vol = sum(volumes[-21:-1]) / 20
            if volumes[-1] > avg_vol * 1.5:
                # Volume confirms the candle direction
                direction = "Buy" if closes[-1] > closes[-2] else "Sell"
                reasons.append(f"High Vol {direction}")
                if direction == "Buy": bias += 5
                else: bias -= 5

    # 2. Sentiment (Context)
    if fg.healthy:
        # Contrarian still applies but lesser weight for scalping
        if fg.value < 20: bias += 5; reasons.append(f"Extreme Fear ({fg.value})")
        if fg.value > 80: bias -= 5; reasons.append(f"Extreme Greed ({fg.value})")
    else: degraded.append("fg")

    # 3. News Catalyst (Impact)
    hits = []
    for hl in news:
        t = hl.title.lower()
        for g, kws in GROUPS.items():
            for k, w in kws.items():
                if k in t:
                    hits.append(k); bias += (w * 5)
    
    # Finalize
    score = int(min(100, max(0, 50 + bias)))
    
    # Regime Definition for Scalping
    if score >= 65: regime = "long_signal"
    elif score <= 35: regime = "short_signal"
    elif score >= 55: regime = "bullish_bias"
    elif score <= 45: regime = "bearish_bias"
    else: regime = "neutral"

    trump = ", ".join(set(h for h in hits if h in GROUPS["policy"]))
    return AlertScore(regime, score, reasons[:5], trump, "ok" if not degraded else "degraded")
