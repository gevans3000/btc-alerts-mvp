import unittest

from collectors.derivatives import DerivativesSnapshot
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot
from engine import compute_score
from utils import Candle, atr, ema, percentile_rank, rsi


class UtilsTests(unittest.TestCase):
    def test_ema_and_rsi(self):
        values = [100 + i for i in range(30)]
        self.assertIsNotNone(ema(values, 9))
        self.assertGreater(rsi(values, 14), 50)

    def test_atr_and_percentile(self):
        candles = [Candle(str(i), 100 + i, 101 + i, 99 + i, 100.5 + i, 10) for i in range(30)]
        self.assertGreater(atr(candles, 14), 0)
        self.assertEqual(percentile_rank([1, 2, 3, 4], 3), 75.0)


class EngineTests(unittest.TestCase):
    def _candles(self, start=100, n=90, step=0.8):
        rows = []
        px = start
        for i in range(n):
            op = px
            cl = px + step
            hi = max(op, cl) + 0.4
            lo = min(op, cl) - 0.4
            rows.append(Candle(str(i), op, hi, lo, cl, 100 + i))
            px = cl
        return rows

    def test_compute_score_runs_and_outputs_levels(self):
        candles_5m = self._candles()
        candles_15m = self._candles(start=100, n=80, step=1.2)
        candles_1h = self._candles(start=100, n=80, step=1.5)
        price = PriceSnapshot(price=candles_5m[-1].close, timestamp=0)
        fg = FearGreedSnapshot(value=30, label="Fear", healthy=True)
        derivatives = DerivativesSnapshot(funding_rate=0.0002, oi_change_pct=0.9, basis_pct=0.05, healthy=True)

        score = compute_score(price, candles_5m, candles_15m, candles_1h, fg, [], derivatives, [])

        self.assertIn(score.regime, {"long_signal", "short_signal", "bullish_bias", "bearish_bias", "neutral"})
        self.assertGreaterEqual(score.confidence, 0)
        self.assertLessEqual(score.confidence, 100)
        self.assertNotEqual(score.entry_zone, "")


if __name__ == "__main__":
    unittest.main()
