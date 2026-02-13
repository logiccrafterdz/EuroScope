"""
EUR/USD News Engine

Fetches and filters news relevant to EUR/USD using Brave Search API.
"""

import logging
from datetime import datetime
from typing import Optional

import httpx

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


class NewsEngine:
    """Fetches EUR/USD-relevant news via Brave Search API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/news/search"

    async def fetch_news(self, query: str = "EUR/USD forex", count: int = 10) -> list[dict]:
        """Fetch news articles related to EUR/USD."""
        if not self.api_key:
            return [{"title": "⚠️ News unavailable", "description": "Brave API key not configured"}]

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self.base_url,
                    headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
                    params={"q": query, "count": count, "freshness": "pd"},  # past day
                )
                resp.raise_for_status()
                data = resp.json()

            articles = []
            for result in data.get("results", []):
                relevance = self._score_relevance(result.get("title", "") + " " + result.get("description", ""))
                articles.append({
                    "title": result.get("title", ""),
                    "description": result.get("description", ""),
                    "url": result.get("url", ""),
                    "published": result.get("age", ""),
                    "source": result.get("meta_url", {}).get("hostname", ""),
                    "relevance": relevance,
                })

            # Sort by relevance
            articles.sort(key=lambda x: x["relevance"], reverse=True)
            return articles[:count]

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

        for q in queries:
            articles = await self.fetch_news(q, count=5)
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
            lines.append(f"*{i}.* {title}")
            if desc:
                lines.append(f"   _{desc}_")
            if source or age:
                lines.append(f"   🔗 {source} • {age}")
            lines.append("")

        return "\n".join(lines)
