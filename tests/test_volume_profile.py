import unittest
from datetime import datetime, timedelta
from collectors.price import Candle
from intelligence.volume_profile import compute_volume_profile

class TestVolumeProfile(unittest.TestCase):

    def _create_mock_candles(self, num_candles, start_price, volatility=0.01, volume=100):
        candles = []
        timestamp = datetime.now()
        price = start_price
        for i in range(num_candles):
            open_price = price
            close_price = price + (volatility * (0.5 - (i % 2)))
            high_price = max(open_price, close_price) + (volatility * 0.1)
            low_price = min(open_price, close_price) - (volatility * 0.1)
            candles.append(Candle(
                ts=str(int(timestamp.timestamp())),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume
            ))
            price = close_price
            timestamp += timedelta(minutes=5)
        return candles

    def test_basic_volume_profile_calculation(self):
        # Create a set of candles with a clear volume concentration
        candles = self._create_mock_candles(50, 100.0, volatility=0.1, volume=100)
        
        # Artificially increase volume in a specific price range to create a POC
        for i in range(15, 25): # Candles 15-24
            candles[i].volume *= 5 # Increase volume significantly
            candles[i].close = 101.0 + (i * 0.01) # Keep prices around 101-102
            candles[i].open = 101.0 + (i * 0.01)
            candles[i].high = 102.0
            candles[i].low = 101.0

        current_price = 101.5 # Within the expected value area

        vp_result = compute_volume_profile(candles, current_price)
        
        self.assertIn("poc", vp_result)
        self.assertIn("va_high", vp_result)
        self.assertIn("va_low", vp_result)
        self.assertIn("position", vp_result)
        self.assertIn("pts", vp_result)

        self.assertIsInstance(vp_result["poc"], float)
        self.assertIsInstance(vp_result["va_high"], float)
        self.assertIsInstance(vp_result["va_low"], float)
        self.assertIsInstance(vp_result["position"], str)
        self.assertIsInstance(vp_result["pts"], float)

        # Check if POC is roughly in the artificially boosted area
        self.assertGreater(vp_result["poc"], 100.0)
        self.assertLess(vp_result["poc"], 102.0)

        # Check value area is reasonable
        self.assertLess(vp_result["va_low"], vp_result["poc"])
        self.assertGreater(vp_result["va_high"], vp_result["poc"])
        self.assertGreater(vp_result["va_high"], vp_result["va_low"])

        # Current price 101.5 should be AT_VALUE
        self.assertEqual(vp_result["position"], "AT_VALUE")
        self.assertEqual(vp_result["pts"], 0.0)

    def test_volume_profile_below_value(self):
        candles = self._create_mock_candles(50, 100.0, volatility=0.1, volume=100)
        for i in range(15, 25):
            candles[i].volume *= 5
            candles[i].close = 105.0 + (i * 0.01)
            candles[i].open = 105.0 + (i * 0.01)
            candles[i].high = 106.0
            candles[i].low = 105.0

        current_price = 103.0 # Significantly below the value area

        vp_result = compute_volume_profile(candles, current_price)
        self.assertEqual(vp_result["position"], "BELOW_VALUE")
        self.assertGreater(vp_result["pts"], 0.0) # Should be positive points for being below value

    def test_volume_profile_above_value(self):
        candles = self._create_mock_candles(50, 100.0, volatility=0.1, volume=100)
        for i in range(15, 25):
            candles[i].volume *= 5
            candles[i].close = 95.0 + (i * 0.01)
            candles[i].open = 95.0 + (i * 0.01)
            candles[i].high = 96.0
            candles[i].low = 95.0
            
        current_price = 98.0 # Significantly above the value area

        vp_result = compute_volume_profile(candles, current_price)
        self.assertEqual(vp_result["position"], "ABOVE_VALUE")
        self.assertLess(vp_result["pts"], 0.0) # Should be negative points for being above value

    def test_insufficient_candles(self):
        candles = self._create_mock_candles(4, 100.0) # Less than 5 candles
        current_price = 100.0
        vp_result = compute_volume_profile(candles, current_price)
        self.assertEqual(vp_result["position"], "UNKNOWN")
        self.assertEqual(vp_result["pts"], 0.0)
        self.assertEqual(vp_result["poc"], 0.0) # Default value for insufficient data

    def test_single_price_candles(self):
        # All candles have the same high, low, open, close
        candles = [Candle(ts=str(int(datetime.now().timestamp())), open=100.0, high=100.0, low=100.0, close=100.0, volume=100) for _ in range(10)]
        current_price = 100.0
        vp_result = compute_volume_profile(candles, current_price)
        self.assertEqual(vp_result["poc"], 100.0)
        self.assertEqual(vp_result["va_high"], 100.0)
        self.assertEqual(vp_result["va_low"], 100.0)
        self.assertEqual(vp_result["position"], "AT_VALUE")
        self.assertEqual(vp_result["pts"], 0.0)

    def test_high_volatility_no_clear_poc(self):
        candles = self._create_mock_candles(100, 100.0, volatility=5.0, volume=100)
        current_price = 100.0
        vp_result = compute_volume_profile(candles, current_price)
        # We expect a POC and VA, but its exact value is hard to predict without running the algo
        self.assertIsNotNone(vp_result["poc"])
        self.assertIsNotNone(vp_result["va_high"])
        self.assertIsNotNone(vp_result["va_low"])
        self.assertIn(vp_result["position"], ["AT_VALUE", "ABOVE_VALUE", "BELOW_VALUE"])
