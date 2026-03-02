import logging
import os
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



def _fetch_binance_price(budget: BudgetManager, timeout: float) -> PriceSnapshot:
    if not budget.can_call("binance"):
        return PriceSnapshot(0.0, time.time(), source="binance", healthy=False, meta={"provider": "binance"})
    try:
        budget.record_call("binance")
        payload = request_json("https://api.binance.com/api/v3/ticker/price", params={"symbol": "BTCUSDT"}, timeout=timeout)
        return PriceSnapshot(float(payload.get("price", 0.0)), time.time(), source="binance", meta={"provider": "binance"})
    except Exception as exc:
        logging.error(f"Binance price fetch failed: {exc}")
        return PriceSnapshot(0.0, time.time(), source="binance", healthy=False, meta={"provider": "binance"})


def _fetch_coinbase_price(budget: BudgetManager, timeout: float) -> PriceSnapshot:
    if not budget.can_call("coinbase"):
        return PriceSnapshot(0.0, time.time(), source="coinbase", healthy=False, meta={"provider": "coinbase"})
    try:
        budget.record_call("coinbase")
        payload = request_json("https://api.exchange.coinbase.com/products/BTC-USD/ticker", timeout=timeout)
        return PriceSnapshot(float(payload.get("price", 0.0)), time.time(), source="coinbase", meta={"provider": "coinbase"})
    except Exception as exc:
        logging.error(f"Coinbase price fetch failed: {exc}")
        return PriceSnapshot(0.0, time.time(), source="coinbase", healthy=False, meta={"provider": "coinbase"})


def _fetch_bitstamp_price(budget: BudgetManager, timeout: float) -> PriceSnapshot:
    if not budget.can_call("bitstamp"):
        return PriceSnapshot(0.0, time.time(), source="bitstamp", healthy=False, meta={"provider": "bitstamp"})
    try:
        budget.record_call("bitstamp")
        payload = request_json("https://www.bitstamp.net/api/v2/ticker/btcusd/", timeout=timeout)
        return PriceSnapshot(float(payload.get("last", 0.0)), time.time(), source="bitstamp", meta={"provider": "bitstamp"})
    except Exception as exc:
        logging.error(f"Bitstamp price fetch failed: {exc}")
        return PriceSnapshot(0.0, time.time(), source="bitstamp", healthy=False, meta={"provider": "bitstamp"})

def fetch_btc_price(budget: BudgetManager, timeout: float = 10.0) -> PriceSnapshot:
    if budget.can_call("kraken"):
        try:
            budget.record_call("kraken")
            payload = request_json("https://api.kraken.com/0/public/Ticker", params={"pair": "XXBTZUSD"}, timeout=timeout)
            price = float(payload["result"]["XXBTZUSD"]["c"][0])
            return PriceSnapshot(price, time.time(), source="kraken", meta={"provider": "kraken"})
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

    if budget.can_call("freecryptoapi"):
        try:
            token = os.getenv("FREECRYPTOAPI_TOKEN", "").strip()
            if token:
                budget.record_call("freecryptoapi")
                import httpx
                resp = httpx.get(
                    "https://api.freecryptoapi.com/v1/getData",
                    params={"symbol": "BTC"},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=timeout,
                )
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("status") == "success" and payload.get("symbols"):
                    price = float(payload["symbols"][0]["last"])
                    return PriceSnapshot(price, time.time(), source="freecryptoapi", meta={"provider": "freecryptoapi"})
        except Exception as exc:
            logging.error(f"FreeCryptoAPI price fetch failed: {exc}")

    for provider in (_fetch_binance_price, _fetch_coinbase_price, _fetch_bitstamp_price):
        snap = provider(budget, timeout)
        if snap.healthy and snap.price > 0:
            return snap

    return PriceSnapshot(0.0, time.time(), source="none", healthy=False, meta={"provider": "none"})


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
    except Exception as exc:
        logging.error(f"Kraken candle fetch failed for {interval}m: {exc}")
        return []


def _fetch_bybit_ohlc(budget: BudgetManager, interval: str, limit: int) -> List[Candle]:
    if not budget.can_call("bybit"):
        return []
    try:
        budget.record_call("bybit")
        payload = request_json(
            "https://api.bybit.com/v5/market/kline",
            params={"category": "spot", "symbol": "BTCUSDT", "interval": interval, "limit": limit},
            timeout=10,
        )
        rows = payload.get("result", {}).get("list", [])
        candles = [Candle(str(int(r[0]) // 1000), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in rows]
        return list(reversed(candles))[-limit:]
    except Exception as exc:
        logging.error(f"Bybit candle fetch failed for {interval}: {exc}")
        return []




def _fetch_binance_ohlc(budget: BudgetManager, interval: str, limit: int) -> List[Candle]:
    if not budget.can_call("binance"):
        return []
    try:
        budget.record_call("binance")
        rows = request_json(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": interval, "limit": limit},
            timeout=10,
        )
        return [
            Candle(str(int(r[0]) // 1000), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
            for r in rows
        ][-limit:]
    except Exception as exc:
        logging.error(f"Binance candle fetch failed for {interval}: {exc}")
        return []


def _fetch_coinbase_ohlc(budget: BudgetManager, granularity: int, limit: int) -> List[Candle]:
    if not budget.can_call("coinbase"):
        return []
    try:
        budget.record_call("coinbase")
        rows = request_json(
            "https://api.exchange.coinbase.com/products/BTC-USD/candles",
            params={"granularity": granularity},
            timeout=10,
        )
        rows = sorted(rows, key=lambda r: r[0])[-limit:]
        return [Candle(str(int(r[0])), float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5])) for r in rows]
    except Exception as exc:
        logging.error(f"Coinbase candle fetch failed for {granularity}s: {exc}")
        return []


def _fetch_bitstamp_ohlc(budget: BudgetManager, step: int, limit: int) -> List[Candle]:
    if not budget.can_call("bitstamp"):
        return []
    try:
        budget.record_call("bitstamp")
        payload = request_json(
            "https://www.bitstamp.net/api/v2/ohlc/btcusd/",
            params={"step": step, "limit": limit},
            timeout=10,
        )
        rows = payload.get("data", {}).get("ohlc", [])
        return [
            Candle(str(r["timestamp"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r.get("volume", 0.0)))
            for r in rows
        ][-limit:]
    except Exception as exc:
        logging.error(f"Bitstamp candle fetch failed for {step}s: {exc}")
        return []


def fetch_btc_multi_timeframe_candles(budget: BudgetManager, limit: int = 120) -> Dict[str, List[Candle]]:
    frames = {
        "5m": {"kraken": 5, "bybit": "5", "binance": "5m", "coinbase": 300, "bitstamp": 300},
        "15m": {"kraken": 15, "bybit": "15", "binance": "15m", "coinbase": 900, "bitstamp": 900},
        "1h": {"kraken": 60, "bybit": "60", "binance": "1h", "coinbase": 3600, "bitstamp": 3600},
        "4h": {"kraken": 240, "bybit": "240", "binance": "4h", "coinbase": 14400, "bitstamp": 14400},
    }
    out = {}
    for label, m in frames.items():
        if out:
            time.sleep(1.0)
        candles = _fetch_kraken_ohlc(budget, interval=m["kraken"], limit=limit)
        if not candles:
            candles = _fetch_bybit_ohlc(budget, interval=m["bybit"], limit=limit)
        if not candles:
            candles = _fetch_binance_ohlc(budget, interval=m["binance"], limit=limit)
        if not candles:
            candles = _fetch_coinbase_ohlc(budget, granularity=m["coinbase"], limit=limit)
        if not candles:
            candles = _fetch_bitstamp_ohlc(budget, step=m["bitstamp"], limit=limit)
        out[label] = candles
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
    maps = {"5m": ("5m", "5d")} # REDUCED: Only fetch 5m to minimize API usage
    # Disabled for safety: "15m": ("15m", "1mo"), "1h": ("1h", "3mo")
    
    out: Dict[str, List[Candle]] = {}
    source_map: Dict[str, str] = {}
    for tf, (interval, rng) in maps.items():
        if out: time.sleep(2.0) 
        
        direct = _fetch_yahoo_symbol_candles(budget, "%5EGSPC", interval, rng, limit=limit)
        if direct:
            out[tf] = direct
            source_map[tf] = "^GSPC"
            continue
        proxy = _fetch_yahoo_symbol_candles(budget, "SPY", interval, rng, limit=limit)
        out[tf] = proxy
        source_map[tf] = "SPY" if proxy else "none"
    return out, source_map


def fetch_macro_context(budget: BudgetManager, limit: int = 120, prefetched_spx: List[Candle] = None) -> Dict[str, List[Candle]]:
    """Fetch macro context with inter-call delays to prevent Yahoo 429 bursts."""
    spx = []
    if prefetched_spx:
        spx = prefetched_spx
    elif budget.can_call("yahoo"):
        spx = _fetch_yahoo_symbol_candles(budget, "%5EGSPC", "5m", "5d", limit) or \
              _fetch_yahoo_symbol_candles(budget, "SPY", "5m", "5d", limit)

    # Stagger Yahoo requests with 2s delays to avoid 429 bursts
    time.sleep(2.0)
    dxy = _fetch_yahoo_symbol_candles(budget, "DX-Y.NYB", "1d", "1y", limit)

    time.sleep(2.0)
    gold = _fetch_yahoo_symbol_candles(budget, "GC=F", "1d", "1y", limit)

    time.sleep(2.0)
    vix = _fetch_yahoo_symbol_candles(budget, "%5EVIX", "5m", "5d", limit)

    return {
        "spx": spx,
        "dxy": dxy,
        "gold": gold,
        "vix": vix,
        "nq": [],
    }

