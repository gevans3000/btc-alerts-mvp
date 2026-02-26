#!/usr/bin/env python3
import base64
import hashlib
import json
import struct
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


def _safe_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


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


def _portfolio_stats(portfolio):
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

    streak = 0
    for value in reversed(r_values):
        if value < 0:
            streak -= 1
        elif value > 0:
            streak += 1
        else:
            continue  # Skip scratch trades (r_multiple == 0)

    return {
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_r": round(avg_r, 2),
        "streak": streak,
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
        # Limit to 15 alerts and strip heavy context to keep WS frames well under 64KB
        alerts = _load_alerts(limit=15)
        portfolio = _safe_json(PORTFOLIO_PATH, {"balance": 10000, "positions": [], "closed_trades": [], "max_drawdown": 0})
        mid = _latest_price(alerts)
        spread = _estimate_spread(alerts) if mid else 0.0
        stats = _portfolio_stats(portfolio)

        # Strip heavy decision_trace.context from each alert to reduce payload size
        # (codes are kept — only the bulk context dict with walls/sentiment/macro is removed)
        for a in alerts:
            dt = a.get("decision_trace")
            if isinstance(dt, dict):
                ctx = dt.get("context")
                if isinstance(ctx, dict):
                    # Keep only the small context keys needed by the dashboard JS
                    keep_keys = {"session_levels", "volume_profile", "avwap", "structure", "volume_impulse", "auto_rr"}
                    dt["context"] = {k: v for k, v in ctx.items() if k in keep_keys}

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "orderbook": {
                "mid": round(mid, 2),
                "spread": round(spread, 2),
                "bid": round(mid - spread/2, 2) if mid else 0,
                "ask": round(mid + spread/2, 2) if mid else 0
            },
            "portfolio": portfolio,
            "alerts": alerts,
            "stats": stats,
            "logs": f"Heartbeat {datetime.now().strftime('%H:%M:%S')}",
        }
    except Exception as e:
        print(f"Data error: {e}")
        return {"error": str(e)}


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
        else:
            self._serve_dashboard()

    def _serve_dashboard(self):
        path = DASHBOARD_PATH if (self.path=="/" or self.path=="/dashboard.html") else None
        if not path or not path.exists():
            self.send_error(404)
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Connection", "close") # Don't keep-alive for the HTML request to avoid WS conflicts
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
                payload = json.dumps(get_dashboard_data())
                self.wfile.write(_build_ws_frame(payload))
                self.wfile.flush()
                time.sleep(2)
        except:
            print(f"[*] WS disconnected: {self.client_address}")

    def log_message(self, fmt, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard Server Alpha: http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
