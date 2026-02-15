import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from concurrent.futures import ThreadPoolExecutor
from collectors.base import BudgetManager
from collectors.derivatives import fetch_derivatives_context
from collectors.price import fetch_btc_multi_timeframe_candles, fetch_btc_price, fetch_spx_candles
from collectors.social import fetch_fear_greed, fetch_news
from engine import compute_score

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("btc_alerts")


class Notifier:
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.last_hash = ""

    def send(self, msg: str):
        if not self.token or not self.chat_id:
            print(f"\n--- ALERT ---\n{msg}\n------------\n")
            return
        msg_hash = hashlib.md5(msg[:140].encode()).hexdigest()
        if msg_hash == self.last_hash:
            return
        try:
            httpx.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            ).raise_for_status()
            self.last_hash = msg_hash
        except Exception as exc:
            logger.error(f"Telegram fail: {exc}")


class AlertStateStore:
    def __init__(self, path: str = ".mvp_alert_state.json"):
        self.path = Path(path)
        self.state = self._load()

    def _load(self):
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                return {}
        return {}

    def should_send(self, score, current_price: float) -> bool:
        now = int(time.time())
        last_key = self.state.get("lifecycle_key")
        last_regime = self.state.get("regime")
        last_sent = int(self.state.get("last_sent", 0))
        cooldown = 15 * 60

        if last_key != score.lifecycle_key or last_regime != score.regime:
            return True
        if now - last_sent > cooldown:
            return True

        tp1_hit = self.state.get("tp1_hit", False)
        if not tp1_hit and score.regime in ("long_signal", "bullish_bias") and current_price >= score.tp1:
            return True
        if not tp1_hit and score.regime in ("short_signal", "bearish_bias") and current_price <= score.tp1:
            return True
        return False

    def save(self, score, current_price: float):
        tp1_hit = False
        if score.regime in ("long_signal", "bullish_bias"):
            tp1_hit = current_price >= score.tp1
        if score.regime in ("short_signal", "bearish_bias"):
            tp1_hit = current_price <= score.tp1

        payload = {
            "lifecycle_key": score.lifecycle_key,
            "regime": score.regime,
            "last_sent": int(time.time()),
            "tp1_hit": tp1_hit,
        }
        self.path.write_text(json.dumps(payload))
        self.state = payload


def run():
    bm = BudgetManager(".mvp_budget.json")
    notif = Notifier()
    state = AlertStateStore()

    with ThreadPoolExecutor(max_workers=6) as executor:
        f_price = executor.submit(fetch_btc_price, bm)
        f_tf = executor.submit(fetch_btc_multi_timeframe_candles, bm)
        f_fg = executor.submit(fetch_fear_greed, bm)
        f_news = executor.submit(fetch_news, bm)
        f_deriv = executor.submit(fetch_derivatives_context, bm)
        f_spx = executor.submit(fetch_spx_candles, bm)

        price = f_price.result()
        tf = f_tf.result()
        fg = f_fg.result()
        news = f_news.result()
        derivatives = f_deriv.result()
        spx = f_spx.result()

    score = compute_score(price, tf["5m"], tf["15m"], tf["1h"], fg, news, derivatives, spx)

    if not state.should_send(score, price.price):
        logger.info("No meaningful state change; skipping alert.")
        return

    emoji = {
        "long_signal": "🟢🚀",
        "short_signal": "🔴📉",
        "bullish_bias": "📗",
        "bearish_bias": "📕",
        "sideways / no signal": "⚪",
    }.get(score.regime, "⚪")

    msg = (
        f"*{emoji} BTC 5m Alert ({score.confidence}/100)*\n"
        f"Regime: {score.regime.upper().replace('_', ' ')}\n"
        f"Direction: {score.direction}\n"
        f"Quality: {score.quality}\n"
        f"Price: ${price.price:,.0f}\n"
        f"R:R Ratio: 1:{score.rr_ratio:.2f}\n"
        f"Entry: {score.entry_zone}\n"
        f"Invalidation: {score.invalidation:,.0f}\n"
        f"TP1/TP2: {score.tp1:,.0f} / {score.tp2:,.0f}\n"
        f"Horizon: ~{score.time_horizon_bars} bars\n"
        "Factors:\n"
        + "\n".join(f"• {r}" for r in score.reasons)
    )
    if score.trump_hits:
        msg += f"\nPolicy: {score.trump_hits}"

    notif.send(msg)
    state.save(score, price.price)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run()
    else:
        while True:
            try:
                run()
            except Exception as exc:
                logger.error(f"Error: {exc}")
            time.sleep(300 - (time.time() % 300))
