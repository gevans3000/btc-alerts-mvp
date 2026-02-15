import logging
import time
from dataclasses import dataclass
from typing import Dict, List

import httpx

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
            response = httpx.get(
                "https://api.kraken.com/0/public/Ticker",
                params={"pair": "XXBTZUSD"},
                timeout=timeout,
            )
            response.raise_for_status()
            price = float(response.json()["result"]["XXBTZUSD"]["c"][0])
            return PriceSnapshot(price, time.time(), source="kraken")
        except Exception as exc:
            logging.error(f"Kraken price fetch failed: {exc}")

    if budget.can_call("coingecko"):
        try:
            budget.record_call("coingecko")
            response = httpx.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin", "vs_currencies": "usd"},
                timeout=timeout,
            )
            response.raise_for_status()
            return PriceSnapshot(float(response.json()["bitcoin"]["usd"]), time.time(), source="coingecko")
        except Exception as exc:
            logging.error(f"CoinGecko price fetch failed: {exc}")

    return PriceSnapshot(0.0, time.time(), healthy=False)


def _fetch_kraken_ohlc(budget: BudgetManager, interval: int, limit: int) -> List[Candle]:
    if not budget.can_call("kraken"):
        return []
    try:
        budget.record_call("kraken")
        response = httpx.get(
            "https://api.kraken.com/0/public/OHLC",
            params={"pair": "XXBTZUSD", "interval": interval},
            timeout=10,
        )
        response.raise_for_status()
        raw = response.json()["result"].get("XXBTZUSD", [])
        candles = [
            Candle(str(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[6]))
            for row in raw
        ]
        return candles[-limit:]
    except Exception as exc:
        logging.error(f"Kraken candle fetch failed for {interval}m: {exc}")
        return []


def fetch_btc_candles(budget: BudgetManager, interval: int = 5, limit: int = 100) -> List[Candle]:
    return _fetch_kraken_ohlc(budget, interval=interval, limit=limit)


def fetch_btc_multi_timeframe_candles(budget: BudgetManager, limit: int = 120) -> Dict[str, List[Candle]]:
    return {
        "5m": _fetch_kraken_ohlc(budget, interval=5, limit=limit),
        "15m": _fetch_kraken_ohlc(budget, interval=15, limit=limit),
        "1h": _fetch_kraken_ohlc(budget, interval=60, limit=limit),
    }


def _fetch_yahoo_symbol_candles(budget: BudgetManager, symbol: str, limit: int = 120) -> List[Candle]:
    if not budget.can_call("yahoo"):
        return []
    try:
        budget.record_call("yahoo")
        response = httpx.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "5m", "range": "5d"},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        ts = result.get("timestamp", [])
        quote = result["indicators"]["quote"][0]
        candles: List[Candle] = []
        for i, tstamp in enumerate(ts):
            o, h, l, c, v = (
                quote["open"][i],
                quote["high"][i],
                quote["low"][i],
                quote["close"][i],
                quote.get("volume", [0] * len(ts))[i],
            )
            if None in (o, h, l, c):
                continue
            candles.append(Candle(str(tstamp), float(o), float(h), float(l), float(c), float(v or 0.0)))
        return candles[-limit:]
    except Exception as exc:
        logging.error(f"Yahoo fetch failed for {symbol}: {exc}")
        return []


def fetch_spx_candles(budget: BudgetManager, limit: int = 120) -> List[Candle]:
    return _fetch_yahoo_symbol_candles(budget, "%5EGSPC", limit)


def fetch_macro_context(budget: BudgetManager, limit: int = 120) -> Dict[str, List[Candle]]:
    return {
        "spx": _fetch_yahoo_symbol_candles(budget, "%5EGSPC", limit),
        "vix": _fetch_yahoo_symbol_candles(budget, "%5EVIX", limit),
        "nq": _fetch_yahoo_symbol_candles(budget, "NQ%3DF", limit),
    }
