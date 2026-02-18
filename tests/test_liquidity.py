import unittest
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass
import sys
import os

# Add the parent directory to the path to allow imports from collectors and intelligence
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from collectors.orderbook import OrderBookSnapshot, _detect_walls
from intelligence.liquidity import analyze_liquidity
from config import LIQUIDITY # Import the LIQUIDITY config directly for testing

# Mocking the OrderBookSnapshot dataclass for testing purposes
# In a real scenario, you would use the actual dataclass.
# For isolated testing of analyze_liquidity, a simple mock is sufficient
@dataclass
class MockOrderBookSnapshot:
    ts: int
    bids: List[Tuple[float, float]]  # (price, amount)
    asks: List[Tuple[float, float]] # (price, amount)
    mid_price: float = 0.0
    healthy: bool = True

    def __post_init__(self):
        if not self.bids and not self.asks:
            self.mid_price = 0.0
        elif not self.bids:
            self.mid_price = self.asks[0][0]
        elif not self.asks:
            self.mid_price = self.bids[0][0]
        else:
            self.mid_price = (self.bids[0][0] + self.asks[0][0]) / 2


class TestLiquidity(unittest.TestCase):

    def setUp(self):
        # Store original config values to restore after tests
        self._original_liquidity_config = LIQUIDITY.copy()
        # Set up a default LIQUIDITY config for tests, or use the one from config.py
        # For this test, we'll use the one defined in config.py, but ensure it's imported.
        pass

    def tearDown(self):
        # Restore original config values
        LIQUIDITY.update(self._original_liquidity_config)

    def test_analyze_liquidity_healthy_no_walls_no_imbalance(self):
        bids = [(99.9, 1.0), (99.8, 1.0)]
        asks = [(100.1, 1.0), (100.2, 1.0)]
        ob = MockOrderBookSnapshot(ts=123, bids=bids, asks=asks, mid_price=100.0)
        
        # Temporarily adjust config for this test if needed, or rely on defaults
        LIQUIDITY["wall_threshold_btc"] = 100.0 # High threshold to avoid walls
        LIQUIDITY["imbalance_threshold"] = 0.9 # High threshold to avoid imbalance

        result = analyze_liquidity(ob)
        self.assertTrue(result["healthy"])
        self.assertAlmostEqual(result["imbalance"], 0.0)
        self.assertEqual(len(result["bid_walls"]), 0)
        self.assertEqual(len(result["ask_walls"]), 0)
        self.assertEqual(result["pts"], 0.0)

    def test_analyze_liquidity_healthy_with_bid_wall(self):
        bids = [(99.9, 100.0), (99.8, 1.0)] # Strong bid wall
        asks = [(100.1, 1.0), (100.2, 1.0)]
        ob = MockOrderBookSnapshot(ts=123, bids=bids, asks=asks, mid_price=100.0)
        
        LIQUIDITY["wall_threshold_btc"] = 50.0  # Threshold to detect wall
        LIQUIDITY["imbalance_threshold"] = 0.1
        LIQUIDITY["wall_bonus_pts"] = 10.0

        result = analyze_liquidity(ob)
        self.assertTrue(result["healthy"])
        self.assertGreater(result["imbalance"], 0.0) # Bids > Asks
        self.assertGreater(len(result["bid_walls"]), 0)
        self.assertEqual(len(result["ask_walls"]), 0)
        self.assertEqual(result["pts"], 10.0 + LIQUIDITY["imbalance_bonus_pts"]) # Wall bonus + imbalance bonus

    def test_analyze_liquidity_healthy_with_ask_wall(self):
        bids = [(99.9, 1.0), (99.8, 1.0)]
        asks = [(100.1, 100.0), (100.2, 1.0)] # Strong ask wall
        ob = MockOrderBookSnapshot(ts=123, bids=bids, asks=asks, mid_price=100.0)
        
        LIQUIDITY["wall_threshold_btc"] = 50.0
        LIQUIDITY["imbalance_threshold"] = 0.1
        LIQUIDITY["wall_bonus_pts"] = 10.0

        result = analyze_liquidity(ob)
        self.assertTrue(result["healthy"])
        self.assertLess(result["imbalance"], 0.0) # Asks > Bids
        self.assertEqual(len(result["bid_walls"]), 0)
        self.assertGreater(len(result["ask_walls"]), 0)
        self.assertEqual(result["pts"], -(10.0 + LIQUIDITY["imbalance_bonus_pts"])) # Wall penalty + imbalance penalty

    def test_analyze_liquidity_unhealthy_orderbook(self):
        ob = MockOrderBookSnapshot(ts=123, bids=[], asks=[], healthy=False)
        result = analyze_liquidity(ob)
        self.assertFalse(result["healthy"])
        self.assertEqual(result["imbalance"], 0.0)
        self.assertEqual(result["pts"], 0.0)

    def test_analyze_liquidity_high_imbalance_no_walls(self):
        bids = [(99.9, 50.0), (99.8, 1.0)]
        asks = [(100.1, 1.0), (100.2, 1.0)]
        ob = MockOrderBookSnapshot(ts=123, bids=bids, asks=asks, mid_price=100.0)
        
        LIQUIDITY["wall_threshold_btc"] = 1000.0 # No walls
        LIQUIDITY["imbalance_threshold"] = 0.5 # Trigger imbalance
        LIQUIDITY["imbalance_bonus_pts"] = 5.0

        result = analyze_liquidity(ob)
        self.assertTrue(result["healthy"])
        self.assertAlmostEqual(result["imbalance"], (51.0 - 2.0) / (51.0 + 2.0), places=3)
        self.assertEqual(len(result["bid_walls"]), 0)
        self.assertEqual(len(result["ask_walls"]), 0)
        self.assertEqual(result["pts"], 5.0) # Only imbalance bonus

    def test_analyze_liquidity_bid_and_ask_walls(self):
        bids = [(99.9, 100.0)]
        asks = [(100.1, 100.0)]
        ob = MockOrderBookSnapshot(ts=123, bids=bids, asks=asks, mid_price=100.0)

        LIQUIDITY["wall_threshold_btc"] = 50.0
        LIQUIDITY["imbalance_threshold"] = 0.1
        LIQUIDITY["wall_penalty_pts"] = 5.0 # Penalty for both walls
        
        result = analyze_liquidity(ob)
        self.assertTrue(result["healthy"])
        self.assertAlmostEqual(result["imbalance"], 0.0)
        self.assertGreater(len(result["bid_walls"]), 0)
        self.assertGreater(len(result["ask_walls"]), 0)
        self.assertEqual(result["pts"], -5.0) # Only wall penalty

if __name__ == '__main__':
    unittest.main()
