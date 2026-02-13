"""
Fundamental Analysis Skill — Wraps NewsEngine, EconomicCalendar.
"""

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class FundamentalAnalysisSkill(BaseSkill):
    name = "fundamental_analysis"
    description = "News sentiment, economic calendar, and central bank data"
    emoji = "📰"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["get_news", "get_calendar", "get_sentiment", "full"]

    def __init__(self, news_engine=None, calendar=None):
        super().__init__()
        self._news = news_engine
        self._calendar = calendar

    def set_engines(self, news_engine=None, calendar=None):
        if news_engine:
            self._news = news_engine
        if calendar:
            self._calendar = calendar

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "get_news":
            return await self._get_news(context)
        elif action == "get_calendar":
            return await self._get_calendar(context)
        elif action == "get_sentiment":
            return await self._get_sentiment(context)
        elif action == "full":
            return await self._full(context)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _get_news(self, context: SkillContext) -> SkillResult:
        if not self._news:
            return SkillResult(success=False, error="No news engine configured")
        try:
            articles = await self._news.get_eurusd_news()
            context.analysis["news"] = articles
            
            formatted = self._news.format_news(articles) if hasattr(self._news, 'format_news') else str(articles)
            return SkillResult(success=True, data=articles, metadata={"formatted": formatted})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_calendar(self, context: SkillContext) -> SkillResult:
        if not self._calendar:
            return SkillResult(success=False, error="No calendar configured")
        try:
            events = self._calendar.get_upcoming_events()
            data = [e.__dict__ if hasattr(e, "__dict__") else e for e in events]
            context.analysis["calendar"] = data
            
            formatted = self._format_calendar(data)
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_sentiment(self, context: SkillContext) -> SkillResult:
        if not self._news:
            return SkillResult(success=False, error="No news engine configured")
        try:
            articles = await self._news.get_eurusd_news()
            if not articles:
                return SkillResult(success=True, data={"sentiment": "neutral", "score": 0})
            scores = [a.get("sentiment_score", 0) for a in articles]
            avg = sum(scores) / len(scores) if scores else 0
            sentiment = "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral"
            data = {"sentiment": sentiment, "score": round(avg, 3), "article_count": len(articles)}
            context.analysis["sentiment_summary"] = data
            
            formatted = f"📊 *Sentiment:* {sentiment.capitalize()} (Score: {avg:.2f})"
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _full(self, context: SkillContext) -> SkillResult:
        news = await self._get_news(context)
        cal = await self._get_calendar(context)
        sent = await self._get_sentiment(context)
        data = {
            "news": news.data if news.success else [],
            "calendar": cal.data if cal.success else [],
            "sentiment": sent.data if sent.success else {},
        }
        return SkillResult(success=True, data=data)

    def _format_calendar(self, events: list) -> str:
        # Check if events is None or empty
        if not events:
            return "📅 No major impacted events upcoming."
        
        lines = ["📅 *Economic Calendar*"]
        # Limit to 5 events
        for e in events[:5]:
            # Handle both dict and object (though we converted to dict in _get_calendar)
            time = e.get("time", "") if isinstance(e, dict) else getattr(e, "time", "")
            currency = e.get("currency", "") if isinstance(e, dict) else getattr(e, "currency", "")
            impact = e.get("impact", "Low") if isinstance(e, dict) else getattr(e, "impact", "Low")
            event = e.get("event", "") if isinstance(e, dict) else getattr(e, "event", "")
            actual = e.get("actual", "") if isinstance(e, dict) else getattr(e, "actual", "")
            forecast = e.get("forecast", "") if isinstance(e, dict) else getattr(e, "forecast", "")
            
            icon = "🔴" if impact == "High" else "🟠" if impact == "Medium" else "⚪"
            lines.append(f"{icon} `{time}` {currency}: {event}")
            if actual or forecast:
                lines.append(f"   Act: `{actual}` Fcst: `{forecast}`")
        return "\n".join(lines)
