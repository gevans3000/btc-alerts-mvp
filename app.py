import hashlib
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import load_dotenv

from collectors.base import BudgetManager
from collectors.derivatives import DerivativesSnapshot, fetch_derivatives_context
from collectors.flows import FlowSnapshot, fetch_flow_context
from collectors.price import (
    PriceSnapshot,
    fetch_btc_multi_timeframe_candles,
    fetch_btc_price,
    fetch_macro_context,
    fetch_spx_multi_timeframe_bundle,
)
from collectors.social import FearGreedSnapshot, fetch_fear_greed, fetch_news
from config import COOLDOWN_SECONDS, validate_config
from engine import AlertScore, compute_score

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
        msg_hash = hashlib.md5(msg[:160].encode()).hexdigest()
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
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except Exception as exc:
            logger.warning("State file unreadable, resetting state: %s", exc)
            try:
                self.path.rename(self.path.with_suffix(self.path.suffix + ".bak"))
            except Exception:
                logger.warning("Failed to rotate bad state file")
            return {}
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}

    def should_send(self, score: AlertScore, current_price: float) -> bool:
        if score.action == "SKIP":
            return False
        now = int(time.time())
        s = self.state.get(score.symbol, {}).get(score.timeframe, {})
        cooldown = COOLDOWN_SECONDS.get(score.tier, COOLDOWN_SECONDS["B"])
        if s.get("lifecycle_key") != score.lifecycle_key or s.get("tier") != score.tier:
            return True
        if now - int(s.get("last_sent", 0)) > cooldown:
            return True
        if not s.get("tp1_hit", False):
            if score.direction == "LONG" and current_price >= score.tp1:
                return True
            if score.direction == "SHORT" and current_price <= score.tp1:
                return True
        return False

    def save(self, score: AlertScore, current_price: float):
        tp1_hit = (score.direction == "LONG" and current_price >= score.tp1) or (
            score.direction == "SHORT" and current_price <= score.tp1
        )
        self.state.setdefault(score.symbol, {})[score.timeframe] = {
            "lifecycle_key": score.lifecycle_key,
            "tier": score.tier,
            "last_sent": int(time.time()),
            "tp1_hit": tp1_hit,
        }
        self.path.write_text(json.dumps(self.state))




def _latest_spx_price(spx_tf, timeframe: str) -> float:
    candles = spx_tf.get(timeframe, [])
    if not candles:
        return 0.0
    return candles[-1].close


def _format_alert(score: AlertScore, provider_context: dict) -> str:
    payload = {
        "symbol": score.symbol,
        "timeframe": score.timeframe,
        "action": score.action,
        "tier": score.tier,
        "direction": score.direction,
        "strategy_type": score.strategy_type,
        "confidence_score": score.confidence,
        "entry_zone": score.entry_zone,
        "invalidation_level": round(score.invalidation, 2),
        "tp1": round(score.tp1, 2),
        "tp2": round(score.tp2, 2),
        "rr_ratio": round(score.rr_ratio, 2),
        "context": {
            "regime": score.regime,
            "session": score.session,
            "quality": score.quality,
            "providers": provider_context,
        },
        "reason_codes": score.reason_codes,
        "score_breakdown": score.score_breakdown,
        "blockers": score.blockers,
        "decision_trace": score.decision_trace,
    }
    return f"*{score.symbol} {score.timeframe} {score.action} ({score.tier})*\n```{json.dumps(payload, indent=2)}```"


def run():
    validate_config()
    bm = BudgetManager(".mvp_budget.json")
    notif = Notifier()
    state = AlertStateStore()

    with ThreadPoolExecutor(max_workers=8) as executor:
        f_price = executor.submit(fetch_btc_price, bm)
        f_btc = executor.submit(fetch_btc_multi_timeframe_candles, bm)
        f_spx = executor.submit(fetch_spx_multi_timeframe_bundle, bm)
        f_fg = executor.submit(fetch_fear_greed, bm)
        f_news = executor.submit(fetch_news, bm)
        f_deriv = executor.submit(fetch_derivatives_context, bm)
        f_flow = executor.submit(fetch_flow_context, bm)
        f_macro = executor.submit(fetch_macro_context, bm)

        btc_price = f_price.result()
        btc_tf = f_btc.result()
        spx_tf, spx_source_map = f_spx.result()
        fg = f_fg.result()
        news = f_news.result()
        derivatives = f_deriv.result()
        flows = f_flow.result()
        macro = f_macro.result()

    alerts = []
    for tf in ["5m", "15m", "1h"]:
        if btc_tf.get(tf):
            alerts.append(
                compute_score(
                    "BTC",
                    tf,
                    btc_price,
                    btc_tf[tf],
                    btc_tf.get("15m", []),
                    btc_tf.get("1h", []),
                    fg,
                    news,
                    derivatives,
                    flows,
                    macro,
                )
            )
        if spx_tf.get(tf):
            spx_price = PriceSnapshot(price=spx_tf[tf][-1].close, timestamp=time.time(), source="yahoo", healthy=True)
            alerts.append(
                compute_score(
                    "SPX_PROXY",
                    tf,
                    spx_price,
                    spx_tf[tf],
                    spx_tf.get("15m", []),
                    spx_tf.get("1h", []),
                    FearGreedSnapshot(50, "Neutral", healthy=False),
                    [],
                    DerivativesSnapshot(0.0, 0.0, 0.0, healthy=False, source="none", meta={"provider": "none"}),
                    FlowSnapshot(1.0, 1.0, 0.0, healthy=False, source="none", meta={"provider": "none"}),
                    macro,
                )
            )

    for alert in alerts:
        px = btc_price.price if alert.symbol == "BTC" else _latest_spx_price(spx_tf, alert.timeframe)
        provider_context = {
            "price": btc_price.source if alert.symbol == "BTC" else spx_source_map.get(alert.timeframe, "none"),
            "derivatives": derivatives.source if alert.symbol == "BTC" else "none",
            "flows": flows.source if alert.symbol == "BTC" else "none",
            "spx_mode": "direct" if spx_source_map.get(alert.timeframe) == "^GSPC" else "proxy" if alert.symbol != "BTC" else "n/a",
        }
        if not state.should_send(alert, px):
            logger.info("Filtered %s %s: %s", alert.symbol, alert.timeframe, json.dumps(alert.decision_trace))
            continue
        notif.send(_format_alert(alert, provider_context))
        state.save(alert, px)


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
