"""
Technical Analysis Skill — Wraps TechnicalAnalyzer, PatternDetector, LevelAnalyzer.
"""

from ...analysis.technical import TechnicalAnalyzer
from ...analysis.patterns import PatternDetector
from ...analysis.levels import LevelAnalyzer
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class TechnicalAnalysisSkill(BaseSkill):
    name = "technical_analysis"
    description = "Computes indicators, detects patterns, and finds key price levels"
    emoji = "📈"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["analyze", "detect_patterns", "find_levels", "full"]

    def __init__(self):
        super().__init__()
        self.technical = TechnicalAnalyzer()
        self.patterns = PatternDetector()
        self.levels = LevelAnalyzer()
        self._provider = None

    def set_provider(self, provider):
        """Inject the PriceProvider instance."""
        self._provider = provider

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        df = params.get("df", context.market_data.get("candles"))
        
        # Auto-fetch if missing and provider available
        if (df is None or (hasattr(df, 'empty') and df.empty)) and self._provider:
            tf = params.get("timeframe", context.market_data.get("timeframe", "H1"))
            df = self._provider.get_candles(timeframe=tf)
            if df is not None:
                context.market_data["candles"] = df
                context.market_data["timeframe"] = tf

        if df is None or (hasattr(df, 'empty') and df.empty):
            return SkillResult(success=False, error="No candle data available")

        if action == "analyze":
            return await self._analyze(context, df)
        elif action == "detect_patterns":
            return await self._detect_patterns(context, df)
        elif action == "find_levels":
            return await self._find_levels(context, df)
        elif action == "full":
            return await self._full(context, df)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _analyze(self, context: SkillContext, df) -> SkillResult:
        ta = self.technical.analyze(df)
        if "error" in ta:
            return SkillResult(success=False, error=ta["error"])
        context.analysis["indicators"] = ta
        return SkillResult(success=True, data=ta)

    async def _detect_patterns(self, context: SkillContext, df) -> SkillResult:
        patterns = self.patterns.detect_all(df)
        context.analysis["patterns"] = patterns
        return SkillResult(success=True, data=patterns)

    async def _find_levels(self, context: SkillContext, df) -> SkillResult:
        levels = self.levels.find_support_resistance(df)
        context.analysis["levels"] = levels
        return SkillResult(success=True, data=levels)

    async def _full(self, context: SkillContext, df) -> SkillResult:
        ta = self.technical.analyze(df)
        patterns = self.patterns.detect_all(df)
        levels = self.levels.find_support_resistance(df)

        data = {"indicators": ta, "patterns": patterns, "levels": levels}
        context.analysis.update(data)
        return SkillResult(
            success=True, data=data, next_skill="risk_management",
        )
