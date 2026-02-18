from typing import Dict, Any, List
from collectors.social import FearGreedSnapshot, Headline
from config import SENTIMENT
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

class SentimentEngine:
    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()
        # Extend VADER's lexicon with crypto-specific terms from config
        self.analyzer.lexicon.update(SENTIMENT["crypto_lexicon"])

    def analyze_text(self, text: str) -> Dict[str, float]:
        vs = self.analyzer.polarity_scores(text)
        return vs

sentiment_engine = SentimentEngine() # Initialize a global sentiment engine

def analyze_sentiment(
    news: List[Headline],
) -> Dict[str, Any]:
    """
    Analyzes news headlines for sentiment using VADER.
    Returns a composite score, bullish/bearish percentages, and fallback status.
    """
    if not news:
        return {"composite": 0.0, "bullish_pct": 0, "bearish_pct": 0, "count": 0, "fallback": True}

    total_headlines = len(news)
    positive_scores = []
    negative_scores = []
    neutral_scores = []

    for article in news:
        vs = sentiment_engine.analyze_text(article.title)
        if vs["compound"] >= 0.05:
            positive_scores.append(vs["compound"])
        elif vs["compound"] <= -0.05:
            negative_scores.append(vs["compound"])
        else:
            neutral_scores.append(vs["compound"])

    # Calculate composite score (average of compound scores, or just compound if only one score)
    # If no strong sentiment, composite is 0.0
    composite_score = 0.0
    if positive_scores or negative_scores:
        all_compound_scores = [sentiment_engine.analyze_text(a.title)["compound"] for a in news]
        composite_score = sum(all_compound_scores) / len(all_compound_scores)

    bullish_pct = int((len(positive_scores) / total_headlines) * 100)
    bearish_pct = int((len(negative_scores) / total_headlines) * 100)

    return {
        "composite": round(composite_score, 3),
        "bullish_pct": bullish_pct,
        "bearish_pct": bearish_pct,
        "count": total_headlines,
        "fallback": False,
    }
