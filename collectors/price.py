import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from collectors.base import BudgetManager, request_json
from utils import Candle


@dataclass
class PriceSnapshot:
    price: float
    timestamp: float
    source: str = "kraken"
    healthy: bool = True
    meta: Dict[str, str] = field(default_factory=dict)


def fetch_btc_price(budget: BudgetManager, timeout: float = 10.0) -> PriceSnapshot:
    if budget.can_call("kraken"):
        try:
            budget.record_call("kraken")
            payload = request_json("https://api.kraken.com/0/public/Ticker", params={"pair": "XXBTZUSD"}, timeout=timeout)
            price = float(payload["result"]["XXBTZUSD"]["c"][0])
            return PriceSnapshot(price, time.time(), source="kraken", meta={"provider": "kraken"})
            response = httpx.get("https://api.kraken.com/0/public/Ticker", params={"pair": "XXBTZUSD"}, timeout=timeout)
            response.raise_for_status()
            price = float(response.json()["result"]["XXBTZUSD"]["c"][0])
            return PriceSnapshot(price, time.time(), source="kraken")
        except Exception as exc:
            logging.error(f"Kraken price fetch failed: {exc}")

    if budget.can_call("coingecko"):
        try:
            budget.record_call("coingecko")
            payload = request_json(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin", "vs_currencies": "usd"},
                timeout=timeout,
            )
            return PriceSnapshot(float(payload["bitcoin"]["usd"]), time.time(), source="coingecko", meta={"provider": "coingecko"})
        except Exception as exc:
            logging.error(f"CoinGecko price fetch failed: {exc}")

    return PriceSnapshot(0.0, time.time(), source="none", healthy=False, meta={"provider": "none"})


def _from_ohlc_rows(raw: List[List], limit: int) -> List[Candle]:
    return [Candle(str(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[6])) for r in raw][-limit:]


def _from_ohlc_rows(raw: List[List], limit: int) -> List[Candle]:
    return [Candle(str(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[6])) for r in raw][-limit:]


def _fetch_kraken_ohlc(budget: BudgetManager, interval: int, limit: int) -> List[Candle]:
    if not budget.can_call("kraken"):
        return []
    try:
        budget.record_call("kraken")
        payload = request_json(
            "https://api.kraken.com/0/public/OHLC",
            params={"pair": "XXBTZUSD", "interval": interval},
            timeout=10,
        )
        return _from_ohlc_rows(payload["result"].get("XXBTZUSD", []), limit)
        response.raise_for_status()
        return _from_ohlc_rows(response.json()["result"].get("XXBTZUSD", []), limit)
    except Exception as exc:
        logging.error(f"Kraken candle fetch failed for {interval}m: {exc}")
        return []


def _fetch_bybit_ohlc(budget: BudgetManager, interval: str, limit: int) -> List[Candle]:
    if not budget.can_call("bybit"):
        return []
    try:
        budget.record_call("bybit")
        payload = request_json(
        response = httpx.get(
            "https://api.bybit.com/v5/market/kline",
            params={"category": "spot", "symbol": "BTCUSDT", "interval": interval, "limit": limit},
            timeout=10,
        )
        rows = payload.get("result", {}).get("list", [])
        response.raise_for_status()
        rows = response.json().get("result", {}).get("list", [])
        candles = [Candle(str(int(r[0]) // 1000), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in rows]
        return list(reversed(candles))[-limit:]
    except Exception as exc:
        logging.error(f"Bybit candle fetch failed for {interval}: {exc}")
        return []


def fetch_btc_multi_timeframe_candles(budget: BudgetManager, limit: int = 120) -> Dict[str, List[Candle]]:
    frames = {"5m": (5, "5"), "15m": (15, "15"), "1h": (60, "60")}
    out = {}
    for label, (kraken_i, bybit_i) in frames.items():
        candles = _fetch_kraken_ohlc(budget, interval=kraken_i, limit=limit)
        out[label] = candles or _fetch_bybit_ohlc(budget, interval=bybit_i, limit=limit)
    return out


def _fetch_yahoo_symbol_candles(budget: BudgetManager, symbol: str, interval: str, lookback: str, limit: int = 120) -> List[Candle]:
    if not budget.can_call("yahoo"):
        return []
    try:
        budget.record_call("yahoo")
        payload = request_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": interval, "range": lookback},
            timeout=10,
        )
        result = payload["chart"]["result"][0]
        ts = result.get("timestamp", [])
        quote = result["indicators"]["quote"][0]
        candles: List[Candle] = []
        for i, tstamp in enumerate(ts):
            o, h, l, c = quote["open"][i], quote["high"][i], quote["low"][i], quote["close"][i]
            v = quote.get("volume", [0] * len(ts))[i]
            if None in (o, h, l, c):
                continue
            candles.append(Candle(str(tstamp), float(o), float(h), float(l), float(c), float(v or 0.0)))
        return candles[-limit:]
    except Exception as exc:
        logging.error(f"Yahoo fetch failed for {symbol}: {exc}")
        return []


def fetch_spx_multi_timeframe_candles(budget: BudgetManager, limit: int = 120) -> Dict[str, List[Candle]]:
    candles, _ = fetch_spx_multi_timeframe_bundle(budget, limit)
    return candles


def fetch_spx_multi_timeframe_bundle(budget: BudgetManager, limit: int = 120) -> Tuple[Dict[str, List[Candle]], Dict[str, str]]:
    maps = {"5m": ("5m", "5d"), "15m": ("15m", "1mo"), "1h": ("1h", "3mo")}
    out: Dict[str, List[Candle]] = {}
    source_map: Dict[str, str] = {}
    for tf, (interval, rng) in maps.items():
        direct = _fetch_yahoo_symbol_candles(budget, "%5EGSPC", interval, rng, limit=limit)
        if direct:
            out[tf] = direct
            source_map[tf] = "^GSPC"
            continue
        proxy = _fetch_yahoo_symbol_candles(budget, "SPY", interval, rng, limit=limit)
        out[tf] = proxy
        source_map[tf] = "SPY" if proxy else "none"
    return out, source_map
    symbol = "%5EGSPC"
    maps = {"5m": ("5m", "5d"), "15m": ("15m", "1mo"), "1h": ("1h", "3mo")}
    out: Dict[str, List[Candle]] = {}
    for tf, (interval, rng) in maps.items():
        candles = _fetch_yahoo_symbol_candles(budget, symbol, interval, rng, limit=limit)
        if not candles:
            candles = _fetch_yahoo_symbol_candles(budget, "SPY", interval, rng, limit=limit)
        out[tf] = candles
    return out


def fetch_macro_context(budget: BudgetManager, limit: int = 120) -> Dict[str, List[Candle]]:
    return {
        "spx": _fetch_yahoo_symbol_candles(budget, "%5EGSPC", "5m", "5d", limit)
        or _fetch_yahoo_symbol_candles(budget, "SPY", "5m", "5d", limit),
        "spx": _fetch_yahoo_symbol_candles(budget, "%5EGSPC", "5m", "5d", limit) or _fetch_yahoo_symbol_candles(budget, "SPY", "5m", "5d", limit),
        "vix": _fetch_yahoo_symbol_candles(budget, "%5EVIX", "5m", "5d", limit),
        "nq": _fetch_yahoo_symbol_candles(budget, "NQ%3DF", "5m", "5d", limit),
    }
