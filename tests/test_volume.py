import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import time
from pathlib import Path
import os

from intelligence.volume import volume_profile
from engine import compute_score, AlertScore
from utils import Candle
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from config import INTELLIGENCE_FLAGS, SQUEEZE, VOLUME_PROFILE

class TestVolumeProfile(unittest.TestCase):

    def setUp(self):
        # Reset INTELLIGENCE_FLAGS to default for each test
        self.original_intelligence_flags = INTELLIGENCE_FLAGS.copy()
        INTELLIGENCE_FLAGS.update({
            "squeeze_enabled": True,
            "volume_profile_enabled": True,
            "liquidity_enabled": True,
            "macro_correlation_enabled": True,
            "sentiment_enabled": True,
            "confluence_enabled": True,
        })
        # Ensure a clean budget.json for budget manager tests if any
        budget_path = Path(".budget.json")
        if budget_path.exists():
            os.remove(budget_path)

    def tearDown(self):
        # Restore original INTELLIGENCE_FLAGS
        INTELLIGENCE_FLAGS.update(self.original_intelligence_flags)
        # Clean up budget.json if created
        budget_path = Path(".budget.json")
        if budget_path.exists():
            os.remove(budget_path)

    def create_mock_candles(self, prices, volumes):
        candles = []
        for i, (price, volume) in enumerate(zip(prices, volumes)):
            candles.append(Candle(
                ts=str(time.time() - (len(prices) - 1 - i) * 60), # Mocking 1-minute candles
                open=price - 1,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=volume
            ))
        return candles

    def test_volume_profile_empty_candles(self):
        result = volume_profile([])
        self.assertEqual(result, {})

    def test_volume_profile_basic_calculation(self):
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
        volumes = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        candles = self.create_mock_candles(prices, volumes)
        
        result = volume_profile(candles, num_buckets=10) # 10 buckets for 10 prices, so each price is a bucket

        self.assertIn('poc_price', result)
        self.assertIn('poc_volume', result)
        self.assertIn('va_high', result)
        self.assertIn('va_low', result)
        self.assertIn('total_volume', result)
        self.assertIn('profile', result)
        
        # In this simple case, the highest volume is at 109, so POC should be 109
        self.assertEqual(result['poc_price'], 109.45)
        self.assertEqual(result['poc_volume'], 100)
        self.assertEqual(result['total_volume'], sum(volumes))

        # Test VA calculation (70% of 550 = 385)
        # The profile is sorted by price. We need to accumulate volume until 385
        # The VA should cover prices 105 to 109
        self.assertAlmostEqual(result['va_high'], 109.45, delta=0.1)
        self.assertAlmostEqual(result['va_low'], 105, delta=0.1)


    def test_volume_profile_with_uneven_distribution(self):
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
        volumes = [10, 10, 10, 100, 10, 10, 10, 10, 10, 10] # POC at 103
        candles = self.create_mock_candles(prices, volumes)

        result = volume_profile(candles, num_buckets=10)
        self.assertEqual(result['poc_price'], 102.85)
        self.assertEqual(result['poc_volume'], 100)
        self.assertEqual(result['total_volume'], sum(volumes))

        # VA calculation for 70% of 190 = 133
        # 103 (100) -> 101, 102, 104, 105 (10+10+10+10=40)
        # So VA should cover 102-104 (120 volume) or 101-105 (140 volume)
        # Given the calculation, it should be around 102-104 or slightly wider.
        # Let's check if the range includes the POC.
        self.assertLessEqual(result['va_low'], 103)
        self.assertGreaterEqual(result['va_high'], 103)

    def test_compute_score_with_volume_profile_bonus(self):
        INTELLIGENCE_FLAGS["volume_profile_enabled"] = True
        
        # Mock IntelBundle with VA and POC that gives bonus
        mock_intel = MagicMock()
        mock_intel.volume_profile = {
            "poc_price": 100.0,
            "poc_volume": 1000.0,
            "va_high": 101.0,
            "va_low": 99.0,
            "total_volume": 2000.0,
            "profile": []
        }
        mock_intel.liquidity = None # Added for compatibility
        mock_intel.liquidity = None # Added for compatibility
        mock_intel.liquidity = None # Added for compatibility

        # Current price within VA and near POC
        mock_btc_price = PriceSnapshot(source='mock', price=100.5, timestamp=time.time())
        mock_fg = FearGreedSnapshot(value=50, label='Neutral')
        mock_news = [Headline(title='test', source='test.com')]
        mock_derivatives = DerivativesSnapshot(funding_rate=0.0001, oi_change_pct=0.0, basis_pct=0.0)
        mock_flows = FlowSnapshot(taker_ratio=1.1, long_short_ratio=1.0, crowding_score=0.0)
        mock_macro = {} # No macro for this test

        # Need to provide some candles for compute_score to work
        mock_candles = self.create_mock_candles([100]*22, [10]*22)

        score: AlertScore = compute_score(
            symbol="BTC/USD",
            timeframe="1h", price=mock_btc_price, fg=mock_fg, news=mock_news,
            derivatives=mock_derivatives, flows=mock_flows, macro=mock_macro,
            candles=mock_candles, candles_15m=[], candles_1h=[], intel=mock_intel
        )
        
        # Check if bonus was applied
        self.assertIn("VP_IN_VA", score.decision_trace["codes"])
        self.assertGreater(score.score_breakdown["momentum"], 0)
        self.assertEqual(score.decision_trace["context"]["vp_in_va"], True)
        self.assertIn("VP_NEAR_POC", score.decision_trace["codes"])

    def test_compute_score_with_volume_profile_penalty(self):
        INTELLIGENCE_FLAGS["volume_profile_enabled"] = True
        
        # Mock IntelBundle with VA and POC that gives penalty
        mock_intel = MagicMock()
        mock_intel.volume_profile = {
            "poc_price": 100.0,
            "poc_volume": 1000.0,
            "va_high": 101.0,
            "va_low": 99.0,
            "total_volume": 2000.0,
            "profile": []
        }
        mock_intel.liquidity = None # Added for compatibility

        # Current price far from POC
        mock_btc_price = PriceSnapshot(source='mock', price=105.0, timestamp=time.time()) # Far from POC 100
        mock_fg = FearGreedSnapshot(value=50, label='Neutral')
        mock_news = [Headline(title='test', source='test.com')]
        mock_derivatives = DerivativesSnapshot(funding_rate=0.0001, oi_change_pct=0.0, basis_pct=0.0)
        mock_flows = FlowSnapshot(taker_ratio=1.1, long_short_ratio=1.0, crowding_score=0.0)
        mock_macro = {}

        mock_candles = self.create_mock_candles([100]*22, [10]*22)

        score: AlertScore = compute_score(
            symbol="BTC/USD",
            timeframe="1h", price=mock_btc_price, fg=mock_fg, news=mock_news,
            derivatives=mock_derivatives, flows=mock_flows, macro=mock_macro,
            candles=mock_candles, candles_15m=[], candles_1h=[], intel=mock_intel
        )
        
        # Check if penalty was applied
        self.assertIn("VP_FAR_FROM_POC", score.decision_trace["codes"])
        self.assertLess(score.score_breakdown["penalty"], 0)
        self.assertEqual(score.decision_trace["context"]["vp_in_va"], False)
        self.assertAlmostEqual(score.decision_trace["context"]["vp_poc_dist_pct"], 0.05, delta=0.001)

    def test_compute_score_volume_profile_disabled(self):
        INTELLIGENCE_FLAGS["volume_profile_enabled"] = False
        
        mock_intel = MagicMock()
        mock_intel.volume_profile = {
            "poc_price": 100.0,
            "poc_volume": 1000.0,
            "va_high": 101.0,
            "va_low": 99.0,
            "total_volume": 2000.0,
            "profile": []
        }
        mock_intel.liquidity = None # Added for compatibility

        mock_btc_price = PriceSnapshot(source='mock', price=100.5, timestamp=time.time())
        mock_fg = FearGreedSnapshot(value=50, label='Neutral')
        mock_news = [Headline(title='test', source='test.com')]
        mock_derivatives = DerivativesSnapshot(funding_rate=0.0001, oi_change_pct=0.0, basis_pct=0.0)
        mock_flows = FlowSnapshot(taker_ratio=1.1, long_short_ratio=1.0, crowding_score=0.0)
        mock_macro = {}

        mock_candles = self.create_mock_candles([100]*22, [10]*22)

        score: AlertScore = compute_score(
            symbol="BTC/USD",
            timeframe="1h",
            price=mock_btc_price,
            fg=mock_fg,
            news=mock_news,
            derivatives=mock_derivatives,
            flows=mock_flows,
            macro=mock_macro,
            candles=mock_candles,
            candles_15m=[],
            candles_1h=[],
            intel=mock_intel
        )
        
        # Ensure no VP related codes or context are added if disabled
        self.assertNotIn("VP_IN_VA", score.decision_trace["codes"])
        self.assertNotIn("VP_FAR_FROM_POC", score.decision_trace["codes"])
        self.assertNotIn("vp_in_va", score.decision_trace["context"])
        self.assertNotIn("vp_poc_dist_pct", score.decision_trace["context"])

if __name__ == '__main__':
    unittest.main()
