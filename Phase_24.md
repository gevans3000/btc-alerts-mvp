# Phase 24 — Trading Terminal Backend Rewrite

**Status:** ✅ COMPLETELY DONE
**Depends on:** Phase 23 (✅ DONE)  
**Target files:** `scripts/pid-129/dashboard_server.py`, `dashboard.html`
**Goal:** Transform the dashboard server from a passive log viewer into a real-time decision-support system that helps the trader make *profitable* BTC futures decisions by surfacing directional edge, recipe performance, optimal position sizing, and interactive trade management.

---

## 🧩 PROBLEM STATEMENT (What's Broken Today)

### 1. Polling I/O wastes CPU
The WS loop does `time.sleep(2)` and re-reads `pid-129-alerts.jsonl` + `paper_portfolio.json` from disk **every 2 seconds per connected client**. With 3 browser tabs, that's 6 disk reads per second for files that only change every 5–10 minutes.

### 2. Full context is thrown away
Lines 128–137 strip `decision_trace.context` to keep WS frames under 64KB. The dashboard JS *needs* that context for the Confluence Radar, Key Levels, and Volume Impulse widgets. The current approach is a hack — it keeps some keys and deletes the rest, leading to missing data and bugs in every new widget.

### 3. Analytics don't help trading decisions
`_portfolio_stats()` returns 4 numbers (win_rate, profit_factor, avg_r, streak). But the trader cannot see:
- **Which direction** is working (LONGs vs SHORTs)
- **Which recipe** is profitable (HTF_REVERSAL vs BOS_CONTINUATION vs VOL_EXPANSION)
- **Which timeframe** to focus on right now
- **How much to risk** based on recent edge (Kelly criterion)
- **Unrealized PnL** for open positions at current market price

### 4. No bidirectional communication
The dashboard can't send commands back. The "Mute" button and "Signal Floor" filter exist in HTML but do nothing server-side. Settings changes require editing Python source code and restarting.

---

## 📋 IMPLEMENTATION TASKS

> **Rule for implementing agent:** Each task is independent. Complete them in order. After each task, verify the server starts and the dashboard still renders. **Do not modify any file outside of `scripts/pid-129/dashboard_server.py` in this phase.**

---

### Task 1: Event-Driven File Watching + Global State Cache

**What to change:** Replace the per-connection disk polling with a shared global state.

**Current code (lines 204–211):**
```python
while True:
    payload = json.dumps(get_dashboard_data())
    self.wfile.write(_build_ws_frame(payload))
    self.wfile.flush()
    time.sleep(2)
```

**New architecture:**
```python
import threading

# Module-level shared state
_STATE_LOCK = threading.Lock()
_CACHED_DATA = {}          # Latest dashboard JSON payload
_LAST_ALERT_MTIME = 0.0    # os.stat() mtime of alerts JSONL
_LAST_PORTFOLIO_MTIME = 0.0 # os.stat() mtime of portfolio JSON

def _watcher_loop():
    """Background thread: polls file mtimes every 1s, rebuilds cache only on change."""
    global _CACHED_DATA, _LAST_ALERT_MTIME, _LAST_PORTFOLIO_MTIME
    while True:
        try:
            changed = False
            if ALERTS_PATH.exists():
                mt = ALERTS_PATH.stat().st_mtime
                if mt != _LAST_ALERT_MTIME:
                    _LAST_ALERT_MTIME = mt
                    changed = True
            if PORTFOLIO_PATH.exists():
                mt = PORTFOLIO_PATH.stat().st_mtime
                if mt != _LAST_PORTFOLIO_MTIME:
                    _LAST_PORTFOLIO_MTIME = mt
                    changed = True
            if changed:
                new_data = get_dashboard_data()
                with _STATE_LOCK:
                    _CACHED_DATA = new_data
        except Exception as e:
            print(f"Watcher error: {e}")
        time.sleep(1)
```

**WS loop becomes:**
```python
while True:
    with _STATE_LOCK:
        payload = json.dumps(_CACHED_DATA) if _CACHED_DATA else "{}"
    self.wfile.write(_build_ws_frame(payload))
    self.wfile.flush()
    time.sleep(2)
```

**Why this matters:** Zero wasted disk reads. Multiple WS clients share one cached copy. The watcher thread is cheap (just `os.stat()`).

**Start the watcher in `main()`:**
```python
def main():
    # Seed initial data
    _CACHED_DATA.update(get_dashboard_data())
    watcher = threading.Thread(target=_watcher_loop, daemon=True)
    watcher.start()
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    ...
```

---

### Task 2: REST API for Full Alert Context (Stop Stripping Data)

**What to add:** Two new HTTP endpoints so the dashboard can fetch full context on demand.

**Add a `do_POST` method** to `DashboardHandler` and extend `do_GET`:

```python
def do_GET(self):
    if self.path == "/ws":
        self._handle_websocket()
    elif self.path.startswith("/api/alert/"):
        self._serve_alert_detail()
    elif self.path == "/api/alerts":
        self._serve_alerts_full()
    else:
        self._serve_dashboard()

def _serve_alert_detail(self):
    """GET /api/alert/<index> — returns full un-stripped alert JSON."""
    try:
        idx = int(self.path.split("/")[-1])
        alerts = _load_alerts(limit=50)
        if 0 <= idx < len(alerts):
            self._json_response(alerts[idx])
        else:
            self.send_error(404, "Alert index out of range")
    except Exception as e:
        self._json_response({"error": str(e)}, status=400)

def _serve_alerts_full(self):
    """GET /api/alerts — returns all alerts without context stripping."""
    alerts = _load_alerts(limit=50)
    self._json_response(alerts)

def _json_response(self, data, status=200):
    body = json.dumps(data).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(body)))
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Connection", "close")
    self.end_headers()
    self.wfile.write(body)
```

**What to change in `get_dashboard_data()`:**

For the **WS payload** (which must stay small), send only lightweight alert summaries instead of stripping fields from full alerts:

```python
def _light_alerts(alerts):
    """Create lightweight alert summaries for the WS stream."""
    light = []
    for i, a in enumerate(alerts):
        dt = a.get("decision_trace", {})
        light.append({
            "idx": i,
            "symbol": a.get("symbol"),
            "timeframe": a.get("timeframe"),
            "direction": a.get("direction"),
            "confidence": a.get("confidence"),
            "tier": a.get("tier"),
            "action": a.get("action"),
            "entry_zone": a.get("entry_zone"),
            "invalidation": a.get("invalidation"),
            "tp1": a.get("tp1"),
            "tp2": a.get("tp2"),
            "rr_ratio": a.get("rr_ratio"),
            "regime": a.get("regime"),
            "session": a.get("session"),
            "strategy_type": a.get("strategy_type"),
            "reason_codes": a.get("reason_codes", []),
            "score_breakdown": a.get("score_breakdown", {}),
            "timestamp": a.get("timestamp"),
            "price": a.get("price") or a.get("entry_price"),
            "recipe": a.get("recipe_name"),
            # Keep the full decision_trace.context for radar/key-levels
            "decision_trace": dt,
        })
    return light
```

**Why:** The dashboard JS already reads `decision_trace.codes` and `decision_trace.context.*` for every widget. By sending the full `decision_trace` in a compact summary (dropping only `intel` and the heavy raw candle data), we keep WS frames reasonable while giving the UI 100% of what it needs. The full raw alerts (including `intel`) are available via `/api/alert/<idx>` for deep-dive views.

---

### Task 3: Advanced Decision-Support Analytics

**Rewrite `_portfolio_stats()`** to return everything the trader needs to decide *whether to take the next trade*.

**New function signature and output:**
```python
def _portfolio_stats(portfolio, current_price=0.0):
    """
    Calculate comprehensive trading analytics from paper portfolio.
    
    Returns dict with keys:
    - win_rate, profit_factor, avg_r, streak (existing — keep these)
    - total_trades, total_r
    - long_stats: {count, wins, win_rate, avg_r, total_r}
    - short_stats: {count, wins, win_rate, avg_r, total_r}
    - recipe_stats: {recipe_name: {count, wins, win_rate, avg_r}}
    - tf_stats: {timeframe: {count, wins, win_rate, avg_r, total_r}}
    - kelly_pct: optimal Kelly fraction (float, 0.0–1.0)
    - open_upnl: total unrealized PnL across open positions
    - drawdown_pct: current drawdown from peak
    """
```

**Implementation details for each sub-calculation:**

#### 3a. Directional Edge (LONG vs SHORT)
```python
closed = portfolio.get("closed_trades", [])
for t in closed:
    direction = t.get("direction", "NEUTRAL")
    r = t.get("r_multiple", 0)
    if direction == "LONG":
        long_trades.append(r)
    elif direction == "SHORT":
        short_trades.append(r)

# For each direction, compute: count, wins, win_rate, avg_r, total_r
# Example output: long_stats = {"count": 8, "wins": 5, "win_rate": 62.5, "avg_r": 0.15, "total_r": 1.2}
```

**Trading value:** If LONGs are 60% WR with +0.3R avg but SHORTs are 30% WR with -0.5R avg, the trader knows to ONLY take LONG signals.

#### 3b. Recipe Performance
```python
# Group closed trades by the recipe that generated them.
# The recipe name is NOT currently stored in closed_trades.
# Workaround: match closed_trade.alert_id against alerts JSONL to find recipe name.
# If no match found, label as "NO_RECIPE".
#
# For the implementing agent: Add a helper function:
def _match_recipe(alert_id, alerts):
    """Find the recipe name from the alerts JSONL for a given alert_id."""
    for a in alerts:
        if a.get("alert_id") == alert_id or a.get("id") == alert_id:
            dt = a.get("decision_trace", {})
            codes = dt.get("codes", [])
            for c in codes:
                if c.endswith("_RECIPE"):
                    return c.replace("_RECIPE", "")
            return "NO_RECIPE"
    return "UNKNOWN"
```

**Trading value:** If `BOS_CONTINUATION` has 80% WR but `HTF_REVERSAL` has 20% WR, the trader will mute reversal alerts.

#### 3c. Kelly Criterion Position Sizing
```python
# Kelly % = W - [(1 - W) / R]
# W = win probability (decimal)
# R = average win / average loss ratio (absolute values)
# Cap at 25% (quarter Kelly for safety)
wins = [r for r in r_values if r > 0]
losses = [abs(r) for r in r_values if r < 0]
if wins and losses:
    W = len(wins) / len(r_values)
    R = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
    kelly = W - ((1 - W) / R)
    kelly_pct = round(max(0.0, min(kelly / 4, 0.25)), 4)  # Quarter Kelly, capped at 25%
else:
    kelly_pct = 0.0
```

**Trading value:** Tells the trader "based on your edge, risk X% of balance per trade" instead of guessing.

#### 3d. Unrealized PnL for Open Positions
```python
open_positions = portfolio.get("positions", [])
open_upnl = 0.0
if current_price > 0:
    for pos in open_positions:
        entry = pos.get("entry_price", 0)
        size = pos.get("size_usdt", 0)
        direction = pos.get("direction", "LONG")
        if entry > 0 and size > 0:
            if direction == "LONG":
                pnl = (current_price - entry) / entry * size
            else:
                pnl = (entry - current_price) / entry * size
            open_upnl += pnl
```

**Trading value:** Shows "you're currently up/down $X across all open trades" — critical for deciding whether to add more exposure.

#### 3e. Drawdown from Peak
```python
balance = portfolio.get("balance", 10000)
peak = portfolio.get("peak_balance", balance)
drawdown_pct = round(((peak - balance) / peak) * 100, 2) if peak > 0 else 0.0
```

**Trading value:** If drawdown > 10%, the system should warn the trader to reduce risk.

---

### Task 4: Bidirectional Command Interface

**Add `do_POST` to `DashboardHandler`:**
```python
def do_POST(self):
    if self.path == "/api/command":
        self._handle_command()
    else:
        self.send_error(404)

def do_OPTIONS(self):
    """Handle CORS preflight for POST requests."""
    self.send_response(200)
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.end_headers()

# Module-level overrides state
OVERRIDES_PATH = BASE_DIR / "data" / "dashboard_overrides.json"
_OVERRIDES = {}

def _load_overrides():
    global _OVERRIDES
    if OVERRIDES_PATH.exists():
        try:
            _OVERRIDES = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _OVERRIDES = {}
    return _OVERRIDES

def _save_overrides():
    OVERRIDES_PATH.write_text(json.dumps(_OVERRIDES, indent=2), encoding="utf-8")
```

**Supported commands (implement in `_handle_command`):**

| Action | Payload Example | Effect |
|--------|----------------|--------|
| `mute_recipe` | `{"action":"mute_recipe","recipe":"HTF_REVERSAL","minutes":60}` | Adds recipe to `_OVERRIDES["muted_recipes"]` with expiry timestamp |
| `set_min_score` | `{"action":"set_min_score","value":50}` | Sets `_OVERRIDES["min_score"]` = 50 |
| `set_direction_filter` | `{"action":"set_direction_filter","direction":"LONG"}` | Sets `_OVERRIDES["direction_filter"]` = "LONG" |
| `reset_overrides` | `{"action":"reset_overrides"}` | Clears all overrides |

**Apply overrides in `get_dashboard_data()`:**
```python
overrides = _load_overrides()
# Filter alerts based on overrides
if overrides.get("min_score"):
    alerts = [a for a in alerts if (a.get("confidence", 0) >= overrides["min_score"])]
if overrides.get("direction_filter"):
    alerts = [a for a in alerts if a.get("direction") == overrides["direction_filter"]]
```

**Include overrides in WS payload:**
```python
return {
    ...existing keys...,
    "overrides": _load_overrides(),
}
```

**Trading value:** The trader can mute a losing recipe mid-session, filter to LONG-only during an uptrend, or raise the minimum score floor — all from the dashboard without restarting anything.

---

### Task 5: Enhanced WS Payload Structure

**Final `get_dashboard_data()` output schema:**
```python
{
    "timestamp": "2026-02-28T15:56:48+00:00",
    "orderbook": {"mid": 64893.30, "spread": 3.60, "bid": 64891.50, "ask": 64895.10},
    "portfolio": {
        "balance": 8929.97,
        "positions": [...],          # Open positions array
        "closed_trades": [...],      # Closed trades array (needed for client-side inspection)
        "peak_balance": 10000.0,
        "max_drawdown": 0.1629
    },
    "alerts": [...],                 # Lightweight alert summaries (from _light_alerts)
    "stats": {
        "win_rate": 63.0,
        "profit_factor": 1.85,
        "avg_r": 0.26,
        "streak": 2,
        "total_trades": 27,
        "total_r": 6.92,
        "long_stats": {"count": 8, "wins": 5, "win_rate": 62.5, "avg_r": 0.15, "total_r": 1.2},
        "short_stats": {"count": 15, "wins": 11, "win_rate": 73.3, "avg_r": 0.32, "total_r": 4.8},
        "recipe_stats": {"BOS_CONTINUATION": {"count": 5, "wins": 4, "win_rate": 80.0, "avg_r": 0.45}},
        "tf_stats": {"5m": {"count": 15, "wins": 10, "win_rate": 66.7, "avg_r": 0.13}},
        "kelly_pct": 0.12,
        "open_upnl": -45.20,
        "drawdown_pct": 10.7
    },
    "overrides": {"min_score": 50, "muted_recipes": []},
    "logs": "Heartbeat 12:15:00"
}
```

**Critical: do NOT break the existing frontend.** The dashboard JS reads:
- `data.orderbook.mid` / `.spread` → Live Tape
- `data.portfolio.balance` → Balance display
- `data.stats.win_rate` / `.profit_factor` → Stats display
- `data.alerts[].decision_trace.codes` → Confluence Radar
- `data.alerts[].decision_trace.context.*` → Key Levels, RVOL, OI Regime, etc.

All of these existing keys MUST remain in the same shape. The new keys (`long_stats`, `short_stats`, `kelly_pct`, etc.) are **additive only** — the frontend will use them later.

---

## ⚙️ EXECUTION ORDER

```
1. Task 1 (Event-driven watcher)    — threading change, no API change
2. Task 5 (Define payload schema)   — ensure _light_alerts works
3. Task 2 (REST endpoints)          — new GET routes, no WS change
4. Task 3 (Advanced analytics)      — rewrite _portfolio_stats
5. Task 4 (Command interface)       — add POST routes + overrides
```

---

## ✅ VERIFICATION CHECKLIST

After implementing, verify ALL of these:

1. **Server starts:**  
   ```
   python scripts/pid-129/dashboard_server.py
   ```
   No import errors, prints `Dashboard Server Alpha: http://localhost:8000`.

2. **Dashboard loads:**  
   Open `http://localhost:8000` in browser — the HTML renders, WebSocket connects ("Live Feed: Online").

3. **Live data still works:**  
   - BTC Mid price updates every 2s
   - Confluence Radar still shows colored dots (🟢/🔴/⚫)
   - Key Levels (PDH, PDL, POC, AVWAP) still populate
   - RVol, OI Regime, Taker Ratio still display

4. **New REST endpoints work:**
   ```
   curl http://localhost:8000/api/alerts
   curl http://localhost:8000/api/alert/0
   ```
   Both return valid JSON with full `decision_trace`.

5. **Stats include new fields:**  
   In WS payload, `stats` must contain `long_stats`, `short_stats`, `kelly_pct`, `open_upnl`, `drawdown_pct`.

6. **Commands work:**
   ```
   curl -X POST http://localhost:8000/api/command -H "Content-Type: application/json" -d "{\"action\":\"set_min_score\",\"value\":50}"
   curl http://localhost:8000/api/command
   ```
   Overrides persist to `data/dashboard_overrides.json`.

7. **No existing tests break:**
   ```
   python -m pytest tests/ -q
   ```

---

## 🚫 WHAT THIS PHASE DOES NOT CHANGE

- **No changes to `engine.py`** — score calculation untouched
- **No changes to `app.py`** — alert loop untouched
- **No changes to `config.py`** — tunables untouched
- **No changes to `dashboard.html`** — frontend untouched (new stats keys are additive; frontend will consume them in a later phase)
- **No changes to any collector or intelligence module**
- **No new pip dependencies** — uses only `threading`, `json`, `os`, `time`, `struct`, `hashlib`, `base64`, `http.server` (all stdlib)
- **No removal of existing WS functionality** — `connectWS()` in dashboard.html will keep working

---

## 📊 IMPACT ON TRADING DECISIONS

| Before (Phase 23) | After (Phase 24) |
|---|---|
| "Win rate: 63%" — but am I winning LONGs or SHORTs? | `long_stats.win_rate: 62.5%` / `short_stats.win_rate: 73.3%` → short bias is working, fade weak LONGs |
| No recipe performance visibility | `recipe_stats.BOS_CONTINUATION: 80% WR` → trust this recipe, mute others |
| Guessing position size | `kelly_pct: 0.12` → risk 12% of balance per trade (quarter-Kelly) |
| No idea if open trades are profitable | `open_upnl: -$45` → reduce exposure, don't add |
| Must restart server to change settings | POST `/api/command` → mute a recipe or raise score floor live |
| Context data randomly missing in UI | Full `decision_trace` in WS + REST fallback → 100% radar accuracy |

---

_Phase 24 | Trading Terminal Backend Rewrite | v24.0_
