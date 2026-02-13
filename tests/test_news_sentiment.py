"""
Tests for news engine sentiment analysis.
"""

import os
import tempfile

import pytest

from euroscope.data.news import analyze_sentiment, NewsEngine
from euroscope.data.storage import Storage


class TestAnalyzeSentiment:
    """Test the sentiment analysis function."""

    def test_bullish_text(self):
        result = analyze_sentiment("ECB rate hike expected, euro strength continues")
        assert result["sentiment"] == "bullish"
        assert result["score"] > 0

    def test_bearish_text(self):
        result = analyze_sentiment("Fed rate hike, dollar strength, euro falls sharply")
        assert result["sentiment"] == "bearish"
        assert result["score"] < 0

    def test_neutral_text(self):
        result = analyze_sentiment("Markets were steady today with no major moves")
        assert result["sentiment"] == "neutral"
        assert -0.2 <= result["score"] <= 0.2

    def test_empty_text(self):
        result = analyze_sentiment("")
        assert result["sentiment"] == "neutral"
        assert result["score"] == 0.0

    def test_hawkish_ecb_is_bullish(self):
        result = analyze_sentiment("hawkish ecb signals more rate hikes ahead")
        assert result["sentiment"] == "bullish"

    def test_dovish_fed_is_bullish(self):
        result = analyze_sentiment("dovish fed hints at rate cuts in coming months")
        assert result["sentiment"] == "bullish"

    def test_hawkish_fed_is_bearish(self):
        result = analyze_sentiment("hawkish fed signals continued tightening")
        assert result["sentiment"] == "bearish"

    def test_score_range(self):
        """Score should always be between -1 and 1."""
        texts = [
            "extremely bullish euro rally ecb rate hike euro strength eurozone growth",
            "terrible bearish crash dollar strength fed rate hike euro falls",
        ]
        for text in texts:
            result = analyze_sentiment(text)
            assert -1.0 <= result["score"] <= 1.0


class TestNewsEngineSentiment:
    """Test news engine with sentiment and storage integration."""

    def test_format_news_with_sentiment(self):
        engine = NewsEngine(api_key="", storage=None)
        articles = [
            {"title": "ECB hikes rates", "description": "Rate up 25bps", "source": "reuters",
             "published": "2h", "sentiment": "bullish", "relevance": 5},
            {"title": "Dollar strengthens", "description": "DXY rises", "source": "cnbc",
             "published": "1h", "sentiment": "bearish", "relevance": 3},
        ]
        formatted = engine.format_news(articles)
        assert "🟢" in formatted  # bullish
        assert "🔴" in formatted  # bearish
        assert "Sentiment" in formatted

    def test_format_empty_news(self):
        engine = NewsEngine(api_key="", storage=None)
        formatted = engine.format_news([])
        assert "No EUR/USD news" in formatted

    def test_sentiment_summary_no_storage(self):
        engine = NewsEngine(api_key="", storage=None)
        result = engine.get_sentiment_summary()
        assert "error" in result

    def test_sentiment_summary_with_storage(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            storage = Storage(path)
            engine = NewsEngine(api_key="", storage=storage)

            # Add some mock news
            storage.save_news_event("Bullish news", "test", sentiment="bullish", sentiment_score=0.5)
            storage.save_news_event("Bearish news", "test", sentiment="bearish", sentiment_score=-0.5)
            storage.save_news_event("Neutral news", "test", sentiment="neutral", sentiment_score=0.0)

            summary = engine.get_sentiment_summary()
            assert summary["total"] == 3
            assert summary["bullish"] == 1
            assert summary["bearish"] == 1
            assert summary["neutral"] == 1
        finally:
            try:
                os.unlink(path)
            except PermissionError:
                pass

    def test_relevance_scoring(self):
        engine = NewsEngine(api_key="", storage=None)
        high_score = engine._score_relevance("EUR/USD ECB Federal Reserve FOMC interest rate decision")
        low_score = engine._score_relevance("local weather forecast for tomorrow")
        assert high_score > low_score
