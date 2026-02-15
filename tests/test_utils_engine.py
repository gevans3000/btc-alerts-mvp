import copy
import json
import tempfile
import time
import unittest
import httpx
from unittest.mock import Mock, patch

from app import AlertStateStore, _format_alert
from config import TIMEFRAME_RULES, validate_config
from collectors.base import request_json
from collectors.derivatives import fetch_derivatives_context
from collectors.flows import fetch_flow_context
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from engine import compute_score
from tools.replay import replay_symbol_timeframe, summarize
from tools.replay import replay_symbol_timeframe
from utils import Candle, adx, atr, ema, percentile_rank, rsi


class UtilsTests(unittest.TestCase):
    def test_ema_and_rsi(self):
        values = [100 + i for i in range(30)]
        self.assertIsNotNone(ema(values, 9))
        self.assertGreater(rsi(values, 14), 50)

    def test_atr_adx_percentile(self):
        candles = [Candle(str(i), 100 + i, 101 + i, 99 + i, 100.5 + i, 10) for i in range(40)]
        self.assertGreater(atr(candles, 14), 0)
        self.assertGreater(adx(candles, 14), 0)
        self.assertEqual(percentile_rank([1, 2, 3, 4], 3), 75.0)


class EngineTests(unittest.TestCase):
    def _candles(self, start=100, n=90, step=0.8):
        rows, px = [], start
        now = int(time.time()) - (n * 300)
        for i in range(n):
            op, cl = px, px + step
            rows.append(Candle(str(now + (i * 300)), op, max(op, cl) + 0.4, min(op, cl) - 0.4, cl, 100 + i))
        for i in range(n):
            op, cl = px, px + step
            rows.append(Candle(str(now + (i * 300)), op, max(op, cl) + 0.4, min(op, cl) - 0.4, cl, 100 + i))
        for i in range(n):
            op, cl = px, px + step
            rows.append(Candle(str(now + (i * 300)), op, max(op, cl) + 0.4, min(op, cl) - 0.4, cl, 100 + i))
        for i in range(n):
            op, cl = px, px + step
            rows.append(Candle(str(1700000000 + (i * 300)), op, max(op, cl) + 0.4, min(op, cl) - 0.4, cl, 100 + i))
            px = cl
        return rows

    def test_compute_score_outputs_fields(self):
        c5 = self._candles()
        c15 = self._candles(step=1.2)
        c1h = self._candles(step=1.5)
        price = PriceSnapshot(price=c5[-1].close, timestamp=0)
        fg = FearGreedSnapshot(value=30, label="Fear", healthy=True)
        macro = {"spx": c5, "vix": list(reversed(c5)), "nq": c5}

        score = compute_score(
            "BTC", "5m", price, c5, c15, c1h, fg, [], fetch_derivatives_context(_OffBudget()), fetch_flow_context(_OffBudget()), macro
        )

        self.assertIn(score.strategy_type, {"BREAKOUT", "TREND_CONTINUATION", "MEAN_REVERSION", "VOLATILITY_EXPANSION", "NONE"})
        self.assertIn(score.tier, {"A+", "B", "NO-TRADE"})
        self.assertIn(score.action, {"TRADE", "WATCH", "SKIP"})
        self.assertGreaterEqual(score.confidence, 0)
        self.assertLessEqual(score.confidence, 100)
        self.assertTrue(isinstance(score.reason_codes, list))
        self.assertIn("candidates", score.decision_trace)

    def test_news_changes_confidence(self):
        c5 = self._candles()
        c15 = self._candles(step=1.2)
        c1h = self._candles(step=1.5)
        price = PriceSnapshot(price=c5[-1].close, timestamp=0)
        fg = FearGreedSnapshot(value=30, label="Fear", healthy=True)
        macro = {"spx": c5, "vix": list(reversed(c5)), "nq": c5}

        base = compute_score(
            "BTC", "5m", price, c5, c15, c1h, fg, [], fetch_derivatives_context(_OffBudget()), fetch_flow_context(_OffBudget()), macro
        )
        with_news = compute_score(
            "BTC",
            "5m",
            price,
            c5,
            c15,
            c1h,
            fg,
            [Headline(title="Major exchange hack triggers panic", source="test")],
            fetch_derivatives_context(_OffBudget()),
            fetch_flow_context(_OffBudget()),
            macro,
        )
        self.assertLess(with_news.confidence, base.confidence)

    def test_stale_candles_block_signal(self):
        stale_end = int(time.time()) - (4 * 3600)
        stale_start = stale_end - (89 * 300)
        c5 = [Candle(str(stale_start + (i * 300)), 100 + i, 101 + i, 99 + i, 100.5 + i, 100 + i) for i in range(90)]
        macro = {"spx": c5, "vix": list(reversed(c5)), "nq": c5}

        score = compute_score(
            "BTC",
            "5m",
            PriceSnapshot(price=c5[-1].close, timestamp=0),
            c5,
            c5,
            c5,
            FearGreedSnapshot(value=30, label="Fear", healthy=True),
            [],
            fetch_derivatives_context(_OffBudget()),
            fetch_flow_context(_OffBudget()),
            macro,
        )

        self.assertIn("Stale market data", score.blockers)
        self.assertEqual(score.action, "SKIP")

    def test_arbitration_same_side_tie_keeps_signal(self):
        now = int(time.time()) - (90 * 300)
        candles = [
            Candle(str(now + (i * 300)), 100 + i * 0.5, 101 + i * 0.5, 99 + i * 0.5, 100.5 + i * 0.5, 150 + i)
            for i in range(90)
        ]
        score = compute_score(
            "BTC",
            "5m",
            PriceSnapshot(price=candles[-1].close, timestamp=0),
            candles,
            candles,
            candles,
            FearGreedSnapshot(value=50, label="Neutral", healthy=False),
            [Headline(title="ETF adoption", source="t"), Headline(title="ETF adoption", source="t")],
            fetch_derivatives_context(_OffBudget()),
            fetch_flow_context(_OffBudget()),
            {"spx": candles, "vix": candles, "nq": candles},
        )
        self.assertIn(score.direction, {"LONG", "NEUTRAL"})


class AlertStateTests(unittest.TestCase):
    def test_non_btc_uses_real_price_for_tp1_transition(self):
        with tempfile.TemporaryDirectory() as d:
            store = AlertStateStore(f"{d}/state.json")
            mock_score = Mock()
            mock_score.action = "TRADE"
            mock_score.symbol = "SPX_PROXY"
            mock_score.timeframe = "5m"
            mock_score.tier = "A+"
            mock_score.lifecycle_key = "spx:5m:test"
            mock_score.direction = "LONG"
            mock_score.tp1 = 5010.0

            self.assertTrue(store.should_send(mock_score, 5000.0))
            store.save(mock_score, 5000.0)
            self.assertFalse(store.should_send(mock_score, 5000.0))
            self.assertTrue(store.should_send(mock_score, 5011.0))


    def test_corrupt_state_file_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            path = f"{d}/state.json"
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken")
            store = AlertStateStore(path)
            self.assertEqual(store.state, {})

    def test_payload_contract(self):
        score = Mock()
        score.symbol = "BTC"
        score.timeframe = "5m"
        score.action = "WATCH"
        score.tier = "B"
        score.direction = "LONG"
        score.strategy_type = "BREAKOUT"
        score.confidence = 61
        score.entry_zone = "1-2"
        score.invalidation = 1.0
        score.tp1 = 2.0
        score.tp2 = 3.0
        score.rr_ratio = 1.4
        score.regime = "trend"
        score.session = "us"
        score.quality = "ok"
        score.reason_codes = ["EMA_BULL"]
        score.score_breakdown = {"momentum": 1}
        score.blockers = []
        score.decision_trace = {"candidates": {"BREAKOUT_LONG": 12}}

        body = _format_alert(score, {"price": "kraken", "derivatives": "bybit", "flows": "bybit", "spx_mode": "n/a"})
        payload = json.loads(body.split("```", maxsplit=2)[1])
        for key in [
            "symbol",
            "timeframe",
            "action",
            "tier",
            "direction",
            "strategy_type",
            "confidence_score",
            "entry_zone",
            "invalidation_level",
            "tp1",
            "tp2",
            "rr_ratio",
            "context",
            "reason_codes",
            "score_breakdown",
            "blockers",
            "decision_trace",
        ]:
            self.assertIn(key, payload)

        providers = payload["context"]["providers"]
        for pkey in ["price", "derivatives", "flows", "spx_mode"]:
            self.assertIn(pkey, providers)


class ReplayTests(unittest.TestCase):
    def test_replay_outputs_metrics(self):
        now = int(time.time()) - (120 * 300)
        candles = [
            Candle(str(now + (i * 300)), 100 + i * 0.1, 101 + i * 0.1, 99 + i * 0.1, 100.4 + i * 0.1, 100 + i)
            for i in range(130)
        ]
        metrics = replay_symbol_timeframe("BTC", "5m", candles)
        self.assertGreaterEqual(metrics.alerts, 0)
        self.assertGreaterEqual(metrics.trades, 0)
        self.assertIn(metrics.horizon_bars, {1, 2, 3})
        summary = summarize({"btc": metrics})
        self.assertIn("horizon_bars", summary["btc"])


class ConfigAndRetryTests(unittest.TestCase):
    def test_unknown_timeframe_does_not_crash(self):
        now = int(time.time()) - (90 * 300)
        candles = [
            Candle(str(now + (i * 300)), 100 + i, 101 + i, 99 + i, 100.5 + i, 100 + i)
            for i in range(90)
        ]
        score = compute_score(
            "BTC",
            "2m",
            PriceSnapshot(price=candles[-1].close, timestamp=0),
            candles,
            candles,
            candles,
            FearGreedSnapshot(value=50, label="Neutral", healthy=False),
            [],
            fetch_derivatives_context(_OffBudget()),
            fetch_flow_context(_OffBudget()),
            {"spx": candles, "vix": candles, "nq": candles},
        )
        self.assertIn(score.action, {"TRADE", "WATCH", "SKIP"})

    @patch("collectors.base.httpx.get")
    def test_retry_non_retriable_403(self, mock_get):
        resp = Mock()
        req = httpx.Request("GET", "https://example.com")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("forbidden", request=req, response=Mock(status_code=403))
        mock_get.return_value = resp
        with self.assertRaises(httpx.HTTPStatusError):
            request_json("https://example.com")
        self.assertEqual(mock_get.call_count, 1)

    @patch("collectors.base.time.sleep")
    @patch("collectors.base.httpx.get")
    def test_retry_retriable_500(self, mock_get, _sleep):
        req = httpx.Request("GET", "https://example.com")
        bad = Mock()
        bad.raise_for_status.side_effect = httpx.HTTPStatusError("server", request=req, response=Mock(status_code=500))
        good = Mock()
        good.raise_for_status.return_value = None
        good.json.return_value = {"ok": True}
        mock_get.side_effect = [bad, good]
        payload = request_json("https://example.com")
        self.assertTrue(payload["ok"])
        self.assertEqual(mock_get.call_count, 2)

    def test_validate_config(self):
        validate_config()


    def test_validate_config_rejects_invalid_rules(self):
        original_rules = copy.deepcopy(TIMEFRAME_RULES)
        try:
            TIMEFRAME_RULES["5m"]["trade_long"] = TIMEFRAME_RULES["5m"]["watch_long"]
            with self.assertRaises(ValueError):
                validate_config()
        finally:
            TIMEFRAME_RULES.clear()
            TIMEFRAME_RULES.update(original_rules)


class _OffBudget:
    def can_call(self, source):
        return False

    def record_call(self, source):
        return None


        base = compute_score(
            "BTC", "5m", price, c5, c15, c1h, fg, [], fetch_derivatives_context(_OffBudget()), fetch_flow_context(_OffBudget()), macro
        )
        with_news = compute_score(
            "BTC",
            "5m",
            price,
            c5,
            c15,
            c1h,
            fg,
            [Headline(title="Major exchange hack triggers panic", source="test")],
            fetch_derivatives_context(_OffBudget()),
            fetch_flow_context(_OffBudget()),
            macro,
        )
        self.assertLess(with_news.confidence, base.confidence)

    def test_stale_candles_block_signal(self):
        stale_end = int(time.time()) - (4 * 3600)
        stale_start = stale_end - (89 * 300)
        c5 = [Candle(str(stale_start + (i * 300)), 100 + i, 101 + i, 99 + i, 100.5 + i, 100 + i) for i in range(90)]
        macro = {"spx": c5, "vix": list(reversed(c5)), "nq": c5}

        score = compute_score(
            "BTC",
            "5m",
            PriceSnapshot(price=c5[-1].close, timestamp=0),
            c5,
            c5,
            c5,
            FearGreedSnapshot(value=30, label="Fear", healthy=True),
            [],
            fetch_derivatives_context(_OffBudget()),
            fetch_flow_context(_OffBudget()),
            macro,
        )

        self.assertIn("Stale market data", score.blockers)
        self.assertEqual(score.action, "SKIP")


class AlertStateTests(unittest.TestCase):
    def test_non_btc_uses_real_price_for_tp1_transition(self):
        with tempfile.TemporaryDirectory() as d:
            store = AlertStateStore(f"{d}/state.json")
            mock_score = Mock()
            mock_score.action = "TRADE"
            mock_score.symbol = "SPX_PROXY"
            mock_score.timeframe = "5m"
            mock_score.tier = "A+"
            mock_score.lifecycle_key = "spx:5m:test"
            mock_score.direction = "LONG"
            mock_score.tp1 = 5010.0

            self.assertTrue(store.should_send(mock_score, 5000.0))
            store.save(mock_score, 5000.0)
            self.assertFalse(store.should_send(mock_score, 5000.0))
            self.assertTrue(store.should_send(mock_score, 5011.0))

    def test_payload_contract(self):
        score = Mock()
        score.symbol = "BTC"
        score.timeframe = "5m"
        score.action = "WATCH"
        score.tier = "B"
        score.direction = "LONG"
        score.strategy_type = "BREAKOUT"
        score.confidence = 61
        score.entry_zone = "1-2"
        score.invalidation = 1.0
        score.tp1 = 2.0
        score.tp2 = 3.0
        score.rr_ratio = 1.4
        score.regime = "trend"
        score.session = "us"
        score.quality = "ok"
        score.reason_codes = ["EMA_BULL"]
        score.score_breakdown = {"momentum": 1}
        score.blockers = []
        score.decision_trace = {"candidates": {"BREAKOUT_LONG": 12}}

        body = _format_alert(score, {"price": "kraken", "derivatives": "bybit", "flows": "bybit", "spx_mode": "n/a"})
        payload = json.loads(body.split("```", maxsplit=2)[1])
        for key in [
            "symbol",
            "timeframe",
            "action",
            "tier",
            "direction",
            "strategy_type",
            "confidence_score",
            "entry_zone",
            "invalidation_level",
            "tp1",
            "tp2",
            "rr_ratio",
            "context",
            "reason_codes",
            "score_breakdown",
            "blockers",
            "decision_trace",
        ]:
            self.assertIn(key, payload)

        providers = payload["context"]["providers"]
        for pkey in ["price", "derivatives", "flows", "spx_mode"]:
            self.assertIn(pkey, providers)


class ReplayTests(unittest.TestCase):
    def test_replay_outputs_metrics(self):
        now = int(time.time()) - (120 * 300)
        candles = [
            Candle(str(now + (i * 300)), 100 + i * 0.1, 101 + i * 0.1, 99 + i * 0.1, 100.4 + i * 0.1, 100 + i)
            for i in range(130)
        ]
        metrics = replay_symbol_timeframe("BTC", "5m", candles)
        self.assertGreaterEqual(metrics.alerts, 0)
        self.assertGreaterEqual(metrics.trades, 0)


class ConfigAndRetryTests(unittest.TestCase):
    def test_unknown_timeframe_does_not_crash(self):
        now = int(time.time()) - (90 * 300)
        candles = [
            Candle(str(now + (i * 300)), 100 + i, 101 + i, 99 + i, 100.5 + i, 100 + i)
            for i in range(90)
        ]
        score = compute_score(
            "BTC",
            "2m",
            PriceSnapshot(price=candles[-1].close, timestamp=0),
            candles,
            candles,
            candles,
            FearGreedSnapshot(value=50, label="Neutral", healthy=False),
            [],
            fetch_derivatives_context(_OffBudget()),
            fetch_flow_context(_OffBudget()),
            {"spx": candles, "vix": candles, "nq": candles},
        )
        self.assertIn(score.action, {"TRADE", "WATCH", "SKIP"})

    @patch("collectors.base.httpx.get")
    def test_retry_non_retriable_403(self, mock_get):
        resp = Mock()
        req = httpx.Request("GET", "https://example.com")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("forbidden", request=req, response=Mock(status_code=403))
        mock_get.return_value = resp
        with self.assertRaises(httpx.HTTPStatusError):
            request_json("https://example.com")
        self.assertEqual(mock_get.call_count, 1)

    @patch("collectors.base.time.sleep")
    @patch("collectors.base.httpx.get")
    def test_retry_retriable_500(self, mock_get, _sleep):
        req = httpx.Request("GET", "https://example.com")
        bad = Mock()
        bad.raise_for_status.side_effect = httpx.HTTPStatusError("server", request=req, response=Mock(status_code=500))
        good = Mock()
        good.raise_for_status.return_value = None
        good.json.return_value = {"ok": True}
        mock_get.side_effect = [bad, good]
        payload = request_json("https://example.com")
        self.assertTrue(payload["ok"])
        self.assertEqual(mock_get.call_count, 2)

    def test_validate_config(self):
        validate_config()



class _OffBudget:
    def can_call(self, source):
        return False

    def record_call(self, source):
        return None


class CollectorTests(unittest.TestCase):
    @patch("collectors.derivatives.request_json")
    def test_derivatives_bybit_parse(self, mock_request_json):
        mock_request_json.side_effect = [
            {"result": {"list": [{"markPrice": "60000", "indexPrice": "59800", "fundingRate": "0.0005"}]}},
            {"result": {"list": [{"openInterest": "110"}, {"openInterest": "100"}]}},
        ]

        class _Budget:
            def can_call(self, source):
                return source == "bybit"

            def record_call(self, source):
                return None

        snap = fetch_derivatives_context(_Budget())
        self.assertTrue(snap.healthy)
        self.assertEqual(snap.source, "bybit")
        self.assertGreater(snap.oi_change_pct, 0)


if __name__ == "__main__":
    unittest.main()
