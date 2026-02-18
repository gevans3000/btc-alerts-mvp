import pytest
from unittest.mock import Mock
from intelligence.sentiment import analyze_sentiment, SentimentEngine
from collectors.social import Headline, FearGreedSnapshot
from config import SENTIMENT

# Mock the global sentiment_engine to ensure consistent lexicon for tests
@pytest.fixture(autouse=True)
def mock_sentiment_engine():
    engine = SentimentEngine()
    # Reset lexicon to a base state and then apply the test config lexicon
    # This ensures tests are isolated from previous lexicon modifications
    engine.analyzer.lexicon = engine.analyzer.make_lex_dict()
    engine.analyzer.lexicon.update(SENTIMENT["crypto_lexicon"])
    yield engine

def test_analyze_sentiment_empty_news(mock_sentiment_engine):
    # Ensure it handles empty news list gracefully
    result = analyze_sentiment([])
    assert result == {"composite": 0.0, "bullish_pct": 0, "bearish_pct": 0, "count": 0, "fallback": True}

def test_analyze_sentiment_positive_news(mock_sentiment_engine):
    news = [
        Headline(title="Bitcoin absolutely explodes and rallies to new all-time highs!", source="test_source"),
        Headline(title="Ethereum adoption surges tremendously with massive institutional interest!", source="test_source"),
        Headline(title="New groundbreaking partnership announced for highly successful crypto project!", source="test_source"),
    ]
    result = analyze_sentiment(news)
    assert result["fallback"] == False
    assert result["count"] == 3
    assert result["composite"] > 0.3 # Should be positive
    assert result["bullish_pct"] >= 60 # At least 2/3 are strongly positive
    assert result["bearish_pct"] < 30 # Less than 1/3 are strongly negative

def test_analyze_sentiment_negative_news(mock_sentiment_engine):
    news = [
        Headline(title="Crypto market dumps hard", source="test_source"),
        Headline(title="Exchange hacked, funds lost", source="test_source"),
        Headline(title="Regulation threat for DeFi", source="test_source"),
    ]
    result = analyze_sentiment(news)
    assert result["fallback"] == False
    assert result["count"] == 3
    assert result["composite"] < -0.3 # Should be negative
    assert result["bearish_pct"] >= 60 # At least 2/3 are strongly negative
    assert result["bullish_pct"] < 30 # Less than 1/3 are strongly positive

def test_analyze_sentiment_mixed_news(mock_sentiment_engine):
    news = [
        Headline(title="Bitcoin rallies to new highs", source="test_source"),
        Headline(title="Exchange hacked, funds lost", source="test_source"),
        Headline(title="Neutral crypto report released", source="test_source"),
    ]
    result = analyze_sentiment(news)
    assert result["fallback"] == False
    assert result["count"] == 3
    # The composite score might be close to zero or slightly positive/negative depending on VADER's specific scoring
    # We can check that both bullish and bearish percentages are present
    assert result["bullish_pct"] > 0
    assert result["bearish_pct"] > 0
    # Check that composite is not extremely positive or negative
    assert -0.5 < result["composite"] < 0.5

def test_analyze_sentiment_neutral_news(mock_sentiment_engine):
    news = [
        Headline(title="Crypto price shows no significant movement, consolidating sideways", source="test_source"),
        Headline(title="Market analysis indicates a period of indecision", source="test_source"),
    ]
    result = analyze_sentiment(news)
    assert result["fallback"] == False
    assert result["count"] == 2
    # Neutral news should result in a composite close to zero and low bullish/bearish percentages
    assert -0.2 < result["composite"] < 0.2
    assert result["bullish_pct"] < 60
    assert result["bearish_pct"] < 60

def test_analyze_sentiment_with_crypto_lexicon(mock_sentiment_engine):
    news = [
        Headline(title="HODLers strong, Bitcoin to the moon!", source="test_source"),
        Headline(title="FUD spreads, market dumps", source="test_source"),
    ]
    result = analyze_sentiment(news)
    assert result["fallback"] == False
    assert result["count"] == 2
    # The custom lexicon should influence these scores significantly
    assert result["bullish_pct"] > 0
    assert result["bearish_pct"] > 0
    # Check composite based on the combined effect of custom lexicon words
    # HODL, moon, FUD, dump are strong. Expected a relatively neutral to slightly negative/positive result depending on balance.
    # Let's verify it's not extreme in either direction and not fallback.
    assert -0.5 < result["composite"] < 0.5
