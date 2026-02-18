import unittest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
import time
from typing import List, Tuple, Dict, Any, Optional

# Import the necessary components
from collectors.orderbook import OrderBookSnapshot, get_orderbook_snapshot
from intelligence.liquidity import analyze_liquidity
from intelligence import IntelligenceBundle
from engine import compute_score, AlertScore
from config import LIQUIDITY, INTELLIGENCE_FLAGS, TIMEFRAME_RULES, REGIME, DETECTORS, STALE_SECONDS, SESSION_WEIGHTS, CONFLUENCE_RULES, TP_MULTIPLIERS

# Mock AlertScore dependencies
@dataclass
class Candle:
    ts: str # Changed from timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class PriceSnapshot:
    price: float
    timestamp: float
    symbol: str

@dataclass
class FearGreedSnapshot:
    value: int
    label: str
    healthy: bool = True

@dataclass
class Headline:
    title: str
    summary: str
    source: str
    timestamp: float
    score: float
    groups: List[str]

@dataclass
class DerivativesSnapshot:
    funding_rate: float
    oi_change_pct: float
    basis_pct: float
    source: str = "none"
    healthy: bool = True

@dataclass
class FlowSnapshot:
    taker_ratio: float
    long_short_ratio: float
    crowding_score: float
    healthy: bool = True
    source: str = "none"

class TestLiquidityIntelligence(unittest.TestCase):

    def setUp(self):
        # Reset config flags for isolated testing
        self.original_liquidity_config = LIQUIDITY.copy()
        self.original_intelligence_flags = INTELLIGENCE_FLAGS.copy()
        
        # Ensure liquidity is enabled by default for these tests
        INTELLIGENCE_FLAGS["liquidity_enabled"] = True

        # Mock dependencies for compute_score that are not directly related to liquidity
        self.mock_price_snapshot = PriceSnapshot(price=100.0, timestamp=time.time(), symbol="BTC")
        self.mock_candles = [
            Candle(ts=str(int(time.time() - 60 * i)), open=90 + i, high=91 + i, low=89 + i, close=90.5 + i, volume=100) for i in range(100, 0, -1)
        ] # Enough candles for regime calc
        self.mock_candles_15m = self.mock_candles
        self.mock_candles_1h = self.mock_candles
        self.mock_fg_snapshot = FearGreedSnapshot(value=50, label="Neutral", healthy=True)
        self.mock_news = []
        self.mock_derivatives = DerivativesSnapshot(funding_rate=0.001, oi_change_pct=0.0, basis_pct=0.0, source="mock", healthy=True)
        self.mock_flows = FlowSnapshot(taker_ratio=1.0, long_short_ratio=1.0, crowding_score=0.0, healthy=True, source="mock")
        self.mock_macro = {} # Not used in liquidity tests directly

        # Mock the `_calculate_raw_regime` and `_regime` functions in engine.py
        # as their internal logic is complex and not the focus of these tests.
        # We want to ensure they return a predictable value.
        patcher_raw_regime = patch('engine._calculate_raw_regime', return_value="range")
        patcher_regime = patch('engine._regime', return_value=("range", 0.0, ["REGIME_RANGE"]))
        patcher_detector_candidates = patch('engine._detector_candidates', return_value=({}, [], []))
        patcher_arbitrate_candidates = patch('engine._arbitrate_candidates', return_value=(0.0, "NONE", [], 0.0))
        patcher_is_stale = patch('engine._is_stale', return_value=False)
        patcher_tier_and_action = patch('engine._tier_and_action', return_value=("B", "WATCH"))


        self.mock_raw_regime = patcher_raw_regime.start()
        self.mock_regime = patcher_regime.start()
        self.mock_detector_candidates = patcher_detector_candidates.start()
        self.mock_arbitrate_candidates = patcher_arbitrate_candidates.start()
        self.mock_is_stale = patcher_is_stale.start()
        self.mock_tier_and_action = patcher_tier_and_action.start()

        self.addCleanup(patcher_raw_regime.stop)
        self.addCleanup(patcher_regime.stop)
        self.addCleanup(patcher_detector_candidates.stop)
        self.addCleanup(patcher_arbitrate_candidates.stop)
        self.addCleanup(patcher_is_stale.stop)
        self.addCleanup(patcher_tier_and_action.stop)

    def tearDown(self):
        # Restore original config flags
        LIQUIDITY.clear()
        LIQUIDITY.update(self.original_liquidity_config)
        INTELLIGENCE_FLAGS.clear()
        INTELLIGENCE_FLAGS.update(self.original_intelligence_flags)

    # --- Tests for analyze_liquidity function ---
    def test_analyze_liquidity_healthy_balanced(self):
        # Mock a balanced order book
        mock_orderbook = OrderBookSnapshot(
            source="test", timestamp=time.time(), symbol="BTC",
            bids=[(99.9, 100), (99.8, 100)],
            asks=[(100.1, 100), (100.2, 100)],
            is_healthy=True
        )
        result = analyze_liquidity(mock_orderbook, depth_pct=0.01)
        self.assertTrue(result["is_healthy"])
        self.assertAlmostEqual(result["imbalance"], 0.0)
        self.assertEqual(len(result["walls"]), 0) # No walls with default threshold
        self.assertGreater(result["total_bid_volume"], 0)
        self.assertGreater(result["total_ask_volume"], 0)

    def test_analyze_liquidity_healthy_bid_imbalance(self):
        # Mock a bid-heavy order book
        mock_orderbook = OrderBookSnapshot(
            source="test", timestamp=time.time(), symbol="BTC",
            bids=[(99.9, 200), (99.8, 200)], # Heavier bids
            asks=[(100.1, 100), (100.2, 100)],
            is_healthy=True
        )
        result = analyze_liquidity(mock_orderbook, depth_pct=0.01)
        self.assertTrue(result["is_healthy"])
        self.assertGreater(result["imbalance"], 0.0) # Positive imbalance
        self.assertLessEqual(result["imbalance"], 1.0)
        self.assertEqual(len(result["walls"]), 2) # Walls detected based on placeholder threshold > 100
        self.assertEqual(result["walls"][0]["side"], "buy")
        self.assertEqual(result["walls"][1]["side"], "buy")

    def test_analyze_liquidity_healthy_ask_imbalance(self):
        # Mock an ask-heavy order book
        mock_orderbook = OrderBookSnapshot(
            source="test", timestamp=time.time(), symbol="BTC",
            bids=[(99.9, 100), (99.8, 100)],
            asks=[(100.1, 200), (100.2, 200)], # Heavier asks
            is_healthy=True
        )
        result = analyze_liquidity(mock_orderbook, depth_pct=0.01)
        self.assertTrue(result["is_healthy"])
        self.assertLess(result["imbalance"], 0.0) # Negative imbalance
        self.assertGreaterEqual(result["imbalance"], -1.0)
        self.assertEqual(len(result["walls"]), 2) # Walls detected
        self.assertEqual(result["walls"][0]["side"], "sell")
        self.assertEqual(result["walls"][1]["side"], "sell")

    def test_analyze_liquidity_unhealthy_orderbook(self):
        # Mock an unhealthy order book
        mock_orderbook = OrderBookSnapshot(
            source="test", timestamp=time.time(), symbol="BTC",
            bids=[], asks=[], is_healthy=False, message="No data"
        )
        result = analyze_liquidity(mock_orderbook, depth_pct=0.01)
        self.assertFalse(result["is_healthy"])
        self.assertEqual(result["message"], "No data")
        self.assertEqual(result["imbalance"], 0.0)
        self.assertEqual(len(result["walls"]), 0)

    def test_analyze_liquidity_empty_orderbook(self):
        # Mock an empty but healthy order book
        mock_orderbook = OrderBookSnapshot(
            source="test", timestamp=time.time(), symbol="BTC",
            bids=[], asks=[], is_healthy=True
        )
        result = analyze_liquidity(mock_orderbook, depth_pct=0.01)
        self.assertFalse(result["is_healthy"])
        self.assertEqual(result["message"], "Order book data not healthy or empty.")
        self.assertEqual(result["imbalance"], 0.0)
        self.assertEqual(len(result["walls"]), 0)

    # --- Tests for compute_score integration with liquidity ---
    def test_compute_score_liquidity_healthy_bid_imbalance_bonus(self):
        # Setup liquidity with significant bid imbalance
        liquidity_intel = {
            "is_healthy": True,
            "total_bid_volume": 1000.0,
            "total_ask_volume": 200.0,
            "imbalance": 0.67, # (1000-200)/(1000+200) = 800/1200 = 0.666...
            "walls": [],
            "mid_price": 100.0
        }
        intel_bundle = IntelligenceBundle(liquidity=liquidity_intel)

        # Ensure imbalance threshold is met
        LIQUIDITY["imbalance_threshold"] = 0.6
        LIQUIDITY["imbalance_bonus_pts"] = 5.0

        score_result = compute_score(
            symbol="BTC",
            timeframe="5m",
            price=self.mock_price_snapshot,
            candles=self.mock_candles,
            candles_15m=self.mock_candles_15m,
            candles_1h=self.mock_candles_1h,
            fg=self.mock_fg_snapshot,
            news=self.mock_news,
            derivatives=self.mock_derivatives,
            flows=self.mock_flows,
            macro=self.mock_macro,
            intel=intel_bundle
        )
        # Check if bonus points for bid imbalance were added to 'volume' breakdown
        self.assertIn("LIQUIDITY_BID_IMBALANCE", score_result.decision_trace["codes"])
        self.assertAlmostEqual(score_result.score_breakdown["volume"], LIQUIDITY["imbalance_bonus_pts"])
        self.assertIn("liquidity_imbalance", score_result.decision_trace["context"])
        self.assertAlmostEqual(score_result.decision_trace["context"]["liquidity_imbalance"], liquidity_intel["imbalance"])

    def test_compute_score_liquidity_healthy_ask_imbalance_penalty(self):
        # Setup liquidity with significant ask imbalance
        liquidity_intel = {
            "is_healthy": True,
            "total_bid_volume": 200.0,
            "total_ask_volume": 1000.0,
            "imbalance": -0.67,
            "walls": [],
            "mid_price": 100.0
        }
        intel_bundle = IntelligenceBundle(liquidity=liquidity_intel)

        # Ensure imbalance threshold is met
        LIQUIDITY["imbalance_threshold"] = 0.6
        LIQUIDITY["imbalance_bonus_pts"] = 5.0 # This will be subtracted for ask imbalance

        score_result = compute_score(
            symbol="BTC",
            timeframe="5m",
            price=self.mock_price_snapshot,
            candles=self.mock_candles,
            candles_15m=self.mock_candles_15m,
            candles_1h=self.mock_candles_1h,
            fg=self.mock_fg_snapshot,
            news=self.mock_news,
            derivatives=self.mock_derivatives,
            flows=self.mock_flows,
            macro=self.mock_macro,
            intel=intel_bundle
        )
        # Check if bonus points for ask imbalance were subtracted from 'volume' breakdown
        self.assertIn("LIQUIDITY_ASK_IMBALANCE", score_result.decision_trace["codes"])
        self.assertAlmostEqual(score_result.score_breakdown["volume"], -LIQUIDITY["imbalance_bonus_pts"])
        self.assertIn("liquidity_imbalance", score_result.decision_trace["context"])
        self.assertAlmostEqual(score_result.decision_trace["context"]["liquidity_imbalance"], liquidity_intel["imbalance"])

    def test_compute_score_liquidity_unhealthy(self):
        # Setup unhealthy liquidity intelligence
        liquidity_intel = {
            "is_healthy": False,
            "message": "Order book data not healthy or empty.",
            "total_bid_volume": 0.0,
            "total_ask_volume": 0.0,
            "imbalance": 0.0,
            "walls": [],
            "mid_price": 100.0
        }
        intel_bundle = IntelligenceBundle(liquidity=liquidity_intel)

        score_result = compute_score(
            symbol="BTC",
            timeframe="5m",
            price=self.mock_price_snapshot,
            candles=self.mock_candles,
            candles_15m=self.mock_candles_15m,
            candles_1h=self.mock_candles_1h,
            fg=self.mock_fg_snapshot,
            news=self.mock_news,
            derivatives=self.mock_derivatives,
            flows=self.mock_flows,
            macro=self.mock_macro,
            intel=intel_bundle
        )
        # Check if a blocker was added
        self.assertIn("Unhealthy liquidity data", score_result.blockers)
        self.assertIn("LIQUIDITY_UNHEALTHY", score_result.decision_trace["codes"])
        # No score changes from liquidity if unhealthy
        self.assertAlmostEqual(score_result.score_breakdown["volume"], 0.0)

    def test_compute_score_liquidity_disabled(self):
        # Disable liquidity flag
        INTELLIGENCE_FLAGS["liquidity_enabled"] = False
        
        liquidity_intel = { # This data should be ignored
            "is_healthy": True, "total_bid_volume": 1000.0, "total_ask_volume": 200.0,
            "imbalance": 0.67, "walls": [], "mid_price": 100.0
        }
        intel_bundle = IntelligenceBundle(liquidity=liquidity_intel)

        score_result = compute_score(
            symbol="BTC",
            timeframe="5m",
            price=self.mock_price_snapshot,
            candles=self.mock_candles,
            candles_15m=self.mock_candles_15m,
            candles_1h=self.mock_candles_1h,
            fg=self.mock_fg_snapshot,
            news=self.mock_news,
            derivatives=self.mock_derivatives,
            flows=self.mock_flows,
            macro=self.mock_macro,
            intel=intel_bundle
        )
        # No score changes from liquidity if disabled
        self.assertNotIn("LIQUIDITY_BID_IMBALANCE", score_result.decision_trace["codes"])
        self.assertNotIn("LIQUIDITY_ASK_IMBALANCE", score_result.decision_trace["codes"])
        self.assertAlmostEqual(score_result.score_breakdown["volume"], 0.0)
        self.assertNotIn("liquidity_imbalance", score_result.decision_trace["context"])
        self.assertNotIn("liquidity_walls", score_result.decision_trace["context"])

    def test_compute_score_liquidity_with_buy_wall_bonus(self):
        # Setup liquidity with a buy wall
        liquidity_intel = {
            "is_healthy": True,
            "total_bid_volume": 500.0,
            "total_ask_volume": 500.0,
            "imbalance": 0.0,
            "walls": [{"side": "buy", "price": 99.0, "quantity": 150.0}], # Quantity > 100, will be a wall
            "mid_price": 100.0
        }
        intel_bundle = IntelligenceBundle(liquidity=liquidity_intel)

        # Ensure wall bonus points are set
        LIQUIDITY["wall_threshold_btc"] = 10.0 # Placeholder, actual check is quantity > 100 in analyze_liquidity
        LIQUIDITY["wall_bonus_pts"] = 10.0

        score_result = compute_score(
            symbol="BTC",
            timeframe="5m",
            price=self.mock_price_snapshot,
            candles=self.mock_candles,
            candles_15m=self.mock_candles_15m,
            candles_1h=self.mock_candles_1h,
            fg=self.mock_fg_snapshot,
            news=self.mock_news,
            derivatives=self.mock_derivatives,
            flows=self.mock_flows,
            macro=self.mock_macro,
            intel=intel_bundle
        )
        self.assertIn("LIQUIDITY_BUY_WALL", score_result.decision_trace["codes"])
        self.assertAlmostEqual(score_result.score_breakdown["volume"], LIQUIDITY["wall_bonus_pts"])
        self.assertIn("liquidity_walls", score_result.decision_trace["context"])
        self.assertEqual(score_result.decision_trace["context"]["liquidity_walls"], 1)

    def test_compute_score_liquidity_with_sell_wall_penalty(self):
        # Setup liquidity with a sell wall
        liquidity_intel = {
            "is_healthy": True,
            "total_bid_volume": 500.0,
            "total_ask_volume": 500.0,
            "imbalance": 0.0,
            "walls": [{"side": "sell", "price": 101.0, "quantity": 150.0}], # Quantity > 100, will be a wall
            "mid_price": 100.0
        }
        intel_bundle = IntelligenceBundle(liquidity=liquidity_intel)

        # Ensure wall penalty points are set
        LIQUIDITY["wall_threshold_btc"] = 10.0
        LIQUIDITY["wall_penalty_pts"] = 5.0

        score_result = compute_score(
            symbol="BTC",
            timeframe="5m",
            price=self.mock_price_snapshot,
            candles=self.mock_candles,
            candles_15m=self.mock_candles_15m,
            candles_1h=self.mock_candles_1h,
            fg=self.mock_fg_snapshot,
            news=self.mock_news,
            derivatives=self.mock_derivatives,
            flows=self.mock_flows,
            macro=self.mock_macro,
            intel=intel_bundle
        )
        self.assertIn("LIQUIDITY_SELL_WALL", score_result.decision_trace["codes"])
        self.assertAlmostEqual(score_result.score_breakdown["volume"], -LIQUIDITY["wall_penalty_pts"])
        self.assertIn("liquidity_walls", score_result.decision_trace["context"])
        self.assertEqual(score_result.decision_trace["context"]["liquidity_walls"], 1)

if __name__ == "__main__":
    unittest.main()
