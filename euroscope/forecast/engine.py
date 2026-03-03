"""
AI Forecasting Engine

Combines all data sources to generate directional forecasts
and tracks accuracy over time.
"""

import logging
import re
from typing import Optional

from ..brain.agent import Agent
from ..brain.memory import Memory
from ..brain.orchestrator import Orchestrator, SkillContext

logger = logging.getLogger("euroscope.forecast")


class Forecaster:
    """Generates AI-powered EUR/USD forecasts with self-learning."""

    def __init__(self, agent: Agent, memory: Memory, orchestrator: Orchestrator, pattern_tracker=None):
        self.agent = agent
        self.memory = memory
        self.orchestrator = orchestrator
        self.pattern_tracker = pattern_tracker

    async def generate_forecast(self, timeframe: str = "24 hours") -> dict:
        """Generate a comprehensive AI forecast for EUR/USD."""

        # Use Orchestrator to gather all necessary data via Skills
        ctx = await self.orchestrator.run_full_analysis_pipeline()

        # Extract data from context
        price_info = ctx.get_result("market_data")["data"] if ctx.get_result("market_data") else {}
        ta_results = ctx.get_result("technical_analysis")["data"] if ctx.get_result("technical_analysis") else {}
        news_text = ctx.get_result("fundamental_analysis")["data"].get("formatted", "No news available") if ctx.get_result("fundamental_analysis") else "No news available"
        signal_data = {}
        strat_entry = ctx.get_result("trading_strategy")
        if strat_entry and isinstance(strat_entry.get("data"), dict):
            signal_data = strat_entry.get("data") or {}
        elif isinstance(ctx.signals, dict) and ctx.signals:
            signal_data = ctx.signals
        strategy_signal = "No strategy signal available."
        if signal_data:
            direction = signal_data.get("direction", "NEUTRAL")
            strategy = signal_data.get("strategy", "unknown")
            confidence = signal_data.get("confidence", 0)
            regime = signal_data.get("regime") or ""
            reasoning = signal_data.get("reasoning") or ""
            entry_price = signal_data.get("entry_price")
            parts = [
                f"Direction: {direction}",
                f"Strategy: {strategy}",
                f"Confidence: {confidence}",
            ]
            if regime:
                parts.append(f"Regime: {regime}")
            if entry_price not in (None, 0, 0.0):
                parts.append(f"Entry: {entry_price}")
            if reasoning:
                parts.append(f"Reasoning: {reasoning}")
            strategy_signal = "\n".join(parts)

        # Learning context
        learning = await self._build_learning_context(
            price_info=price_info,
            ta_results=ta_results,
            timeframe=timeframe,
        )

        # Build data strings for the AI
        if isinstance(price_info, dict) and price_info:
            price_str = "\n".join(f"  {k}: {v}" for k, v in price_info.items())
        elif hasattr(price_info, 'empty') and not price_info.empty:
            price_str = price_info.head(20).to_string()
        else:
            price_str = "N/A"
        
        # Use existing formatting helpers or results from skills
        ta_timeframe = ta_results.get("timeframe") or price_info.get("timeframe") or "H1"
        ta_str = self._format_ta_for_prompt(ta_results, ta_timeframe)
        
        patterns_str = self._format_patterns_for_prompt(ta_results.get("patterns", []))
        levels_str = self._format_levels_for_prompt(
            ta_results.get("levels", {}), 
            ta_results.get("fibonacci", {})
        )

        # Generate AI forecast
        forecast_text = await self.agent.forecast(
            price_data=price_str,
            technical_summary=ta_str,
            patterns=patterns_str,
            levels=levels_str,
            news=news_text,
            strategy_signal=strategy_signal,
            prediction_history=learning,
            timeframe=timeframe,
        )

        # Extract direction and confidence from AI response
        direction, confidence = self._parse_forecast(forecast_text)

        # Record prediction for accuracy tracking
        pred_id = None
        if direction:
            pred_id = await self.memory.record_prediction(
                direction=direction,
                confidence=confidence,
                reasoning=forecast_text[:500],
                target_price=price_info.get("price"),
                timeframe=timeframe,
            )
            if self.agent.vector_memory:
                self.agent.vector_memory.store_analysis(
                    forecast_text[:800],
                    metadata={
                        "timeframe": timeframe,
                        "direction": direction,
                        "confidence": confidence,
                    },
                )

        return {
            "text": forecast_text,
            "direction": direction,
            "confidence": confidence,
            "prediction_id": pred_id,
            "price": price_info.get("price"),
        }

    async def _build_learning_context(self, price_info: dict, ta_results: dict, timeframe: str) -> str:
        parts = [await self.memory.get_learning_context()]

        patterns = ta_results.get("patterns", []) if ta_results else []
        if self.pattern_tracker and patterns:
            rates = await self.pattern_tracker.get_success_rates()
            tf = ta_results.get("timeframe") or price_info.get("timeframe") or "H1"
            lines = []
            for p in patterns:
                name = p.get("name") or p.get("pattern")
                key = f"{name}_{tf}"
                entry = rates.get(key)
                if entry:
                    lines.append(
                        f"- {entry['pattern']} ({entry['timeframe']}): {entry['success_rate']}% "
                        f"({entry['successes']}/{entry['total']})"
                    )
            if lines:
                parts.append("Pattern performance for similar setups:\n" + "\n".join(lines))

        if self.agent.vector_memory:
            bias = ta_results.get("indicators", {}).get("overall_bias", "")
            context_seed = f"EUR/USD price {price_info.get('price')} bias {bias} timeframe {timeframe}"
            historical = self.agent.vector_memory.get_relevant_context(context_seed)
            if historical:
                parts.append(historical)

        return "\n\n".join(p for p in parts if p)

    def _parse_forecast(self, text: str) -> tuple[str, float]:
        """Extract direction and confidence from AI forecast text using strict parsing."""
        text_upper = text.upper()

        # 1. Stricter Direction Matching (Prioritize Explicit Bias)
        direction = "NEUTRAL"
        bias_match = re.search(r'(?i)bias:\s*\*?\**(BULLISH|BEARISH|NEUTRAL)', text_upper)
        if bias_match:
            direction = bias_match.group(1).upper()
        else:
            # Fallback to broader search if explicit header is missing
            if "BULLISH" in text_upper:
                direction = "BULLISH"
            elif "BEARISH" in text_upper:
                direction = "BEARISH"

        # 2. Stricter Confidence Matching (Avoid grabbing unrelated percentages like inflation rate)
        confidence = 50.0
        # Match "Conviction: 75%", "AI Conviction: 80%", etc.
        conf_match = re.search(r'(?i)(?:conviction|confidence)(?:[^\d]*)(\d{1,3})(?:%)?', text)
        if conf_match:
            confidence = float(conf_match.group(1))
        else:
            # Only fallback to raw keywords if explicit percentage is missing
            if "HIGH" in text_upper:
                confidence = 75.0
            elif "MEDIUM" in text_upper:
                confidence = 55.0
            elif "LOW" in text_upper:
                confidence = 35.0

        return direction, min(confidence, 95.0)

    @staticmethod
    def _format_ta_for_prompt(ta: dict, tf: str) -> str:
        if "error" in ta:
            return f"{tf}: {ta['error']}"
        if not ta.get("indicators"):
            return f"{tf}: No data"
        ind = ta["indicators"]
        return (
            f"\n{tf} Timeframe:"
            f"\n  RSI: {ind.get('RSI', {}).get('value', 'N/A')} ({ind.get('RSI', {}).get('signal', 'N/A')})"
            f"\n  MACD: {ind.get('MACD', {}).get('signal_text', 'N/A')}"
            f"\n  Trend: {ind.get('EMA', {}).get('trend', 'N/A')}"
            f"\n  ADX: {ind.get('ADX', {}).get('value', 'N/A')} ({ind.get('ADX', {}).get('strength', 'N/A')})"
            f"\n  Overall: {ta.get('overall_bias', 'N/A')}"
        )

    @staticmethod
    def _format_patterns_for_prompt(patterns: list) -> str:
        if not patterns:
            return "No patterns detected"
        return "\n".join(f"  - {p['pattern']} ({p['type']}, confidence: {p.get('confidence', '?')}%)" for p in patterns)

    @staticmethod
    def _format_levels_for_prompt(sr: dict, fib: dict) -> str:
        parts = []
        if sr.get("support"):
            parts.append(f"Support: {', '.join(str(s) for s in sr['support'][:3])}")
        if sr.get("resistance"):
            parts.append(f"Resistance: {', '.join(str(r) for r in sr['resistance'][:3])}")
        if fib.get("levels"):
            parts.append(f"Fibonacci ({fib.get('direction', 'N/A')}): 38.2% = {fib['levels'].get('38%', 'N/A')}, 50% = {fib['levels'].get('50%', 'N/A')}, 61.8% = {fib['levels'].get('61%', 'N/A')}")
        return "\n".join(parts) if parts else "No level data"
