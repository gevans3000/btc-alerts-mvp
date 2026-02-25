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


def _load_alerts(limit=20):
    if not ALERTS_PATH.exists():
        return []
    rows = []
    for line in ALERTS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows[-limit:]


def _latest_price(alerts):
    for alert in reversed(alerts):
        for key in ("price", "mark_price", "entry"):
            value = alert.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return 0.0


def _portfolio_stats(portfolio):
    closed = portfolio.get("closed_trades", []) if isinstance(portfolio, dict) else []
    r_values = [t.get("r") for t in closed if isinstance(t.get("r"), (int, float))]
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
            break

    return {
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_r": round(avg_r, 2),
        "streak": streak,
    }


def get_dashboard_data():
    alerts = _load_alerts(limit=50)
    portfolio = _safe_json(PORTFOLIO_PATH, {"balance": 10000, "positions": [], "closed_trades": [], "max_drawdown": 0})
    mid = _latest_price(alerts)
    spread = 0.0
    orderbook = {
        "bid": round(mid - spread / 2, 2) if mid else 0.0,
        "ask": round(mid + spread / 2, 2) if mid else 0.0,
        "mid": round(mid, 2),
        "spread": round(spread, 2),
    }
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "orderbook": orderbook,
        "spread": orderbook["spread"],
        "portfolio": portfolio,
        "alerts": alerts,
        "stats": _portfolio_stats(portfolio),
        "logs": "dashboard_server heartbeat",
    }


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
        if self.path in ("/", "/dashboard.html"):
            self._serve_dashboard()
            return
        if self.path == "/ws":
            self._handle_websocket()
            return
        self.send_error(404, "Not Found")

    def _serve_dashboard(self):
        if not DASHBOARD_PATH.exists():
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"dashboard.html not found. Run: python scripts/pid-129/generate_dashboard.py")
            return
        content = DASHBOARD_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400, "Missing Sec-WebSocket-Key")
            return
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")).digest()
        ).decode("utf-8")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        try:
            while True:
                payload = json.dumps(get_dashboard_data())
                self.wfile.write(_build_ws_frame(payload))
                self.wfile.flush()
                time.sleep(2)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, fmt, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Serving dashboard on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
