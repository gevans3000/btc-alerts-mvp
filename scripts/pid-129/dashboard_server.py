import base64
import hashlib
import json
import os
import struct
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if not (BASE_DIR / "scripts").exists():
    BASE_DIR = Path.cwd()

HOST = "0.0.0.0"
PORT = 8000
DASHBOARD_PATH = BASE_DIR / "dashboard.html"
ALERTS_PATH = BASE_DIR / "logs" / "pid-129-alerts.jsonl"
PORTFOLIO_PATH = BASE_DIR / "data" / "paper_portfolio.json"
OVERRIDES_PATH = BASE_DIR / "data" / "dashboard_overrides.json"

# Module-level shared state
_STATE_LOCK = threading.Lock()
_CACHED_DATA = {}          # Latest dashboard JSON payload
_LAST_ALERT_MTIME = 0.0    # os.stat() mtime of alerts JSONL
_LAST_PORTFOLIO_MTIME = 0.0 # os.stat() mtime of portfolio JSON
_OVERRIDES = {}


def _safe_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


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


def _light_alerts(alerts):
    """Create lightweight alert summaries for the WS stream."""
    light = []
    for i, a in enumerate(alerts):
        dt = a.get("decision_trace", {}).copy()
        # Strip heavy context keys to keep WS frames reasonable while giving the UI what it needs
        if isinstance(dt, dict) and "context" in dt:
            ctx = dt.get("context")
            if isinstance(ctx, dict):
                keep_keys = {"session_levels", "volume_profile", "avwap", "structure", "volume_impulse", "auto_rr", "sentiment", "macro_correlation", "liquidity"}
                dt["context"] = {k: v for k, v in ctx.items() if k in keep_keys}
        
        light.append({
            "idx": i,
            "id": a.get("alert_id") or a.get("id"),
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
            "recipe": a.get("recipe_name") or _match_recipe(a.get("alert_id") or a.get("id"), alerts),
            "decision_trace": dt,
        })
    return light


def _load_alerts(limit=50):
    if not ALERTS_PATH.exists():
        return []
    try:
        # Use a more robust way to read on Windows to avoid sharing violations
        with open(ALERTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            rows = []
            for line in lines:
                if not line.strip(): continue
                try:
                    rows.append(json.loads(line))
                except: continue
            return rows[-limit:]
    except Exception as e:
        print(f"Error loading alerts: {e}")
        return []


def _latest_price(alerts):
    for alert in reversed(alerts):
        # Look for price in various possible fields
        for key in ("price", "mark_price", "entry", "entry_price", "last_price"):
            value = alert.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    return 0.0


def _portfolio_stats(portfolio, current_price=0.0, alerts=None):
    """
    Calculate comprehensive trading analytics from paper portfolio.
    """
    closed = portfolio.get("closed_trades", []) if isinstance(portfolio, dict) else []
    r_values = [t.get("r_multiple") for t in closed if isinstance(t.get("r_multiple"), (int, float))]
    
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r < 0]
    count = len(r_values)
    
    win_rate = (len(wins) / count * 100.0) if count else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    avg_r = (sum(r_values) / count) if count else 0.0

    # Directional Stats
    long_trades = []
    short_trades = []
    for t in closed:
        direction = t.get("direction", "NEUTRAL")
        r = t.get("r_multiple", 0)
        if direction == "LONG":
            long_trades.append(r)
        elif direction == "SHORT":
            short_trades.append(r)

    def _calc_subset(rs):
        c = len(rs)
        ws = [r for r in rs if r > 0]
        wr = (len(ws) / c * 100.0) if c else 0.0
        ar = (sum(rs) / c) if c else 0.0
        tr = sum(rs)
        return {"count": c, "wins": len(ws), "win_rate": round(wr, 1), "avg_r": round(ar, 2), "total_r": round(tr, 2)}

    long_stats = _calc_subset(long_trades)
    short_stats = _calc_subset(short_trades)

    # Recipe Stats
    recipe_performance = {}
    if alerts:
        for t in closed:
            alert_id = t.get("alert_id")
            recipe = _match_recipe(alert_id, alerts)
            if recipe not in recipe_performance:
                recipe_performance[recipe] = []
            recipe_performance[recipe].append(t.get("r_multiple", 0))

    recipe_stats = {}
    for name, rs in recipe_performance.items():
        c = len(rs)
        ws = [r for r in rs if r > 0]
        wr = (len(ws) / c * 100.0) if c else 0.0
        ar = (sum(rs) / c) if c else 0.0
        recipe_stats[name] = {"count": c, "wins": len(ws), "win_rate": round(wr, 1), "avg_r": round(ar, 2)}

    # Timeframe Stats
    tf_performance = {}
    for t in closed:
        tf = t.get("timeframe", "UNKNOWN")
        if tf not in tf_performance:
            tf_performance[tf] = []
        tf_performance[tf].append(t.get("r_multiple", 0))
    
    tf_stats = {}
    for tf, rs in tf_performance.items():
        tf_stats[tf] = _calc_subset(rs)

    # Kelly Criterion
    # Kelly % = W - [(1 - W) / R]
    # W = win probability (decimal)
    # R = average win / average loss ratio (absolute values)
    if wins and losses:
        W = len(wins) / len(r_values)
        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))
        R = avg_win / avg_loss if avg_loss > 0 else 1.0
        kelly = W - ((1 - W) / R)
        kelly_pct = round(max(0.0, min(kelly / 4, 0.25)), 4)  # Quarter Kelly, capped at 25%
    else:
        kelly_pct = 0.0

    # Unrealized PnL
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

    # Drawdown
    balance = portfolio.get("balance", 10000)
    peak = portfolio.get("peak_balance", balance)
    drawdown_pct = round(((peak - balance) / peak) * 100, 2) if peak > 0 else 0.0

    streak = 0
    for value in reversed(r_values):
        if value < 0:
            streak -= 1
        elif value > 0:
            streak += 1
        else:
            continue

    return {
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_r": round(avg_r, 2),
        "streak": streak,
        "total_trades": count,
        "total_r": round(sum(r_values), 2),
        "long_stats": long_stats,
        "short_stats": short_stats,
        "recipe_stats": recipe_stats,
        "tf_stats": tf_stats,
        "kelly_pct": kelly_pct,
        "open_upnl": round(open_upnl, 2),
        "drawdown_pct": drawdown_pct
    }


def _estimate_spread(alerts):
    """Extract real spread from orderbook data in latest alert, or estimate from price data."""
    # Try to get a realistic spread from orderbook liquidity context
    for alert in reversed(alerts):
        dt_ctx = (alert.get("decision_trace") or {}).get("context", {})
        liq = dt_ctx.get("liquidity", {})
        if isinstance(liq, dict) and liq.get("bid_walls", -1) >= 0:
            mid = 0
            for key in ("entry_price", "price"):
                v = alert.get(key)
                if isinstance(v, (int, float)) and v > 0:
                    mid = v
                    break
            if mid > 0:
                return max(round(mid * 0.00004, 2), 0.50)  # ~0.004% = realistic BTC perp spread (~$3.60 at $90k)
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



def get_dashboard_data():
    try:
        # Load all recent alerts for calculations, but only send limited summaries to WS
        all_recent_alerts = _load_alerts(limit=50)
        overrides = _load_overrides()
        
        # Apply filters from overrides
        alerts = all_recent_alerts
        if overrides.get("min_score"):
            alerts = [a for a in alerts if (a.get("confidence", 0) >= overrides["min_score"])]
        if overrides.get("direction_filter"):
            alerts = [a for a in alerts if a.get("direction") == overrides["direction_filter"]]
        
        portfolio = _safe_json(PORTFOLIO_PATH, {"balance": 10000, "positions": [], "closed_trades": [], "max_drawdown": 0})
        mid = _latest_price(all_recent_alerts)
        spread = _estimate_spread(all_recent_alerts) if mid else 0.0
        stats = _portfolio_stats(portfolio, current_price=mid, alerts=all_recent_alerts)

        # WS-friendly lightweight alerts
        light_alerts = _light_alerts(alerts[-15:])

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "orderbook": {
                "mid": round(mid, 2),
                "spread": round(spread, 2),
                "bid": round(mid - spread/2, 2) if mid else 0,
                "ask": round(mid + spread/2, 2) if mid else 0
            },
            "portfolio": portfolio,
            "alerts": light_alerts,
            "stats": stats,
            "overrides": overrides,
            "logs": f"Heartbeat {datetime.now().strftime('%H:%M:%S')}",
        }
    except Exception as e:
        print(f"Data error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


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
            
            # Also check overrides
            if OVERRIDES_PATH.exists():
                mt = OVERRIDES_PATH.stat().st_mtime
                # Not using mt for overrides currently, just checking every loop or on other changes
                # But let's just refresh if anything changed
            
            if changed or not _CACHED_DATA:
                new_data = get_dashboard_data()
                with _STATE_LOCK:
                    _CACHED_DATA = new_data
        except Exception as e:
            print(f"Watcher error: {e}")
        time.sleep(1)


def _build_ws_frame(payload: str) -> bytes:
    data = payload.encode("utf-8")
    length = len(data)
    if length <= 125:
        header = struct.pack("!BB", 0x81, length)
    elif length <= 65535:
        header = struct.pack("!BBH", 0x81, 126, length)
    else:
        header = struct.pack("!BBQ", 0x81, 127, length)
    return header + data


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/ws":
            self._handle_websocket()
        elif self.path.startswith("/api/alert/"):
            self._serve_alert_detail()
        elif self.path == "/api/alerts":
            self._serve_alerts_full()
        elif self.path == "/api/command":
            # Just show current overrides on GET /api/command
            self._json_response(_load_overrides())
        else:
            self._serve_dashboard()

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

    def _serve_alert_detail(self):
        """GET /api/alert/<index> — returns full un-stripped alert JSON."""
        try:
            parts = self.path.split("/")
            idx = int(parts[-1])
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

    def _handle_command(self):
        """POST /api/command — handles dashboard interaction."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            cmd = json.loads(body)
            
            action = cmd.get("action")
            global _OVERRIDES
            _load_overrides() # Refresh
            
            if action == "mute_recipe":
                recipe = cmd.get("recipe")
                minutes = cmd.get("minutes", 60)
                expiry = time.time() + (minutes * 60)
                if "muted_recipes" not in _OVERRIDES:
                    _OVERRIDES["muted_recipes"] = {}
                _OVERRIDES["muted_recipes"][recipe] = expiry
                _save_overrides()
                self._json_response({"status": "success", "muted": recipe, "until": expiry})
            
            elif action == "set_min_score":
                val = int(cmd.get("value", 0))
                _OVERRIDES["min_score"] = val
                _save_overrides()
                self._json_response({"status": "success", "min_score": val})
            
            elif action == "set_direction_filter":
                direction = cmd.get("direction", "BOTH")
                if direction == "BOTH":
                    _OVERRIDES.pop("direction_filter", None)
                else:
                    _OVERRIDES["direction_filter"] = direction
                _save_overrides()
                self._json_response({"status": "success", "direction": direction})
            
            elif action == "reset_overrides":
                _OVERRIDES = {}
                _save_overrides()
                self._json_response({"status": "success", "message": "All overrides cleared"})
            
            else:
                self.send_error(400, f"Unknown action: {action}")
                
        except Exception as e:
            self._json_response({"error": str(e)}, status=400)

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _serve_dashboard(self):
        path = DASHBOARD_PATH if (self.path=="/" or self.path=="/dashboard.html") else None
        if not path or not path.exists():
            self.send_error(404)
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(content)

    def _handle_websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400)
            return
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")).digest()).decode("utf-8")
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        
        print(f"[*] WS connected: {self.client_address}")
        try:
            while True:
                with _STATE_LOCK:
                    payload = json.dumps(_CACHED_DATA) if _CACHED_DATA else "{}"
                self.wfile.write(_build_ws_frame(payload))
                self.wfile.flush()
                time.sleep(2)
        except:
            print(f"[*] WS disconnected: {self.client_address}")

    def log_message(self, fmt, *args):
        return


def main():
    # Seed initial data
    global _CACHED_DATA
    with _STATE_LOCK:
        _CACHED_DATA.update(get_dashboard_data())
    
    # Start watcher thread
    watcher = threading.Thread(target=_watcher_loop, daemon=True)
    watcher.start()
    
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard Server Alpha: http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
