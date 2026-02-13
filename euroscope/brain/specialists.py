"""
Specialist Agents for EUR/USD Analysis

Each specialist focuses on one domain and produces a structured verdict.
The Orchestrator combines them into a final recommendation.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("euroscope.brain.specialists")


class BaseSpecialist(ABC):
    """Base class for all specialist agents."""

    name: str = "base"
    weight: float = 0.25  # Default weight in consensus

    @abstractmethod
    def analyze(self, context: dict) -> dict:
        """
        Analyze market context and return a verdict.

        Args:
            context: dict with relevant data for this specialist

        Returns:
            {
                "specialist": str,
                "verdict": "bullish" | "bearish" | "neutral",
                "confidence": float (0-100),
                "reasoning": str,
                "key_points": list[str],
            }
        """
        ...

    def _make_verdict(self, verdict: str, confidence: float,
                      reasoning: str, key_points: list[str]) -> dict:
        """Helper to build a standardized verdict dict."""
        return {
            "specialist": self.name,
            "verdict": verdict.lower(),
            "confidence": round(max(0, min(100, confidence)), 1),
            "reasoning": reasoning,
            "key_points": key_points,
        }


class TechnicalSpecialist(BaseSpecialist):
    """Analyzes technical indicators, patterns, and key levels."""

    name = "technical"
    weight = 0.35

    def analyze(self, context: dict) -> dict:
        indicators = context.get("indicators", {})
        patterns = context.get("patterns", [])
        levels = context.get("levels", {})

        signals = []
        confidence = 50.0

        # ── Trend indicators ──
        bias = indicators.get("overall_bias", "neutral")
        if bias == "bullish":
            signals.append(1)
            confidence += 10
        elif bias == "bearish":
            signals.append(-1)
            confidence += 10
        else:
            signals.append(0)

        # ── RSI ──
        rsi = indicators.get("rsi")
        if rsi is not None:
            if rsi > 70:
                signals.append(-0.5)  # overbought
                confidence += 5
            elif rsi < 30:
                signals.append(0.5)   # oversold
                confidence += 5

        # ── MACD ──
        macd_data = indicators.get("macd", {})
        if isinstance(macd_data, dict):
            histogram = macd_data.get("histogram_latest")
            if histogram is not None:
                if histogram > 0:
                    signals.append(0.5)
                else:
                    signals.append(-0.5)
                confidence += 5

        # ── Patterns ──
        if patterns:
            bullish_patterns = [p for p in patterns if p.get("bias") == "bullish"]
            bearish_patterns = [p for p in patterns if p.get("bias") == "bearish"]
            pattern_signal = (len(bullish_patterns) - len(bearish_patterns)) * 0.3
            signals.append(pattern_signal)
            confidence += min(len(patterns) * 3, 10)

        # ── Key Levels proximity ──
        current_price = levels.get("current_price", 0)
        support_levels = levels.get("support", [])
        resistance_levels = levels.get("resistance", [])

        if current_price and support_levels:
            nearest_support = support_levels[0] if support_levels else 0
            dist_to_support = (current_price - nearest_support) * 10000  # pips
            if dist_to_support < 15:
                signals.append(0.3)  # near support = potential bounce
                confidence += 5

        if current_price and resistance_levels:
            nearest_resistance = resistance_levels[0] if resistance_levels else 0
            dist_to_resistance = (nearest_resistance - current_price) * 10000
            if dist_to_resistance < 15:
                signals.append(-0.3)  # near resistance = potential rejection
                confidence += 5

        # ── Aggregate ──
        avg_signal = sum(signals) / len(signals) if signals else 0

        if avg_signal > 0.15:
            verdict = "bullish"
        elif avg_signal < -0.15:
            verdict = "bearish"
        else:
            verdict = "neutral"

        key_points = []
        key_points.append(f"Overall technical bias: {bias}")
        if rsi is not None:
            key_points.append(f"RSI: {rsi:.1f}")
        if patterns:
            key_points.append(f"{len(patterns)} chart pattern(s) detected")
        if support_levels:
            key_points.append(f"Nearest support: {support_levels[0]}")
        if resistance_levels:
            key_points.append(f"Nearest resistance: {resistance_levels[0]}")

        return self._make_verdict(
            verdict=verdict,
            confidence=min(confidence, 95),
            reasoning=f"Technical analysis shows {verdict} bias with {len(signals)} signals evaluated.",
            key_points=key_points,
        )


class FundamentalSpecialist(BaseSpecialist):
    """Analyzes macroeconomic data and central bank policy."""

    name = "fundamental"
    weight = 0.30

    def analyze(self, context: dict) -> dict:
        macro = context.get("macro", {})
        calendar = context.get("calendar", [])

        signals = []
        confidence = 45.0
        key_points = []

        # ── Interest rate differential ──
        rate_diff = macro.get("rate_differential", {})
        if rate_diff:
            diff = rate_diff.get("differential", 0)
            if diff >= 0.5:
                signals.append(-0.5)  # USD stronger
                key_points.append(f"Rate differential: {diff:+.2f}% favoring USD")
            elif diff <= -0.5:
                signals.append(0.5)   # EUR stronger
                key_points.append(f"Rate differential: {diff:+.2f}% favoring EUR")
            else:
                signals.append(0)
                key_points.append(f"Rate differential: {diff:+.2f}% (narrow)")
            confidence += 10

        # ── Yield spread ──
        yield_spread = macro.get("yield_spread", {})
        if yield_spread:
            spread = yield_spread.get("spread", 0)
            if spread > 1.0:
                signals.append(-0.3)  # USD bonds more attractive
                key_points.append(f"US-DE 10Y spread: {spread:+.2f}% (supports USD)")
            elif spread < -0.5:
                signals.append(0.3)
                key_points.append(f"US-DE 10Y spread: {spread:+.2f}% (supports EUR)")
            confidence += 8

        # ── CPI / Inflation ──
        cpi = macro.get("us_cpi", {})
        if cpi:
            yoy = cpi.get("yoy_change", 0)
            if yoy > 3.5:
                signals.append(-0.3)  # High inflation → more Fed hikes → USD strength
                key_points.append(f"US CPI YoY: {yoy}% (elevated)")
            elif yoy < 2.0:
                signals.append(0.3)   # Low inflation → less hawkish Fed
                key_points.append(f"US CPI YoY: {yoy}% (cooling)")
            confidence += 7

        # ── High-impact calendar events ──
        high_impact = [e for e in calendar if getattr(e, "impact", "") == "high"]
        if high_impact:
            key_points.append(f"{len(high_impact)} high-impact events upcoming")
            confidence = max(confidence - 5, 30)  # Reduce confidence before events

        # ── Aggregate ──
        avg_signal = sum(signals) / len(signals) if signals else 0

        if avg_signal > 0.15:
            verdict = "bullish"
        elif avg_signal < -0.15:
            verdict = "bearish"
        else:
            verdict = "neutral"

        if not key_points:
            key_points.append("Insufficient fundamental data available")

        return self._make_verdict(
            verdict=verdict,
            confidence=min(confidence, 90),
            reasoning=f"Fundamental analysis shows {verdict} outlook based on macro indicators.",
            key_points=key_points,
        )


class SentimentSpecialist(BaseSpecialist):
    """Analyzes market sentiment from news and social data."""

    name = "sentiment"
    weight = 0.20

    def analyze(self, context: dict) -> dict:
        sentiment_summary = context.get("sentiment_summary", {})
        news_articles = context.get("news_articles", [])

        confidence = 40.0
        key_points = []

        total = sentiment_summary.get("total", 0)
        avg_score = sentiment_summary.get("avg_score", 0)
        overall = sentiment_summary.get("overall", "neutral")
        bullish_count = sentiment_summary.get("bullish", 0)
        bearish_count = sentiment_summary.get("bearish", 0)

        if total > 0:
            key_points.append(f"News sentiment: {bullish_count}🟢 / {bearish_count}🔴 / {total - bullish_count - bearish_count}⚪")
            key_points.append(f"Average score: {avg_score:+.3f}")
            confidence += min(total * 3, 20)

            # Strong consensus boosts confidence
            if total > 5 and (bullish_count / total > 0.7 or bearish_count / total > 0.7):
                confidence += 10
                key_points.append("Strong news consensus detected")
        else:
            key_points.append("No recent news sentiment data")

        verdict = overall if overall in ("bullish", "bearish") else "neutral"

        return self._make_verdict(
            verdict=verdict,
            confidence=min(confidence, 85),
            reasoning=f"Sentiment analysis across {total} articles shows {verdict} bias.",
            key_points=key_points,
        )


class RiskSpecialist(BaseSpecialist):
    """Evaluates risk factors and conflicting signals."""

    name = "risk"
    weight = 0.15

    def analyze(self, context: dict) -> dict:
        """
        Doesn't produce bullish/bearish — instead evaluates
        overall risk level and flags concerns.
        """
        indicators = context.get("indicators", {})
        levels = context.get("levels", {})
        calendar = context.get("calendar", [])
        other_verdicts = context.get("other_verdicts", [])

        risk_score = 0  # 0 = low risk, 100 = high risk
        key_points = []

        # ── Check for conflicting specialist verdicts ──
        verdicts = [v.get("verdict", "neutral") for v in other_verdicts]
        unique_verdicts = set(verdicts)
        if len(unique_verdicts) > 1 and "neutral" not in unique_verdicts:
            risk_score += 25
            key_points.append("⚠️ Conflicting signals between specialists")

        if len(unique_verdicts) == 1 and "neutral" not in unique_verdicts:
            key_points.append("✅ All specialists agree")

        # ── Volatility check (ATR) ──
        atr = indicators.get("atr")
        if atr is not None:
            if atr > 0.0080:  # 80 pips — high volatility
                risk_score += 20
                key_points.append(f"⚠️ High volatility (ATR: {atr*10000:.0f} pips)")
            elif atr < 0.0030:
                key_points.append(f"Low volatility (ATR: {atr*10000:.0f} pips)")

        # ── Proximity to key levels ──
        current_price = levels.get("current_price", 0)
        support = levels.get("support", [])
        resistance = levels.get("resistance", [])

        if current_price and support and resistance:
            nearest_s = support[0] if support else current_price - 0.01
            nearest_r = resistance[0] if resistance else current_price + 0.01
            range_pips = (nearest_r - nearest_s) * 10000

            if range_pips < 30:
                risk_score += 15
                key_points.append(f"⚠️ Tight range ({range_pips:.0f} pips)")

        # ── High-impact events ──
        high_impact_events = [e for e in calendar if getattr(e, "impact", "") == "high"]
        if high_impact_events:
            risk_score += 15
            names = [e.name for e in high_impact_events[:3]]
            key_points.append(f"⚠️ High-impact events: {', '.join(names)}")

        # ── RSI extremes ──
        rsi = indicators.get("rsi")
        if rsi is not None:
            if rsi > 80 or rsi < 20:
                risk_score += 10
                key_points.append(f"⚠️ RSI at extreme ({rsi:.1f})")

        # Verdict based on risk level
        if risk_score >= 50:
            verdict = "neutral"  # High risk → recommend caution
            reasoning = "High risk environment — recommend reduced position size or staying out."
        elif risk_score >= 25:
            verdict = "neutral"
            reasoning = "Moderate risk — proceed with caution."
        else:
            verdict = "neutral"  # Risk specialist stays neutral by design
            reasoning = "Low risk environment — normal trading conditions."

        if not key_points:
            key_points.append("No significant risk factors identified")

        return self._make_verdict(
            verdict=verdict,
            confidence=min(100 - risk_score, 95),
            reasoning=reasoning,
            key_points=key_points,
        )
