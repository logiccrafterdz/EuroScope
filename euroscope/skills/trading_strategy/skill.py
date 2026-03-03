"""
Trading Strategy Skill — Wraps StrategyEngine for the skills framework.
"""

import asyncio
import re

from ...data.models import TradingSignal
from ...trading.strategy_engine import StrategyEngine, StrategySignal
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
        self._agent = None

    def set_agent(self, agent):
        self._agent = agent

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
            "adx": self._to_float(indicators.get("indicators", {}).get("ADX", {}).get("value")),
            "rsi": self._to_float(indicators.get("indicators", {}).get("RSI", {}).get("value")),
            "overall_bias": indicators.get("overall_bias"),
            "macd": indicators.get("indicators", {}).get("MACD", {}),
            "bollinger": indicators.get("indicators", {}).get("Bollinger", {}),
            "ema": indicators.get("indicators", {}).get("EMA", {}),
            "atr": indicators.get("indicators", {}).get("ATR", {}),
            "stochastic": indicators.get("indicators", {}).get("Stochastic", {}),
            "tick_volume_5m": context.market_data.get("tick_volume_5m", 0),
        }

        if ind["adx"] is None or ind["rsi"] is None:
            missing = "ADX" if ind["adx"] is None else "RSI"
            return SkillResult(success=False, error=f"Insufficient indicator data: {missing} is missing")

        levels = {
            "current_price": levels_data.get("current_price", 0),
            "support": levels_data.get("support", []),
            "resistance": levels_data.get("resistance", []),
        }

        try:
            if context.metadata.get("emergency_mode"):
                fallback_signal, regime, strength = self._fallback_to_technical_only(context, ind, levels)
                return self._build_from_fallback(context, fallback_signal, regime, strength)

            uncertainty = {
                "confidence_adjustment": context.metadata.get("confidence_adjustment", 1.0),
                "high_uncertainty": context.metadata.get("high_uncertainty", False),
            }
            macro_data = context.analysis.get("macro_data", {})
            signal = self.engine.detect_strategy(
                ind, levels, patterns, uncertainty=uncertainty, macro_data=macro_data
            )

            # --- Phase 2: MTF Confirmation Check ---
            mtf_bias = context.metadata.get("mtf_bias", "neutral")
            if signal.direction in ("BUY", "SELL") and mtf_bias != "neutral":
                is_conflict = (signal.direction == "BUY" and mtf_bias == "bearish") or \
                              (signal.direction == "SELL" and mtf_bias == "bullish")
                if is_conflict:
                    signal.confidence *= 0.5  # Heavy penalty
                    if isinstance(signal.reasoning, list):
                        signal.reasoning.append(f"Warning: Counter H-TF Trend ({mtf_bias})")
                    else:
                        signal.reasoning += f" | Warning: Counter H-TF Trend ({mtf_bias})"

            if isinstance(signal, TradingSignal):
                return self._build_from_fallback(
                    context,
                    signal,
                    context.metadata.get("regime", ""),
                    context.metadata.get("fallback_strength", ""),
                )

            blocking_reason = None
            if signal.strategy == "uncertain":
                blocking_reason = "high_uncertainty_without_macro_confirmation"
                context.metadata["blocking_reason"] = blocking_reason
                uncertainty_data = context.analysis.get("uncertainty")
                if isinstance(uncertainty_data, dict):
                    uncertainty_data["blocking_reason"] = blocking_reason
            adjusted_confidence, multiplier = self._apply_pattern_multipliers(
                signal.confidence, signal.direction, patterns, context.metadata.get("pattern_multipliers", {})
            )
            data = {
                "direction": signal.direction,
                "strategy": signal.strategy,
                "confidence": adjusted_confidence,
                "raw_confidence": signal.confidence,
                "confidence_multiplier": multiplier,
                "blocking_reason": blocking_reason,
                "entry_price": getattr(signal, "entry_price", 0),
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

    def _fallback_to_technical_only(self, context: SkillContext, indicators: dict,
                                    levels: dict) -> tuple[TradingSignal, str, str]:
        adx = self._to_float(indicators.get("adx"))
        rsi = self._to_float(indicators.get("rsi"))
        macd_hist = self._to_float(self._get_macd_histogram(indicators.get("macd", {})))
        bullish = rsi is not None and macd_hist is not None and rsi >= 55 and macd_hist > 0
        bearish = rsi is not None and macd_hist is not None and rsi <= 45 and macd_hist < 0

        direction = "WAIT"
        confidence = 0.0
        strength = "NEUTRAL"
        if adx is not None and adx > 25 and (bullish or bearish):
            strength = "STRONG_SIGNAL"
            direction = "BUY" if bullish else "SELL"
            confidence = 80.0
        elif adx is not None and adx < 20:
            strength = "NEUTRAL"
            direction = "WAIT"
            confidence = 0.0
        else:
            strength = "WEAK_SIGNAL"
            direction = "BUY" if bullish else "SELL" if bearish else "WAIT"
            confidence = 50.0

        regime = self._infer_regime_from_adx(adx)
        context.metadata["regime"] = regime
        context.metadata["fallback_strength"] = strength

        entry_price = levels.get("current_price", 0)
        timeframe = context.market_data.get("timeframe", "H1")
        reasoning = f"Technical fallback {strength} based on ADX/RSI/MACD"
        signal = TradingSignal(
            direction=direction,
            entry_price=entry_price,
            stop_loss=0.0,
            take_profit=0.0,
            confidence=confidence,
            timeframe=timeframe,
            source="technical_fallback",
            reasoning=reasoning,
        )
        return signal, regime, strength

    def _build_from_fallback(self, context: SkillContext, signal: TradingSignal,
                             regime: str, strength: str) -> SkillResult:
        data = {
            "direction": signal.direction,
            "strategy": strength if strength else "technical_fallback",
            "confidence": signal.confidence,
            "raw_confidence": signal.confidence,
            "confidence_multiplier": 1.0,
            "blocking_reason": None,
            "entry_price": signal.entry_price,
            "reasoning": signal.reasoning,
            "regime": regime,
            "source": signal.source,
        }
        context.signals = data
        context.metadata["regime"] = regime
        formatted = self._format_signal(data)
        return SkillResult(
            success=True,
            data=data,
            next_skill="risk_management" if signal.direction in ("BUY", "SELL") else None,
            metadata={"formatted": formatted},
        )

    @staticmethod
    def _get_macd_histogram(macd: dict) -> float | None:
        if not isinstance(macd, dict):
            return None
        return macd.get("histogram", macd.get("histogram_latest"))

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _infer_regime_from_adx(adx: float | None) -> str:
        if adx is None:
            return "unknown"
        if adx > 25:
            return "trending"
        if adx < 20:
            return "ranging"
        return "transitional"

    @staticmethod
    def _parse_llm_response(response: str) -> tuple[str, float] | None:
        if not response:
            return None
        text = response.upper()
        direction = None
        for candidate in ("BUY", "SELL", "WAIT"):
            if candidate in text:
                direction = candidate
                break
        if not direction:
            return None
        numbers = re.findall(r"(\d+(?:\.\d+)?)", response)
        confidence = float(numbers[0]) if numbers else 50.0
        confidence = max(0.0, min(100.0, confidence))
        return direction, confidence

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
