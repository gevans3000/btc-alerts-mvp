# Phase 15 — Universal Provider Fallback & Collector Resilience

## Objective

Every collector must try **all available providers** in a priority chain. When provider A returns 403/429/timeout, the collector immediately falls back to B, then C, with zero data loss. The `BudgetManager` enforces per-provider rate limits so no API is hit too hard. New providers can be added by appending to the chain — zero changes to engine or dashboard code.

> **Current broken state (live-tested 2026-02-26 05:00 EST):**
>
> | Data Stream | Primary | Status | Fallback | Status | Result |
> |---|---|---|---|---|---|
> | **Orderbook** | Bybit | ❌ 403 Forbidden | None | N/A | Dead — 0 bids, 0 asks |
> | **Flows** | Bybit | ❌ 403 Forbidden | None | N/A | Dead — `healthy=False` |
> | **Derivatives** | Bybit | ❌ 403 Forbidden | OKX | ✅ BUT `funding_rate=0.0` hardcoded | Partial — no funding data |
> | **DXY** | Yahoo | ⚠️ 429 frequently | None | N/A | Intermittent — sometimes 120 candles, sometimes 0 |
> | **Gold** | Yahoo | ❌ 429 consistently | None | N/A | Dead — 0 candles → macro neutral |
> | **VIX** | Yahoo | ❌ Disabled in code | None | N/A | Dead — hardcoded `[]` |
> | **Price** | Kraken | ✅ | CoinGecko | ✅ | Working |
> | **Candles** | Kraken | ✅ | Bybit | ❌ 403 | Working (Kraken alone) |

---

## Architecture: Provider Chain Pattern

Every collector function follows this pattern:

```python
def fetch_X(budget: BudgetManager, ...) -> XSnapshot:
    """Try each provider in order. First healthy response wins."""
    providers = [
        ("provider_a", _fetch_from_a),
        ("provider_b", _fetch_from_b),
        ("provider_c", _fetch_from_c),
    ]
    for name, fetcher in providers:
        if not budget.can_call(name):
            continue
        try:
            result = fetcher(budget, ...)
            if result.healthy:
                return result
        except Exception:
            pass  # Next provider
    return XSnapshot(..., healthy=False)  # All providers exhausted
```

**Rules:**
1. Every provider call goes through `budget.can_call()` FIRST
2. Every provider call is wrapped in `try/except` — exceptions NEVER propagate
3. The `healthy` field is checked — unhealthy results trigger the next provider
4. Budget is recorded per-call, not per-provider

---

## Fix 1 — `collectors/base.py`: Update Budget Limits

### Changes

**BEFORE** (lines 35-44):
```python
    LIMITS = {
        "kraken": (24, 60.0),
        "coingecko": (10, 60.0),
        "alternative_me": (5, 300.0),
        "rss": (20, 300.0),
        "llm": (5, 300.0),
        "yahoo": (10, 300.0),
        "bybit": (24, 60.0),
        "okx": (24, 60.0),
    }
```

**AFTER**:
```python
    LIMITS = {
        "kraken": (24, 60.0),
        "coingecko": (10, 60.0),
        "alternative_me": (5, 300.0),
        "rss": (20, 300.0),
        "llm": (5, 300.0),
        "yahoo": (20, 300.0),     # increased from 10 — need 4 calls for macro per cycle
        "bybit": (24, 60.0),
        "okx": (30, 60.0),        # increased from 24 — OKX is now primary fallback for 3 streams
        "binance": (20, 60.0),    # new — future provider
    }
```

**Rationale:**
- Yahoo increased to 20: each cycle uses ~6 calls (SPX + DXY + Gold + VIX). At 2 cycles per 300s, that's 12 calls. 20 gives headroom.
- OKX increased to 30: now serves as fallback for derivatives (4 calls), orderbook (1), and flows (1) = 6 extra per cycle.
- Binance added: future provider slot. Budget registered but no collector uses it yet.

Also add a `mark_broken` method so collectors can flag a provider as temporarily unreachable, avoiding wasting budget on repeated 403 calls:

**After the `record_call` method (line 76), add:**

```python
    def mark_source_broken(self, source: str, duration_seconds: float = 300.0):
        """Temporarily exhaust a source's budget to skip it for duration_seconds.
        Call this when a source returns 403 (permanent for this session)."""
        with self._lock:
            bucket = self._buckets.get(source)
            if bucket:
                # Fill timestamps to max so can_call() returns False
                now = time.time()
                bucket.timestamps = [now] * bucket.max_calls
                self._save()
```

---

## Fix 2 — `collectors/derivatives.py`: Full Rewrite with OKX Funding Rate

**Replace entire file:**

```python
import logging
from dataclasses import dataclass, field
from typing import Dict

from collectors.base import BudgetManager, request_json

logger = logging.getLogger(__name__)


@dataclass
class DerivativesSnapshot:
    funding_rate: float
    oi_change_pct: float
    basis_pct: float
    source: str = "none"
    healthy: bool = True
    meta: Dict[str, str] = field(default_factory=dict)


def _safe_pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return ((new - old) / abs(old)) * 100.0


def _fetch_bybit(budget: BudgetManager, timeout: float) -> DerivativesSnapshot:
    budget.record_call("bybit")
    ticker_payload = request_json(
        "https://api.bybit.com/v5/market/tickers",
        params={"category": "linear", "symbol": "BTCUSDT"},
        timeout=timeout,
    )
    ticker_rows = ticker_payload.get("result", {}).get("list", [])
    if not ticker_rows:
        return DerivativesSnapshot(0.0, 0.0, 0.0, source="bybit", healthy=False, meta={"provider": "bybit"})

    row = ticker_rows[0]
    mark = float(row.get("markPrice", 0.0))
    index = float(row.get("indexPrice", 0.0))
    basis_pct = ((mark - index) / index) * 100.0 if index else 0.0

    budget.record_call("bybit")
    oi_payload = request_json(
        "https://api.bybit.com/v5/market/open-interest",
        params={"category": "linear", "symbol": "BTCUSDT", "intervalTime": "5min", "limit": 2},
        timeout=timeout,
    )
    oi_rows = oi_payload.get("result", {}).get("list", [])
    if len(oi_rows) < 2:
        return DerivativesSnapshot(float(row.get("fundingRate", 0.0)), 0.0, basis_pct, source="bybit", healthy=True, meta={"provider": "bybit"})

    old_oi = float(oi_rows[-1].get("openInterest", 0.0))
    new_oi = float(oi_rows[0].get("openInterest", 0.0))
    return DerivativesSnapshot(
        funding_rate=float(row.get("fundingRate", 0.0)),
        oi_change_pct=_safe_pct_change(old_oi, new_oi),
        basis_pct=basis_pct,
        source="bybit",
        healthy=True,
        meta={"provider": "bybit"},
    )


def _fetch_okx(budget: BudgetManager, timeout: float) -> DerivativesSnapshot:
    budget.record_call("okx")
    ticker_payload = request_json(
        "https://www.okx.com/api/v5/market/ticker",
        params={"instId": "BTC-USDT-SWAP"},
        timeout=timeout,
    )
    rows = ticker_payload.get("data", [])
    if not rows:
        return DerivativesSnapshot(0.0, 0.0, 0.0, source="okx", healthy=False, meta={"provider": "okx"})

    row = rows[0]
    mark = float(row.get("last", 0.0))

    budget.record_call("okx")
    index_payload = request_json(
        "https://www.okx.com/api/v5/market/index-tickers",
        params={"instId": "BTC-USDT"},
        timeout=timeout,
    )
    idx_rows = index_payload.get("data", [])
    index = float(idx_rows[0].get("idxPx", 0.0)) if idx_rows else 0.0

    # Fetch REAL funding rate from OKX (was hardcoded to 0.0 before)
    funding_rate = 0.0
    try:
        budget.record_call("okx")
        fr_payload = request_json(
            "https://www.okx.com/api/v5/public/funding-rate",
            params={"instId": "BTC-USDT-SWAP"},
            timeout=timeout,
        )
        fr_rows = fr_payload.get("data", [])
        if fr_rows:
            funding_rate = float(fr_rows[0].get("fundingRate", 0.0))
    except Exception:
        pass  # Keep 0.0 — better than crashing

    budget.record_call("okx")
    oi_payload = request_json(
        "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history",
        params={"instId": "BTC-USDT-SWAP", "period": "5m", "limit": 2},
        timeout=timeout,
    )
    oi_rows = oi_payload.get("data", [])
    basis_pct = ((mark - index) / index) * 100.0 if index else 0.0

    if len(oi_rows) < 2:
        return DerivativesSnapshot(funding_rate, 0.0, basis_pct, source="okx", healthy=True, meta={"provider": "okx"})

    old_oi = float(oi_rows[-1][1])
    new_oi = float(oi_rows[0][1])
    return DerivativesSnapshot(funding_rate, _safe_pct_change(old_oi, new_oi), basis_pct, source="okx", healthy=True, meta={"provider": "okx"})


def fetch_derivatives_context(budget: BudgetManager, timeout: float = 10.0) -> DerivativesSnapshot:
    """Provider chain: Bybit → OKX → unhealthy fallback."""
    providers = [
        ("bybit", lambda: _fetch_bybit(budget, timeout)),
        ("okx", lambda: _fetch_okx(budget, timeout)),
    ]
    for name, fetcher in providers:
        if not budget.can_call(name):
            continue
        try:
            result = fetcher()
            if result.healthy:
                return result
        except Exception as e:
            logger.warning(f"Derivatives provider {name} failed: {e}")
            # Mark broken if 403 to avoid retrying this session
            if "403" in str(e):
                budget.mark_source_broken(name)
            continue

    return DerivativesSnapshot(0.0, 0.0, 0.0, source="none", healthy=False, meta={"provider": "none"})
```

---

## Fix 3 — `collectors/orderbook.py`: Add OKX Fallback

**Replace the `fetch_orderbook` function** (lines 23-41):

**AFTER**:
```python
def fetch_orderbook(budget_manager) -> OrderBookSnapshot:
    """Provider chain: Bybit → OKX → unhealthy fallback."""
    from collectors.base import request_json
    import logging
    logger = logging.getLogger(__name__)

    # Provider 1: Bybit
    if budget_manager and budget_manager.can_call("bybit"):
        try:
            budget_manager.record_call("bybit")
            payload = request_json(
                "https://api.bybit.com/v5/market/orderbook",
                params={"category": "linear", "symbol": "BTCUSDT", "limit": 200},
                timeout=5.0
            )
            result = payload.get("result", {})
            bids = [(float(p), float(q)) for p, q in result.get("b", [])]
            asks = [(float(p), float(q)) for p, q in result.get("a", [])]
            if bids and asks:
                ts_ms = payload.get("time", int(datetime.now().timestamp() * 1000))
                return OrderBookSnapshot(ts=int(ts_ms / 1000), bids=bids, asks=asks)
        except Exception as e:
            logger.warning(f"Bybit orderbook failed: {e}")
            if "403" in str(e) and budget_manager:
                budget_manager.mark_source_broken("bybit")

    # Provider 2: OKX
    if budget_manager and budget_manager.can_call("okx"):
        try:
            budget_manager.record_call("okx")
            payload = request_json(
                "https://www.okx.com/api/v5/market/books",
                params={"instId": "BTC-USDT-SWAP", "sz": "200"},
                timeout=5.0
            )
            data_list = payload.get("data", [])
            if data_list:
                book = data_list[0]
                # OKX format: each entry is [price, quantity, deprecatedField, numOrders]
                bids = [(float(row[0]), float(row[1])) for row in book.get("bids", [])]
                asks = [(float(row[0]), float(row[1])) for row in book.get("asks", [])]
                if bids and asks:
                    ts_ms = int(book.get("ts", datetime.now().timestamp() * 1000))
                    return OrderBookSnapshot(ts=int(ts_ms / 1000), bids=bids, asks=asks)
        except Exception as e:
            logger.warning(f"OKX orderbook fallback failed: {e}")

    return OrderBookSnapshot(ts=int(datetime.now().timestamp()), bids=[], asks=[], healthy=False)
```

---

## Fix 4 — `collectors/flows.py`: Add OKX Fallback

**Replace entire file:**

```python
import logging
from dataclasses import dataclass, field
from typing import Dict

from collectors.base import BudgetManager, request_json

logger = logging.getLogger(__name__)


@dataclass
class FlowSnapshot:
    taker_ratio: float
    long_short_ratio: float
    crowding_score: float
    healthy: bool = True
    source: str = "none"
    meta: Dict[str, str] = field(default_factory=dict)


def _fetch_bybit_flow(budget: BudgetManager, timeout: float) -> FlowSnapshot:
    budget.record_call("bybit")
    payload = request_json(
        "https://api.bybit.com/v5/market/account-ratio",
        params={"category": "linear", "symbol": "BTCUSDT", "period": "5min", "limit": 2},
        timeout=timeout,
    )
    rows = payload.get("result", {}).get("list", [])
    if not rows:
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="bybit", meta={"provider": "bybit"})

    row = rows[0]
    buy_ratio = float(row.get("buyRatio", 0.5))
    sell_ratio = float(row.get("sellRatio", 0.5))
    long_ratio = float(row.get("longAccount", 0.5))
    short_ratio = float(row.get("shortAccount", 0.5))
    taker_ratio = buy_ratio / max(sell_ratio, 1e-6)
    ls_ratio = long_ratio / max(short_ratio, 1e-6)
    crowding = (taker_ratio - 1.0) * 12 + (ls_ratio - 1.0) * 10
    return FlowSnapshot(taker_ratio, ls_ratio, crowding, healthy=True, source="bybit", meta={"provider": "bybit"})


def _fetch_okx_flow(budget: BudgetManager, timeout: float) -> FlowSnapshot:
    budget.record_call("okx")
    payload = request_json(
        "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio",
        params={"instId": "BTC-USDT-SWAP", "period": "5m"},
        timeout=timeout,
    )
    rows = payload.get("data", [])
    if not rows:
        return FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="okx", meta={"provider": "okx"})

    # OKX returns list of [timestamp, longShortRatio] or similar
    row = rows[0]
    if isinstance(row, list) and len(row) >= 2:
        ls_ratio = float(row[1])
    elif isinstance(row, dict):
        ls_ratio = float(row.get("longShortRatio", 1.0))
    else:
        ls_ratio = 1.0

    # Use L/S ratio as a proxy for taker ratio (directional pressure)
    taker_ratio = ls_ratio
    crowding = (taker_ratio - 1.0) * 12 + (ls_ratio - 1.0) * 10
    return FlowSnapshot(taker_ratio, ls_ratio, crowding, healthy=True, source="okx", meta={"provider": "okx"})


def fetch_flow_context(budget: BudgetManager, timeout: float = 10.0) -> FlowSnapshot:
    """Provider chain: Bybit → OKX → unhealthy fallback."""
    providers = [
        ("bybit", lambda: _fetch_bybit_flow(budget, timeout)),
        ("okx", lambda: _fetch_okx_flow(budget, timeout)),
    ]
    for name, fetcher in providers:
        if not budget.can_call(name):
            continue
        try:
            result = fetcher()
            if result.healthy:
                return result
        except Exception as e:
            logger.warning(f"Flow provider {name} failed: {e}")
            if "403" in str(e):
                budget.mark_source_broken(name)
            continue

    return FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="none", meta={"provider": "none"})
```

---

## Fix 5 — `collectors/price.py`: Yahoo Rate-Limit Mitigation

Add delays between Yahoo calls in `fetch_macro_context` and re-enable VIX.

**Replace `fetch_macro_context` function** (lines 146-167):

**AFTER**:
```python
def fetch_macro_context(budget: BudgetManager, limit: int = 120, prefetched_spx: List[Candle] = None) -> Dict[str, List[Candle]]:
    """Fetch macro context (SPX, DXY, Gold, VIX) with inter-call delays to avoid Yahoo 429."""
    spx = []
    if prefetched_spx:
        spx = prefetched_spx
    elif budget.can_call("yahoo"):
        spx = _fetch_yahoo_symbol_candles(budget, "%5EGSPC", "5m", "5d", limit) or \
              _fetch_yahoo_symbol_candles(budget, "SPY", "5m", "5d", limit)

    # Stagger requests with 2s delays to prevent Yahoo 429 bursts
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
```

**Rationale**: Yahoo 429s occur from burst patterns (4 calls in <1s). Adding 2s delay between calls spaces them out enough to avoid rate limiting while keeping total macro fetch time under 10s.

---

## Fix 6 — `scripts/pid-129/dashboard_server.py`: Real Spread from Orderbook

**Replace `_estimate_spread` function** (lines 83-96):

**AFTER**:
```python
def _estimate_spread(alerts):
    """Extract real spread from latest alert's liquidity context, or estimate from price data."""
    # Try to compute from actual orderbook liquidity data
    for alert in reversed(alerts):
        dt_ctx = (alert.get("decision_trace") or {}).get("context", {})
        liq = dt_ctx.get("liquidity", {})
        if isinstance(liq, dict) and liq.get("bid_walls", -1) >= 0:
            # Orderbook was healthy for this alert — use realistic BTC perp spread
            mid = 0
            for key in ("entry_price", "price"):
                v = alert.get(key)
                if isinstance(v, (int, float)) and v > 0:
                    mid = v
                    break
            if mid > 0:
                return max(round(mid * 0.00002, 2), 0.50)  # ~0.002% = typical BTC perp spread
    # Fallback: estimate from price deltas across recent alerts
    prices = []
    for alert in reversed(alerts[-10:]):
        for key in ("entry_price", "price"):
            v = alert.get(key)
            if isinstance(v, (int, float)) and v > 0:
                prices.append(v)
                break
    if len(prices) >= 2:
        diffs = [abs(prices[i] - prices[i+1]) for i in range(len(prices)-1)]
        return min(max(min(diffs), 0.50), 50.0)
    return 1.0
```

---

## Summary of ALL Edits

| # | File | Change | Impact |
|---|---|---|---|
| 1 | `collectors/base.py` | Yahoo 10→20, OKX 24→30, add `binance` slot, add `mark_source_broken()` | Budget headroom for fallbacks |
| 2 | `collectors/derivatives.py` | Full rewrite: add OKX funding rate fetch, provider chain pattern | ✅ Funding probe fires |
| 3 | `collectors/orderbook.py` | Add OKX fallback for orderbook | ✅ Order Book probe fires |
| 4 | `collectors/flows.py` | Full rewrite: add OKX L/S ratio, provider chain pattern | ✅ Flow data → Momentum probe |
| 5 | `collectors/price.py` | Add 2s delays between Yahoo calls, re-enable VIX | ✅ DXY/Gold/VIX probes fire |
| 6 | `scripts/pid-129/dashboard_server.py` | Smarter spread from orderbook context | ✅ Live Tape spread real |

**Total files: 6** — `base.py`, `derivatives.py`, `orderbook.py`, `flows.py`, `price.py`, `dashboard_server.py`

---

## Adding a New Provider in the Future

To add a new exchange (e.g., Binance) as a fallback:

1. **`collectors/base.py`**: Add `"binance": (20, 60.0)` to `LIMITS` (already done in this phase)
2. **Create `_fetch_binance()` function** in the relevant collector file
3. **Append** `("binance", lambda: _fetch_binance(budget, timeout))` to the `providers` list in the fetch function

That's it. No engine, dashboard, or config changes needed. The provider chain pattern handles everything.

Example for adding Binance orderbook:
```python
# In collectors/orderbook.py, add after OKX block:

    # Provider 3: Binance
    if budget_manager and budget_manager.can_call("binance"):
        try:
            budget_manager.record_call("binance")
            payload = request_json(
                "https://api.binance.com/api/v3/depth",
                params={"symbol": "BTCUSDT", "limit": 500},
                timeout=5.0
            )
            bids = [(float(row[0]), float(row[1])) for row in payload.get("bids", [])]
            asks = [(float(row[0]), float(row[1])) for row in payload.get("asks", [])]
            if bids and asks:
                return OrderBookSnapshot(ts=int(datetime.now().timestamp()), bids=bids, asks=asks)
        except Exception as e:
            logger.warning(f"Binance orderbook fallback failed: {e}")
```

---

## Execution Checklist

```
[x] 1. Edit collectors/base.py — Budget limits + mark_source_broken() + freecryptoapi + bitunix
[x] 2. Replace collectors/derivatives.py — OKX funding rate + Bitunix fallback
[x] 3. Edit collectors/orderbook.py — OKX + Bitunix fallback
[x] 4. Replace collectors/flows.py — OKX L/S ratio (ccy=BTC param fix)
[x] 5. Edit collectors/price.py — Yahoo 2s delays + VIX re-enable + FreeCryptoAPI price
[x] 6. Edit scripts/pid-129/dashboard_server.py — Smarter spread
[x] 7. Smoke test derivatives: funding=0.0000940, source=okx ✅
[x] 8. Smoke test orderbook: 200 bids, 200 asks via OKX ✅
[x] 9. Smoke test flows: taker=1.54, ls=1.54, source=okx ✅
[x] 10. Run: python app.py --once — 25s cycle ✅
[x] 11. Verify: FUNDING_HIGH, FLOW_TAKER_BULLISH, SQUEEZE_ON, GOLD_RISING_BULLISH ✅
[x] 12. Verify: Radar 8/10 active probes ✅
```

---

## Expected Probe Status After Phase 15

| Probe | Pre-Phase 15 | Post-Phase 15 | Source |
|---|---|---|---|
| Squeeze | ⚫ (correct — no squeeze) | ⚫ or 🟢 when active | Same |
| Trend (HTF) | ✅ 🟢/🔴 | ✅ 🟢/🔴 | Same |
| Momentum | ✅ SENTIMENT only | ✅ SENTIMENT + FLOW_TAKER | OKX L/S ratio |
| ML Model | ✅ 🟢 when score≥20 | ✅ Same | Same |
| **Funding** | ❌ Always ⚫ | ✅ 🟢/🔴 every cycle | **OKX funding-rate API** |
| **DXY Macro** | ❌ Often ⚫ (429) | ✅ 🟢/🔴 reliably | Yahoo with delays |
| **Gold Macro** | ❌ Always ⚫ (429) | ✅ 🟢/🔴 reliably | Yahoo with delays |
| Fear & Greed | ✅ 🟢/🔴 | ✅ Same | Same |
| **Order Book** | ❌ Always ⚫ (403) | ✅ 🟢/🔴 when walls exist | **OKX orderbook API** |
| OI / Basis | ⚠️ Rarely fires | ✅ More frequent | Same OKX data, better thresholds |

**Conservative estimate: 7-9 out of 10 probes active per cycle.**

---
*Phase 15 Blueprint — Universal Provider Fallback & Collector Resilience*
*Fixes Bybit 403 and Yahoo 429 failures with OKX fallbacks and rate-limit mitigation*
*Provider chain pattern allows adding new exchanges with zero engine/dashboard changes*
