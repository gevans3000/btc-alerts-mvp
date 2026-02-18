import pytest
from dataclasses import is_dataclass
from typing import Dict
from pathlib import Path
import time

from engine import AlertScore, compute_score
from intelligence import IntelligenceBundle
from collectors.base import BudgetManager
from config import INTELLIGENCE_FLAGS, TIMEFRAME_RULES
from collectors.price import PriceSnapshot
from collectors.social import FearGreedSnapshot, Headline
from collectors.derivatives import DerivativesSnapshot
from collectors.flows import FlowSnapshot
from utils import Candle

def test_alert_score_has_context_field():
    score = AlertScore(
        symbol="TEST", timeframe="5m", regime="range", confidence=50, tier="B", action="WATCH",
        reasons=[], reason_codes=[], blockers=[], quality="ok", direction="NEUTRAL",
        strategy_type="NONE", entry_zone="-", invalidation=0.0, tp1=0.0, tp2=0.0, rr_ratio=0.0,
        session="us", score_breakdown={}, lifecycle_key="test:key"
    )
    assert hasattr(score, "context")
    assert isinstance(score.context, dict)
    assert score.context == {}

def test_intelligence_bundle_instantiates_with_none():
    bundle = IntelligenceBundle()
    assert is_dataclass(bundle)
    assert bundle.squeeze is None
    assert bundle.sentiment is None
    assert bundle.confluence is None

def test_compute_score_works_with_intel_none():
    # Create mock data for compute_score
    mock_candles = [Candle(ts=str(i), open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0) for i in range(50)]
    mock_price = PriceSnapshot(price=100.0, timestamp=time.time(), source="test", healthy=True)
    mock_fg = FearGreedSnapshot(value=50, label="Neutral", healthy=True)
    mock_news = [Headline(title="test news", source="test.com")]
    mock_derivatives = DerivativesSnapshot(funding_rate=0.0, oi_change_pct=0.0, basis_pct=0.0, healthy=True)
    mock_flows = FlowSnapshot(taker_ratio=1.0, long_short_ratio=1.0, crowding_score=0, healthy=True)
    mock_macro = {"dxy": mock_candles, "gold": mock_candles}

    # Call compute_score without intel (should default to None implicitly)
    score_without_intel = compute_score(
        symbol="BTC",
        timeframe="5m",
        price=mock_price,
        candles=mock_candles,
        candles_15m=mock_candles,
        candles_1h=mock_candles,
        fg=mock_fg,
        news=mock_news,
        derivatives=mock_derivatives,
        flows=mock_flows,
        macro=mock_macro,
    )

    # Call compute_score with explicit intel=None
    score_with_explicit_none_intel = compute_score(
        symbol="BTC",
        timeframe="5m",
        price=mock_price,
        candles=mock_candles,
        candles_15m=mock_candles,
        candles_1h=mock_candles,
        fg=mock_fg,
        news=mock_news,
        derivatives=mock_derivatives,
        flows=mock_flows,
        macro=mock_macro,
        intel=None,
    )

    # Call compute_score with an empty IntelligenceBundle
    score_with_empty_intel_bundle = compute_score(
        symbol="BTC",
        timeframe="5m",
        price=mock_price,
        candles=mock_candles,
        candles_15m=mock_candles,
        candles_1h=mock_candles,
        fg=mock_fg,
        news=mock_news,
        derivatives=mock_derivatives,
        flows=mock_flows,
        macro=mock_macro,
        intel=IntelligenceBundle()
    )

    # Assert that the scores are identical (or at least no breaking changes)
    # We are not checking the content of the score, just that the call succeeds
    assert isinstance(score_without_intel, AlertScore)
    assert isinstance(score_with_explicit_none_intel, AlertScore)
    assert isinstance(score_with_empty_intel_bundle, AlertScore)
    
    # Deeper check for specific attributes that should be the same
    assert score_without_intel.symbol == score_with_explicit_none_intel.symbol
    assert score_without_intel.timeframe == score_with_explicit_none_intel.timeframe
    assert score_without_intel.confidence == score_with_explicit_none_intel.confidence
    assert score_without_intel.action == score_with_explicit_none_intel.action

    assert score_without_intel.symbol == score_with_empty_intel_bundle.symbol
    assert score_without_intel.timeframe == score_with_empty_intel_bundle.timeframe
    assert score_without_intel.confidence == score_with_empty_intel_bundle.confidence
    assert score_without_intel.action == score_with_empty_intel_bundle.action

def test_budget_manager_allows_yahoo_calls():
    # Ensure the budget file is clean before testing
    budget_file = Path(".budget.json")
    if budget_file.exists():
        budget_file.unlink()
    
    bm = BudgetManager()
    # Ensure the limit for yahoo is now 10 (changed from 0)
    assert bm.can_call("yahoo") is True
    # Make 10 calls, it should still be True
    for _ in range(10):
        bm.record_call("yahoo")
    assert bm.can_call("yahoo") is False

def test_intelligence_flags_contain_expected_keys_and_are_booleans():
    expected_flags = [
        "squeeze_enabled",
        "sentiment_enabled",
        "confluence_enabled",
    ]
    assert all(flag in INTELLIGENCE_FLAGS for flag in expected_flags)
    assert all(isinstance(INTELLIGENCE_FLAGS[flag], bool) for flag in expected_flags)

