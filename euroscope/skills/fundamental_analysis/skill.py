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
    capabilities = ["get_news", "get_calendar", "get_sentiment", "get_macro", "get_narratives", "full"]

    def __init__(self, news_engine=None, calendar=None, macro_provider=None):
        super().__init__()
        self._news = news_engine
        self._calendar = calendar
        self._macro = macro_provider

    def set_engines(self, news_engine=None, calendar=None, macro_provider=None):
        if news_engine:
            self._news = news_engine
        if calendar:
            self._calendar = calendar
        if macro_provider:
            self._macro = macro_provider

    def set_macro_provider(self, macro_provider):
        """Standard setter for auto-injection."""
        self._macro = macro_provider

    def set_news_engine(self, news_engine):
        self._news = news_engine

    def set_calendar(self, calendar):
        self._calendar = calendar

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "get_news":
            return await self._get_news(context)
        elif action == "get_calendar":
            return await self._get_calendar(context)
        elif action == "get_sentiment":
            return await self._get_sentiment(context)
        elif action == "get_macro":
            return await self._get_macro(context)
        elif action == "get_narratives":
            return await self._get_narratives(context)
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
            
            # Phase 3: Trigger background narrative graph update
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                loop.create_task(self._update_narrative_graph(articles))
            except Exception as e:
                import logging
                logging.getLogger("euroscope.skill.fundamental").debug(f"Graph update task dispatch failed: {e}")

            return SkillResult(success=True, data=articles, metadata={"formatted": formatted})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _update_narrative_graph(self, articles: list):
        if not articles: return
        try:
            from euroscope.container import get_container
            container = get_container()
            if not container or not container.router: return
            
            # Use top max 3 titles for extraction to save tokens
            combined = "\n".join([a.get('title', '') for a in articles[:3]])
            prompt = (
                "Extract up to 3 macro-economic causal relationships from these news titles.\n"
                "Identify the root entity (source) and its effect on another entity (target).\n"
                "Return STRICTLY as a JSON array with string variables 'source', 'target', 'relation' (verb), and 'weight' (float 0.5-1.0).\n\n"
                f"News:\n{combined}\n"
                "Respond ONLY with valid JSON array."
            )
            resp = await container.router.chat([{"role": "user", "content": prompt}], temperature=0.1)
            import re, json
            match = re.search(r'\[.*\]', resp, re.DOTALL)
            if match:
                relations = json.loads(match.group(0))
                from euroscope.data.sentiment_graph import NarrativeGraph
                graph = NarrativeGraph()
                graph.update_from_news(relations)
        except Exception as e:
            import logging
            logging.getLogger("euroscope.skill.fundamental").debug(f"Narrative extraction failed: {e}")

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
            
            # Inject into metadata for the WorldModel to consume (Fixes Gap #1)
            context.metadata["sentiment_data"] = {
                "label": sentiment,
                "score": round(avg, 3),
                "mood": sentiment,  # For now, market mood matches news sentiment
                "cot_net": 0  # Placeholder since COT is not fetched here
            }
            
            formatted = f"📊 *Sentiment:* {sentiment.capitalize()} (Score: {avg:.2f})"
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_macro(self, context: SkillContext) -> SkillResult:
        if not self._macro:
            return SkillResult(success=False, error="No macro provider configured")
        
        try:
            # Phase 2: Comprehensive fetch with quality assessment
            macro_pkg = await self._macro.fetch_complete_macro_data()
            quality = macro_pkg.get("quality", "complete")
            warnings = macro_pkg.get("warnings", [])
            
            # Fetch formatted context for AI
            context_str = await self._macro.get_macro_context_for_ai()
            
            # Calculate macro impact
            macro_impact = "neutral"
            # Simple logic: check ECB rate or USD rates
            ecb = macro_pkg["eu_data"].get("ecb")
            fed = macro_pkg["us_data"].get("fed")
            
            if ecb and fed:
                diff = fed.get("rate", 0) - ecb.get("value", 0)
                macro_impact = "bullish" if diff < 0 else "bearish" if diff > 1.0 else "neutral"

            # Adaptive Confidence (Phase 2B)
            base_confidence = 0.85
            if quality == "partial_eu" or quality == "partial_us":
                confidence = base_confidence * 0.6  # 40% reduction
            elif quality == "minimal":
                confidence = base_confidence * 0.3  # 70% reduction
            else:
                confidence = base_confidence

            data = {
                "macro_data": macro_pkg,
                "macro_impact": macro_impact,
                "data_quality": quality,
                "confidence": confidence
            }
            
            context.analysis["macro_data"] = data
            context.metadata["macro_quality"] = quality
            context.metadata["fundamental_confidence"] = confidence
            context.metadata["fundamental_bias"] = str(macro_impact).upper()
            
            if warnings:
                context.metadata["macro_warnings"] = warnings

            return SkillResult(
                success=True, 
                data=data, 
                metadata={
                    "formatted": context_str,
                    "warnings": warnings,
                    "quality": quality
                }
            )
        except Exception as e:
            return SkillResult(success=False, error=f"Macro analysis failed: {str(e)}")

    async def _get_narratives(self, context: SkillContext) -> SkillResult:
        try:
            from euroscope.data.sentiment_graph import NarrativeGraph
            g = NarrativeGraph()
            narratives = g.get_central_narratives(top_n=3)
            context.analysis["narratives"] = narratives
            return SkillResult(success=True, data={"narratives": narratives}, metadata={"formatted": narratives})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _full(self, context: SkillContext) -> SkillResult:
        news = await self._get_news(context)
        cal = await self._get_calendar(context)
        sent = await self._get_sentiment(context)
        macro = await self._get_macro(context)
        
        data = {
            "news": news.data if news.success else [],
            "calendar": cal.data if cal.success else [],
            "sentiment": sent.data if sent.success else {},
            "macro": macro.data if macro.success else {},
            "summary": self._generate_summary(macro) if macro.success else "Macro analysis failed"
        }
        return SkillResult(success=True, data=data)

    def _generate_summary(self, macro_result: SkillResult) -> str:
        """Adaptive summary based on data quality (Phase 2B)."""
        data = macro_result.data
        if not data: return "Macro analysis failed"
        
        quality = data.get("data_quality", "complete")
        impact = data.get("macro_impact", "neutral")
        
        if quality == "complete":
            return f"Macro analysis: {impact.capitalize()} bias (US & EU data complete)"
        elif quality == "partial_eu":
            return f"Macro analysis: {impact.capitalize()} bias (US data only — EU data missing)"
        elif quality == "partial_us":
            return f"Macro analysis: {impact.capitalize()} bias (EU data only — US data missing)"
        else:
            return "Macro analysis unavailable — critical data sources offline"

    def _format_calendar(self, events: list) -> str:
        if not events:
            return "📅 No major impacted events upcoming."
        
        lines = ["📅 *Economic Calendar*"]
        for e in events[:5]:
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
