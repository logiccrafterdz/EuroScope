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

    def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        df = params.get("df", context.market_data.get("candles"))
        if df is None or (hasattr(df, 'empty') and df.empty):
            return SkillResult(success=False, error="No candle data available")

        if action == "analyze":
            return self._analyze(context, df)
        elif action == "detect_patterns":
            return self._detect_patterns(context, df)
        elif action == "find_levels":
            return self._find_levels(context, df)
        elif action == "full":
            return self._full(context, df)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    def _analyze(self, context: SkillContext, df) -> SkillResult:
        ta = self.technical.analyze(df)
        if "error" in ta:
            return SkillResult(success=False, error=ta["error"])
        context.analysis["indicators"] = ta
        return SkillResult(success=True, data=ta)

    def _detect_patterns(self, context: SkillContext, df) -> SkillResult:
        patterns = self.patterns.detect_all(df)
        context.analysis["patterns"] = patterns
        return SkillResult(success=True, data=patterns)

    def _find_levels(self, context: SkillContext, df) -> SkillResult:
        levels = self.levels.find_support_resistance(df)
        context.analysis["levels"] = levels
        return SkillResult(success=True, data=levels)

    def _full(self, context: SkillContext, df) -> SkillResult:
        ta = self.technical.analyze(df)
        patterns = self.patterns.detect_all(df)
        levels = self.levels.find_support_resistance(df)

        data = {"indicators": ta, "patterns": patterns, "levels": levels}
        context.analysis.update(data)
        return SkillResult(
            success=True, data=data, next_skill="risk_management",
        )
