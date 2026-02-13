"""
Trading Strategy Skill — Wraps StrategyEngine for the skills framework.
"""

from ...trading.strategy_engine import StrategyEngine
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class TradingStrategySkill(BaseSkill):
    name = "trading_strategy"
    description = "Multi-strategy signal generation with confluence scoring"
    emoji = "🎯"
    category = SkillCategory.TRADING
    version = "1.0.0"
    capabilities = ["detect_signal", "list_strategies"]

    def __init__(self):
        super().__init__()
        self.engine = StrategyEngine()

    def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "detect_signal":
            return self._detect(context, **params)
        elif action == "list_strategies":
            return SkillResult(success=True, data=[
                "trend_following", "mean_reversion", "breakout",
            ])
        return SkillResult(success=False, error=f"Unknown action: {action}")

    def _detect(self, context: SkillContext, **params) -> SkillResult:
        indicators = params.get("indicators") or context.analysis.get("indicators", {})
        levels_data = params.get("levels") or context.analysis.get("levels", {})
        patterns = params.get("patterns") or context.analysis.get("patterns", [])

        # Build indicator dict for StrategyEngine
        ind = {
            "adx": indicators.get("indicators", {}).get("ADX", {}).get("value"),
            "rsi": indicators.get("indicators", {}).get("RSI", {}).get("value"),
            "overall_bias": indicators.get("overall_bias"),
            "macd": indicators.get("indicators", {}).get("MACD", {}),
        }

        if ind["adx"] is None or ind["rsi"] is None:
            return SkillResult(success=False, error="Insufficient indicator data")

        levels = {
            "current_price": levels_data.get("current_price", 0),
            "support": levels_data.get("support", []),
            "resistance": levels_data.get("resistance", []),
        }

        try:
            signal = self.engine.detect_strategy(ind, levels, patterns)
            data = {
                "direction": signal.direction,
                "strategy": signal.strategy,
                "confidence": signal.confidence,
                "entry_price": signal.entry_price,
                "reasoning": signal.reasoning,
            }
            context.signals = data
            return SkillResult(
                success=True, data=data,
                next_skill="risk_management" if signal.direction in ("BUY", "SELL") else None,
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))
