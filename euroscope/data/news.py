"""
EUR/USD News Engine

Fetches and filters news relevant to EUR/USD using DuckDuckGo Search.
Includes TextBlob-based sentiment analysis and DB persistence.
No API key required.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("euroscope.data.news")

# Keywords that are highly relevant to EUR/USD
EURUSD_KEYWORDS = [
    "EUR/USD", "EURUSD", "euro dollar",
    "ECB", "European Central Bank", "Lagarde",
    "Federal Reserve", "Fed", "Powell", "FOMC",
    "eurozone", "euro area", "EU economy",
    "US economy", "nonfarm payroll", "NFP",
    "CPI inflation", "interest rate decision",
    "dollar index", "DXY",
    "PMI eurozone", "GDP eurozone", "GDP US",
]

# Forex-specific sentiment keywords with weights
BULLISH_KEYWORDS = [
    "hawkish ecb", "ecb rate hike", "euro strength", "eurozone growth",
    "dovish fed", "fed rate cut", "dollar weakness", "dxy falling",
    "euro rally", "bullish euro", "eur/usd rises", "euro gains",
    "strong eurozone", "ecb tightening", "us recession",
]

BEARISH_KEYWORDS = [
    "hawkish fed", "fed rate hike", "dollar strength", "dxy rising",
    "dovish ecb", "ecb rate cut", "euro weakness", "eurozone recession",
    "euro falls", "bearish euro", "eur/usd drops", "euro declines",
    "weak eurozone", "us growth strong", "fed tightening",
]


def analyze_sentiment(text: str) -> dict:
    """
    Analyze sentiment of text with forex-specific keyword boosting.

    Returns:
        {"sentiment": "bullish|bearish|neutral", "score": float (-1 to 1)}
    """
    try:
        from textblob import TextBlob
        blob = TextBlob(text)
        base_score = blob.sentiment.polarity  # -1 to 1
    except ImportError:
        logger.warning("textblob not installed, using keyword-only sentiment")
        base_score = 0.0

    # Forex-specific keyword boosting
    text_lower = text.lower()
    boost = 0.0
    for kw in BULLISH_KEYWORDS:
        if kw in text_lower:
            boost += 0.15
    for kw in BEARISH_KEYWORDS:
        if kw in text_lower:
            boost -= 0.15

    # Combine base + boost, clamped to [-1, 1]
    final_score = max(-1.0, min(1.0, base_score + boost))

    if final_score > 0.1:
        sentiment = "bullish"
    elif final_score < -0.1:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return {"sentiment": sentiment, "score": round(final_score, 3)}


class NewsEngine:
    """Fetches EUR/USD-relevant news via DuckDuckGo Search with sentiment analysis."""

    def __init__(self, api_key: str = None, storage=None):
        """
        Initialize the news engine.

        Args:
            api_key: Ignored (kept for backward compatibility). DuckDuckGo is free.
            storage: Optional Storage instance for persistence.
        """
        self.storage = storage

    async def fetch_news(self, query: str = "EUR/USD forex", count: int = 10) -> list[dict]:
        """Fetch news articles related to EUR/USD via DuckDuckGo."""
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            def _search():
                import os
                import warnings
                os.environ["RUST_LOG"] = "error"
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning, module="primp")
                    with DDGS() as ddgs:
                        return list(ddgs.news(query, max_results=count))

            raw_results = await asyncio.to_thread(_search)

            articles = []
            for result in raw_results:
                full_text = result.get("title", "") + " " + result.get("body", "")
                relevance = self._score_relevance(full_text)
                sentiment_data = analyze_sentiment(full_text)

                article = {
                    "title": result.get("title", ""),
                    "description": result.get("body", ""),
                    "url": result.get("url", ""),
                    "published": result.get("date", ""),
                    "source": result.get("source", ""),
                    "relevance": relevance,
                    "sentiment": sentiment_data["sentiment"],
                    "sentiment_score": sentiment_data["score"],
                }
                articles.append(article)

                # Persist to DB if storage available
                if self.storage:
                    try:
                        self.storage.save_news_event(
                            title=article["title"],
                            source=article["source"],
                            url=article["url"],
                            description=article["description"],
                            impact_score=float(relevance),
                            sentiment=article["sentiment"],
                            sentiment_score=article["sentiment_score"],
                            published_at=article["published"],
                        )
                    except Exception as e:
                        logger.debug(f"Failed to persist news: {e}")

            # Sort by relevance
            articles.sort(key=lambda x: x["relevance"], reverse=True)
            return articles[:count]

        except ImportError:
            logger.error("ddgs not installed. Run: pip install ddgs")
            return [{"title": "❌ News unavailable", "description": "ddgs not installed"}]
        except Exception as e:
            logger.error(f"News fetch error: {e}")
            return [{"title": "❌ Error fetching news", "description": str(e)}]

    def _score_relevance(self, text: str) -> int:
        """Score how relevant a piece of text is to EUR/USD."""
        text_lower = text.lower()
        score = 0
        for kw in EURUSD_KEYWORDS:
            if kw.lower() in text_lower:
                score += 1
        return score

    async def get_eurusd_news(self) -> list[dict]:
        """Get the most relevant EUR/USD news from multiple queries."""
        all_articles = []
        queries = [
            "EUR/USD forex analysis today",
            "ECB interest rate euro",
            "Federal Reserve dollar policy",
            "eurozone economy GDP",
        ]

        tasks = [self.fetch_news(q, count=5) for q in queries]
        results = await asyncio.gather(*tasks)
        
        for articles in results:
            all_articles.extend(articles)

        # Deduplicate by title similarity
        seen_titles = set()
        unique = []
        for a in all_articles:
            title_key = a["title"][:50].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique.append(a)

        unique.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return unique[:10]

    def get_sentiment_summary(self) -> dict:
        """
        Get aggregate sentiment from recently stored news.
        Returns sentiment distribution and overall bias.
        """
        if not self.storage:
            return {"error": "No storage configured"}

        recent = self.storage.get_recent_news(limit=20)
        if not recent:
            return {"total": 0, "overall": "neutral", "message": "No recent news"}

        bullish = sum(1 for n in recent if n.get("sentiment") == "bullish")
        bearish = sum(1 for n in recent if n.get("sentiment") == "bearish")
        neutral = sum(1 for n in recent if n.get("sentiment") == "neutral")
        total = len(recent)

        avg_score = sum(n.get("sentiment_score", 0) for n in recent) / total if total else 0

        if avg_score > 0.1:
            overall = "bullish"
        elif avg_score < -0.1:
            overall = "bearish"
        else:
            overall = "neutral"

        return {
            "total": total,
            "bullish": bullish,
            "bearish": bearish,
            "neutral": neutral,
            "avg_score": round(avg_score, 3),
            "overall": overall,
        }

    def format_news(self, articles: list[dict]) -> str:
        """Format news articles for display in Telegram."""
        if not articles:
            return "📰 No EUR/USD news found."

        lines = ["📰 *EUR/USD News*\n"]
        for i, a in enumerate(articles, 1):
            title = a.get("title", "Untitled")
            desc = a.get("description", "")[:120]
            source = a.get("source", "")
            age = a.get("published", "")

            # Sentiment icon
            sentiment = a.get("sentiment", "neutral")
            s_icon = "🟢" if sentiment == "bullish" else "🔴" if sentiment == "bearish" else "⚪"

            lines.append(f"*{i}.* {s_icon} {title}")
            if desc:
                lines.append(f"   _{desc}_")
            if source or age:
                lines.append(f"   🔗 {source} • {age}")
            lines.append("")

        # Sentiment summary at bottom
        sentiments = [a.get("sentiment", "neutral") for a in articles]
        bull = sentiments.count("bullish")
        bear = sentiments.count("bearish")
        lines.append(f"📊 *Sentiment:* 🟢 {bull} bullish | 🔴 {bear} bearish | ⚪ {len(sentiments) - bull - bear} neutral")

        return "\n".join(lines)
