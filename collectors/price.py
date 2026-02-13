import time, httpx, logging
from dataclasses import dataclass
from typing import List, Optional
from collectors.base import BudgetManager
from utils import Candle

@dataclass
class PriceSnapshot:
    price: float
    timestamp: float
    source: str = "kraken"
    healthy: bool = True

def fetch_btc_price(budget: BudgetManager, timeout: float = 10.0) -> PriceSnapshot:
    if budget.can_call("kraken"):
        try:
            budget.record_call("kraken")
            r = httpx.get("https://api.kraken.com/0/public/Ticker", params={"pair": "XXBTZUSD"}, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            # Kraken ticker response: result -> XXBTZUSD -> c (last price) -> [price, volume]
            price = float(data["result"]["XXBTZUSD"]["c"][0])
            return PriceSnapshot(price, time.time(), source="kraken")
        except Exception as e:
            logging.error(f"Kraken price fetch failed: {e}")
            pass
    if budget.can_call("coingecko"):
        try:
            budget.record_call("coingecko")
            r = httpx.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": "bitcoin", "vs_currencies": "usd"}, timeout=timeout)
            r.raise_for_status()
            return PriceSnapshot(float(r.json()["bitcoin"]["usd"]), time.time(), source="coingecko")
        except: pass
    return PriceSnapshot(0.0, time.time(), healthy=False)

def fetch_btc_candles(budget: BudgetManager, limit: int = 100) -> List[Candle]:
    if budget.can_call("kraken"):
        try:
            budget.record_call("kraken")
            # Kraken OHLC interval: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600
            r = httpx.get("https://api.kraken.com/0/public/OHLC", params={"pair": "XXBTZUSD", "interval": 5}, timeout=10)
            r.raise_for_status()
            data = r.json()
            # OHLC entry: [time, open, high, low, close, vwap, volume, count]
            candles = []
            for k in data["result"]["XXBTZUSD"]:
                candles.append(Candle(str(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[6])))
            return candles[-limit:]
        except Exception as e:
            logging.error(f"Kraken candle fetch failed: {e}")
            pass
    
    return []
