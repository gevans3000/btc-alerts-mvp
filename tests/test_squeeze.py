import unittest
from datetime import datetime, timedelta
from typing import List
from unittest.mock import MagicMock, patch

from collectors.price import Candle
from config import INTELLIGENCE_FLAGS, SQUEEZE
from engine import AlertScore, compute_score
from intelligence.squeeze import detect_squeeze, keltner_channels
from intelligence import IntelligenceBundle


class TestSqueezeDetector(unittest.TestCase):
    def _create_mock_candles(self, num_candles, start_price, volatility_factor=0.01, trend_factor=0.0):
        candles = []
        timestamp = datetime.now()
        price = start_price
        for i in range(num_candles):
            open_price = price
            close_price = price + (i * trend_factor) + (volatility_factor * (0.5 - (i % 2)))
            high_price = max(open_price, close_price) + (volatility_factor * 0.1)
            low_price = min(open_price, close_price) - (volatility_factor * 0.1)
            candles.append(Candle(
                ts=str(int(timestamp.timestamp())),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=100
            ))
            price = close_price
            timestamp += timedelta(minutes=5)
        return candles

    def test_keltner_channels(self):
        candles = self._create_mock_candles(30, 100.0)
        kc = keltner_channels(candles)
        self.assertIsNotNone(kc)
        self.assertIsInstance(kc, tuple)
        self.assertEqual(len(kc), 3)
        self.assertIsInstance(kc[0], float) # Upper
        self.assertIsInstance(kc[1], float) # Middle
        self.assertIsInstance(kc[2], float) # Lower

        # Test with insufficient candles
        kc_insufficient = keltner_channels(candles[:10])
        self.assertIsNone(kc_insufficient)

    def test_detect_squeeze_none(self):
        # Simulate normal volatility where BB are outside KC
        mock_candles = self._create_mock_candles(22, 100.0) # Need enough for current and previous
        with patch('intelligence.squeeze.bollinger_bands') as mock_bb, \
             patch('intelligence.squeeze.keltner_channels') as mock_kc:
            # Ensure BB are outside KC for both current and previous state
            mock_bb.side_effect = [(103.0, 100.0, 97.0), (103.0, 100.0, 97.0)] # Wider BB
            mock_kc.side_effect = [(102.0, 100.0, 98.0), (102.0, 100.0, 98.0)] # Narrower KC
            
            result = detect_squeeze(mock_candles)
            self.assertEqual(result["state"], "NONE")
            self.assertEqual(result["pts"], 0)
            self.assertIn("bb_width", result)
            self.assertIn("kc_width", result)

    def test_detect_squeeze_on(self):
        # Simulate BB inside KC (Squeeze ON)
        mock_candles = self._create_mock_candles(22, 100.0) # Need enough for current and previous
        with patch('intelligence.squeeze.bollinger_bands') as mock_bb, \
             patch('intelligence.squeeze.keltner_channels') as mock_kc:
            # Ensure BB are inside KC for current state
            mock_bb.side_effect = [(101.0, 100.0, 99.0), (101.0, 100.0, 99.0)] # Narrower BB
            mock_kc.side_effect = [(102.0, 100.0, 98.0), (102.0, 100.0, 98.0)] # Wider KC

            result = detect_squeeze(mock_candles)
            self.assertEqual(result["state"], "SQUEEZE_ON")
            self.assertEqual(result["pts"], 0)

    def test_detect_squeeze_fire(self):
        # Simulate a squeeze firing (Previous: ON, Current: OFF)
        mock_candles = self._create_mock_candles(23, 100.0) # Need enough for current and previous
        with patch('intelligence.squeeze.bollinger_bands') as mock_bb, \
             patch('intelligence.squeeze.keltner_channels') as mock_kc:
            # Previous state: Squeeze ON (BB inside KC)
            # Current state: Squeeze OFF (BB outside KC)
            mock_bb.side_effect = [
                (102.0, 100.0, 98.0), # current_bb (wider)
                (101.0, 100.0, 99.0), # prev_bb (narrower)
            ]
            mock_kc.side_effect = [
                (101.0, 100.0, 99.0), # current_kc (narrower)
                (102.0, 100.0, 98.0), # prev_kc (wider)
            ]

            result = detect_squeeze(mock_candles)
            self.assertEqual(result["state"], "SQUEEZE_FIRE")
            self.assertEqual(result["pts"], SQUEEZE["fire_bonus_pts"])


    def test_detect_squeeze_insufficient_candles(self):
        candles = self._create_mock_candles(20, 100.0) # Less than 22
        result = detect_squeeze(candles)
        self.assertEqual(result["state"], "NONE")
        self.assertEqual(result["pts"], 0)

    @patch('intelligence.squeeze.bollinger_bands')
    @patch('intelligence.squeeze.keltner_channels')
    def test_detect_squeeze_none_on_indicator_none(self, mock_kc, mock_bb):
        mock_bb.return_value = None
        mock_kc.return_value = (100, 99, 98) # KC can be valid
        candles = self._create_mock_candles(30, 100.0)
        result = detect_squeeze(candles)
        self.assertEqual(result["state"], "NONE")

        mock_bb.return_value = (100, 99, 98) # BB can be valid
        mock_kc.return_value = None
        result = detect_squeeze(candles)
        self.assertEqual(result["state"], "NONE")

    @patch('intelligence.squeeze.bollinger_bands')
    @patch('intelligence.squeeze.keltner_channels')
    def test_detect_squeeze_keys(self, mock_kc, mock_bb):
        mock_bb.return_value = (101.0, 100.0, 99.0)
        mock_kc.return_value = (102.0, 100.0, 98.0)
        candles = self._create_mock_candles(30, 100.0)
        result = detect_squeeze(candles)
        self.assertIsInstance(result, dict)
        self.assertIn("state", result)
        self.assertIn("pts", result)
        self.assertIn("bb_width", result)
        self.assertIn("kc_width", result)

    @patch('app.logger')
    def test_compute_score_with_squeeze_intel(self, mock_app_logger):
        # Mock dependencies for compute_score
        mock_bm = MagicMock()
        mock_btc_price = MagicMock(spec=Candle, price=100.0, healthy=True)
        mock_fg = MagicMock(healthy=True, value=10) # Configure for fg.healthy and fg.value
        mock_news = []
        mock_derivatives = MagicMock(healthy=True, oi_change_pct=0.8, basis_pct=0.1) # Configure for derivatives.healthy, oi_change_pct, basis_pct
        mock_flows = MagicMock(healthy=True, crowding_score=5) # Configure for flows.healthy and crowding_score
        mock_macro = {}

        # Simulate candles for detect_squeeze
        candles = self._create_mock_candles(30, 100.0)
        btc_tf_mock = {
            "5m": candles,
            "15m": self._create_mock_candles(30, 100.0),
            "1h": self._create_mock_candles(30, 100.0),
        }

        # Mock detect_squeeze to return a SQUEEZE_FIRE state
        mock_detect_squeeze_fire_value = {
            "state": "SQUEEZE_FIRE",
            "pts": SQUEEZE["fire_bonus_pts"],
            "bb_width": 0.1,
            "kc_width": 0.2
        }
        mock_detect_squeeze_on_value = {
            "state": "SQUEEZE_ON",
            "pts": 0,
            "bb_width": 0.1,
            "kc_width": 0.2
        }

        with patch('intelligence.squeeze.detect_squeeze') as mock_detect_squeeze:
            # Test with SQUEEZE_FIRE
            mock_detect_squeeze.return_value = mock_detect_squeeze_fire_value
            
            # Ensure INTELLIGENCE_FLAGS is enabled
            INTELLIGENCE_FLAGS["squeeze_enabled"] = True

            # Manually create the IntelligenceBundle and pass it
            intel_bundle = IntelligenceBundle()
            if INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
                intel_bundle.squeeze = mock_detect_squeeze(candles) # Call it with actual candles for this test

            # Call compute_score directly
            score = compute_score(
                symbol="BTC",
                timeframe="5m",
                price=mock_btc_price,
                candles=candles,
                candles_15m=btc_tf_mock["15m"],
                candles_1h=btc_tf_mock["1h"],
                fg=mock_fg,
                news=mock_news,
                derivatives=mock_derivatives,
                flows=mock_flows,
                macro=mock_macro,
                intel=intel_bundle,
            )

            self.assertIsInstance(score, AlertScore)
            self.assertIn("SQUEEZE_FIRE", score.reason_codes)
            self.assertEqual(score.decision_trace["context"]["squeeze"], "SQUEEZE_FIRE")
            self.assertGreaterEqual(score.score_breakdown["volatility"], SQUEEZE["fire_bonus_pts"]) # Should have bonus points

            # Test with SQUEEZE_ON
            mock_detect_squeeze.return_value = mock_detect_squeeze_on_value

            intel_bundle = IntelligenceBundle()
            if INTELLIGENCE_FLAGS.get("squeeze_enabled", True):
                intel_bundle.squeeze = mock_detect_squeeze(candles)

            score_on = compute_score(
                symbol="BTC",
                timeframe="5m",
                price=mock_btc_price,
                candles=candles,
                candles_15m=btc_tf_mock["15m"],
                candles_1h=btc_tf_mock["1h"],
                fg=mock_fg,
                news=mock_news,
                derivatives=mock_derivatives,
                flows=mock_flows,
                macro=mock_macro,
                intel=intel_bundle,
            )
            self.assertIn("SQUEEZE_ON", score_on.reason_codes)
            self.assertEqual(score_on.decision_trace["context"]["squeeze"], "SQUEEZE_ON")
            # Ensure volatility points are not added for SQUEEZE_ON
            # We need to consider other factors that might add to volatility, so check it's not increased by SQUEEZE_FIRE pts
            self.assertLess(score_on.score_breakdown["volatility"], SQUEEZE["fire_bonus_pts"])

            # Test when squeeze_enabled is False
            INTELLIGENCE_FLAGS["squeeze_enabled"] = False
            intel_bundle = IntelligenceBundle()
            if INTELLIGENCE_FLAGS.get("squeeze_enabled", True): # This block will not execute
                intel_bundle.squeeze = mock_detect_squeeze(candles)

            score_disabled = compute_score(
                symbol="BTC",
                timeframe="5m",
                price=mock_btc_price,
                candles=candles,
                candles_15m=btc_tf_mock["15m"],
                candles_1h=btc_tf_mock["1h"],
                fg=mock_fg,
                news=mock_news,
                derivatives=mock_derivatives,
                flows=mock_flows,
                macro=mock_macro,
                intel=intel_bundle,
            )
            self.assertNotIn("SQUEEZE_FIRE", score_disabled.reason_codes)
            self.assertNotIn("SQUEEZE_ON", score_disabled.reason_codes)
            self.assertNotIn("squeeze", score_disabled.context)
            INTELLIGENCE_FLAGS["squeeze_enabled"] = True # Reset for other tests

