import os, sys, time, httpx, hashlib, logging
from datetime import datetime, timezone
from dotenv import load_dotenv

from collectors.base import BudgetManager
from collectors.price import fetch_btc_price, fetch_btc_candles
from collectors.social import fetch_fear_greed, fetch_news
from engine import compute_score

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("btc_alerts")

class Notifier:
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.lh = ""

    def send(self, msg: str):
        if not self.token or not self.chat_id:
            print(f"\n--- ALERT ---\n{msg}\n------------\n"); return
        h = hashlib.md5(msg[:100].encode()).hexdigest()
        if h == self.lh: return
        try:
            httpx.post(f"https://api.telegram.org/bot{self.token}/sendMessage", json={"chat_id":self.chat_id,"text":msg,"parse_mode":"Markdown"}).raise_for_status()
            self.lh = h
        except Exception as e: logger.error(f"Telegram fail: {e}")

def run():
    bm = BudgetManager(".mvp_budget.json")
    notif = Notifier()
    p, c, f, n = fetch_btc_price(bm), fetch_btc_candles(bm), fetch_fear_greed(bm), fetch_news(bm)
    s = compute_score(p, c, f, n)
    emoji = {
        "long_signal": "🟢🚀", 
        "short_signal": "🔴📉", 
        "bullish_bias": "📗", 
        "bearish_bias": "📕", 
        "neutral": "⚪"
    }.get(s.regime, "⚪")
    
    msg = f"*{emoji} BTC 5m Alert ({s.confidence}/100)*\nScale: {s.regime.upper().replace('_', ' ')}\nPrice: ${p.price:,.0f}\nFactors:\n" + "\n".join(f"• {r}" for r in s.reasons)
    if s.trump_hits: msg += f"\nPolicy: {s.trump_hits}"
    notif.send(msg)

if __name__ == "__main__":
    if "--once" in sys.argv: run()
    else:
        while True:
            try: run()
            except Exception as e: logger.error(f"Error: {e}")
            
            # Align with 5-minute clock marks
            # e.g., if now is 12:02:00, sleep 180s to wake at 12:05:00
            time.sleep(300 - (time.time() % 300))
