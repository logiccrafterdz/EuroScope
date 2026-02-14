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
        self._tracker = None

    def set_provider(self, provider):
        """Inject the PriceProvider instance."""
        self._provider = provider

    def set_pattern_tracker(self, tracker):
        """Inject the PatternTracker instance."""
        self._tracker = tracker

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        df = params.get("df", context.market_data.get("candles"))
        
        # Auto-fetch if missing and provider available
        if (df is None or (hasattr(df, 'empty') and df.empty)) and self._provider:
            tf = params.get("timeframe", context.market_data.get("timeframe", "H1"))
            df = await self._provider.get_candles(timeframe=tf)
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
        
        formatted = self._format_analysis(ta)
        return SkillResult(success=True, data=ta, metadata={"formatted": formatted})

    def _format_analysis(self, data: dict) -> str:
        lines = ["📊 *Technical Analysis*"]
        bias = data.get("overall_bias", "N/A")
        icon = {"Bullish": "🟢", "Bearish": "🔴"}.get(bias, "⚪")
        lines.append(f"Bias: {icon} {bias}\n")

        ind = data.get("indicators", {})
        
        # RSI
        rsi = ind.get("RSI", {})
        lines.append(f"*RSI*: `{rsi.get('value', 0):.1f}` ({rsi.get('signal', 'N/A')})")
        
        # MACD
        macd = ind.get("MACD", {})
        lines.append(f"*MACD*: `{macd.get('macd', 0):.5f}` ({macd.get('signaltext', 'N/A')})")
        
        # Bands
        bb = ind.get("Bollinger", {})
        lines.append(f"*BB*: {bb.get('position', 'N/A')}")
        
        # ATR
        atr = ind.get("ATR", {})
        lines.append(f"*ATR*: `{atr.get('pips', 0):.1f} pips`")

        return "\n".join(lines)

    async def _detect_patterns(self, context: SkillContext, df) -> SkillResult:
        patterns = self.patterns.detect_all(df)
        context.analysis["patterns"] = patterns
        
        # Record patterns if tracker available
        multipliers = {}
        if self._tracker:
            tf = context.market_data.get("timeframe", "H1")
            price = float(df['Close'].iloc[-1])
            for p in patterns:
                name, signal = self._normalize_pattern(p)
                self._tracker.record_detection(name, tf, signal, price)
                multipliers[name] = self._tracker.get_confidence_multiplier(name, tf)

        formatted = self._format_patterns(patterns)
        return SkillResult(success=True, data=patterns, metadata={
            "formatted": formatted,
            "pattern_multipliers": multipliers
        })

    def _format_patterns(self, patterns: list) -> str:
        if not patterns:
            return "📉 No patterns detected."
        
        lines = ["🧩 *Detected Patterns*"]
        for p in patterns:
            name, signal = self._normalize_pattern(p)
            icon = "🟢" if signal == "BULLISH" else "🔴" if signal == "BEARISH" else "⚪"
            lines.append(f"{icon} {name} ({signal.capitalize()})")
        return "\n".join(lines)

    async def _find_levels(self, context: SkillContext, df) -> SkillResult:
        levels = self.levels.find_support_resistance(df)
        context.analysis["levels"] = levels
        formatted = self._format_levels(levels)
        return SkillResult(success=True, data=levels, metadata={"formatted": formatted})

    def _format_levels(self, levels: dict) -> str:
        lines = ["📏 *Key Levels*"]
        sup = levels.get("support", [])
        res = levels.get("resistance", [])
        
        lines.append(f"Supports: " + ", ".join([f"`{p:.5f}`" for p in sup[:3]]))
        lines.append(f"Resistances: " + ", ".join([f"`{p:.5f}`" for p in res[:3]]))
        return "\n".join(lines)

    async def _full(self, context: SkillContext, df) -> SkillResult:
        ta = self.technical.analyze(df)
        patterns = self.patterns.detect_all(df)
        levels = self.levels.find_support_resistance(df)

        # Record patterns if tracker available
        multipliers = {}
        if self._tracker:
            tf = context.market_data.get("timeframe", "H1")
            price = float(df['Close'].iloc[-1])
            for p in patterns:
                name, signal = self._normalize_pattern(p)
                self._tracker.record_detection(name, tf, signal, price)
                multipliers[name] = self._tracker.get_confidence_multiplier(name, tf)

        data = {"indicators": ta, "patterns": patterns, "levels": levels}
        context.analysis.update(data)
        if multipliers:
            context.metadata["pattern_multipliers"] = multipliers
        
        return SkillResult(
            success=True, data=data, next_skill="risk_management",
            metadata={"pattern_multipliers": multipliers}
        )

    @staticmethod
    def _normalize_pattern(pattern: dict) -> tuple[str, str]:
        name = pattern.get("name") or pattern.get("pattern") or "Unknown"
        raw_signal = pattern.get("signal") or pattern.get("type") or "neutral"
        signal = str(raw_signal).strip().lower()
        if signal == "bullish":
            return name, "BULLISH"
        if signal == "bearish":
            return name, "BEARISH"
        return name, "NEUTRAL"
