import unittest
from unittest.mock import Mock, patch

from collectors.derivatives import fetch_derivatives_context
from collectors.flows import fetch_flow_context
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot
from engine import compute_score
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


class _OffBudget:
    def can_call(self, source):
        return False

    def record_call(self, source):
        return None


class CollectorTests(unittest.TestCase):
    @patch("collectors.derivatives.httpx.get")
    def test_derivatives_bybit_parse(self, mock_get):
        ticker_resp = Mock()
        ticker_resp.raise_for_status = Mock()
        ticker_resp.json.return_value = {"result": {"list": [{"markPrice": "60000", "indexPrice": "59800", "fundingRate": "0.0005"}]}}
        oi_resp = Mock()
        oi_resp.raise_for_status = Mock()
        oi_resp.json.return_value = {"result": {"list": [{"openInterest": "110"}, {"openInterest": "100"}]}}
        mock_get.side_effect = [ticker_resp, oi_resp]

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
