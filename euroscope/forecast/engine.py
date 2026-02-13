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
from ..analysis.technical import TechnicalAnalyzer
from ..analysis.patterns import PatternDetector
from ..analysis.levels import LevelAnalyzer
from ..data.provider import PriceProvider
from ..data.news import NewsEngine
from ..data.calendar import EconomicCalendar

logger = logging.getLogger("euroscope.forecast")


class Forecaster:
    """Generates AI-powered EUR/USD forecasts with self-learning."""

    def __init__(self, agent: Agent, memory: Memory, price_provider: PriceProvider,
                 news_engine: NewsEngine):
        self.agent = agent
        self.memory = memory
        self.price_provider = price_provider
        self.news_engine = news_engine
        self.technical = TechnicalAnalyzer()
        self.patterns = PatternDetector()
        self.levels = LevelAnalyzer()
        self.calendar = EconomicCalendar()

    async def generate_forecast(self, timeframe: str = "24 hours") -> dict:
        """Generate a comprehensive AI forecast for EUR/USD."""

        # Gather all data
        price_info = self.price_provider.get_price()
        candles_h1 = self.price_provider.get_candles("H1", 100)
        candles_d1 = self.price_provider.get_candles("D1", 50)

        # Technical analysis
        ta_h1 = self.technical.analyze(candles_h1) if candles_h1 is not None else {}
        ta_d1 = self.technical.analyze(candles_d1) if candles_d1 is not None else {}

        # Patterns
        patterns_h1 = self.patterns.detect_all(candles_h1) if candles_h1 is not None else []
        patterns_d1 = self.patterns.detect_all(candles_d1) if candles_d1 is not None else []

        # Levels
        sr_levels = self.levels.find_support_resistance(candles_d1) if candles_d1 is not None else {}
        fib = self.levels.fibonacci_retracement(candles_d1) if candles_d1 is not None else {}

        # News (handle async)
        try:
            news = await self.news_engine.get_eurusd_news()
            news_text = self.news_engine.format_news(news)
        except Exception:
            news_text = "No news available"

        # Learning context
        learning = self.memory.get_learning_context()

        # Build data strings for the AI
        price_str = "\n".join(f"  {k}: {v}" for k, v in price_info.items()) if price_info else "N/A"
        ta_str = self._format_ta_for_prompt(ta_h1, "H1") + "\n" + self._format_ta_for_prompt(ta_d1, "D1")
        patterns_str = self._format_patterns_for_prompt(patterns_h1 + patterns_d1)
        levels_str = self._format_levels_for_prompt(sr_levels, fib)

        # Generate AI forecast
        forecast_text = await self.agent.forecast(
            price_data=price_str,
            technical_summary=ta_str,
            patterns=patterns_str,
            levels=levels_str,
            news=news_text,
            prediction_history=learning,
            timeframe=timeframe,
        )

        # Extract direction and confidence from AI response
        direction, confidence = self._parse_forecast(forecast_text)

        # Record prediction for accuracy tracking
        pred_id = None
        if direction:
            pred_id = self.memory.record_prediction(
                direction=direction,
                confidence=confidence,
                reasoning=forecast_text[:500],
                target_price=price_info.get("price"),
                timeframe=timeframe,
            )

        return {
            "text": forecast_text,
            "direction": direction,
            "confidence": confidence,
            "prediction_id": pred_id,
            "price": price_info.get("price"),
        }

    def _parse_forecast(self, text: str) -> tuple[str, float]:
        """Extract direction and confidence from AI forecast text."""
        text_upper = text.upper()

        # Direction
        direction = "NEUTRAL"
        if "BULLISH" in text_upper:
            direction = "BULLISH"
        elif "BEARISH" in text_upper:
            direction = "BEARISH"

        # Confidence
        confidence = 50.0
        # Try to find percentage
        match = re.search(r'(\d{1,3})%', text)
        if match:
            confidence = float(match.group(1))
        elif "HIGH" in text_upper:
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
