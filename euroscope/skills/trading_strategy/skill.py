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

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "detect_signal":
            return await self._detect(context, **params)
        elif action == "list_strategies":
            return SkillResult(success=True, data=[
                "trend_following", "mean_reversion", "breakout",
            ])
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _detect(self, context: SkillContext, **params) -> SkillResult:
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
            adjusted_confidence, multiplier = self._apply_pattern_multipliers(
                signal.confidence, signal.direction, patterns, context.metadata.get("pattern_multipliers", {})
            )
            data = {
                "direction": signal.direction,
                "strategy": signal.strategy,
                "confidence": adjusted_confidence,
                "raw_confidence": signal.confidence,
                "confidence_multiplier": multiplier,
                "entry_price": signal.entry_price,
                "reasoning": signal.reasoning,
                "regime": signal.regime,
            }
            context.signals = data
            context.metadata["regime"] = signal.regime
            
            formatted = self._format_signal(data)
            return SkillResult(
                success=True, data=data,
                next_skill="risk_management" if signal.direction in ("BUY", "SELL") else None,
                metadata={"formatted": formatted}
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _format_signal(self, data: dict) -> str:
        lines = ["🎯 *Trading Signal*"]
        direction = data.get("direction", "NONE")
        icon = {"BUY": "🟢", "SELL": "🔴"}.get(direction, "⚪")
        
        lines.append(f"{icon} *{direction}*")
        lines.append(f"Strategy: `{data.get('strategy', 'N/A')}`")
        lines.append(f"Confidence: `{data.get('confidence', 0)}%`")
        if data.get("confidence_multiplier", 1.0) != 1.0:
            lines.append(f"Pattern Multiplier: `{data.get('confidence_multiplier', 1.0)}x`")
        if data.get("regime"):
            lines.append(f"Regime: `{data.get('regime')}`")
        
        if direction in ("BUY", "SELL"):
            lines.append(f"Entry: `{data.get('entry_price', 0):.5f}`")
        
        reasoning = data.get("reasoning", [])
        if isinstance(reasoning, str) and reasoning:
            lines.append("\n📝 *Reasoning*:")
            lines.append(f"• {reasoning}")
        elif reasoning:
            lines.append("\n📝 *Reasoning*:")
            for r in reasoning:
                lines.append(f"• {r}")
                
        return "\n".join(lines)

    @staticmethod
    def _apply_pattern_multipliers(base_confidence: float, direction: str,
                                   patterns: list, multipliers: dict) -> tuple[float, float]:
        if direction not in ("BUY", "SELL") or not patterns:
            return round(base_confidence, 1), 1.0
        target_bias = "BULLISH" if direction == "BUY" else "BEARISH"
        matched = []
        for p in patterns:
            name = p.get("name") or p.get("pattern")
            bias = (p.get("signal") or p.get("type") or p.get("bias") or "neutral").lower()
            if bias == "bullish" and target_bias == "BULLISH":
                matched.append(multipliers.get(name, 1.0))
            elif bias == "bearish" and target_bias == "BEARISH":
                matched.append(multipliers.get(name, 1.0))
        if not matched:
            return round(base_confidence, 1), 1.0
        multiplier = round(sum(matched) / len(matched), 2)
        adjusted = min(95.0, max(0.0, base_confidence * multiplier))
        return round(adjusted, 1), multiplier
