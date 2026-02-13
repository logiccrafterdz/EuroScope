"""
Signal Generator

Combines multiple indicators and patterns into actionable trading signals
with confluence scoring.
"""

import logging
from typing import Optional

import pandas as pd

from .technical import TechnicalAnalyzer
from .patterns import PatternDetector
from .levels import LevelAnalyzer

logger = logging.getLogger("euroscope.analysis.signals")


class SignalGenerator:
    """Generates buy/sell signals based on multi-indicator confluence."""

    def __init__(self):
        self.technical = TechnicalAnalyzer()
        self.patterns = PatternDetector()
        self.levels = LevelAnalyzer()

    def generate_signals(self, df: pd.DataFrame, timeframe: str = "H1") -> dict:
        """
        Generate trading signals by combining all analysis.

        Returns signal dict with direction, strength, reasoning.
        """
        if df is None or df.empty or len(df) < 30:
            return {"signal": "NONE", "reason": "Insufficient data"}

        # Run all analysis
        ta_result = self.technical.analyze(df)
        if "error" in ta_result:
            return {"signal": "NONE", "reason": ta_result["error"]}

        detected_patterns = self.patterns.detect_all(df)
        sr_levels = self.levels.find_support_resistance(df)

        # Score system: positive = bullish, negative = bearish
        score = 0
        reasons = []
        indicators = ta_result["indicators"]

        # 1. RSI Signal
        rsi_val = indicators["RSI"]["value"]
        if rsi_val <= 30:
            score += 2
            reasons.append(f"RSI oversold ({rsi_val})")
        elif rsi_val >= 70:
            score -= 2
            reasons.append(f"RSI overbought ({rsi_val})")
        elif rsi_val < 45:
            score -= 1
            reasons.append(f"RSI bearish ({rsi_val})")
        elif rsi_val > 55:
            score += 1
            reasons.append(f"RSI bullish ({rsi_val})")

        # 2. MACD Signal
        if indicators["MACD"]["signal_text"] == "Bullish":
            score += 1
            if indicators["MACD"]["histogram"] > 0:
                score += 1
                reasons.append("MACD bullish + positive histogram")
            else:
                reasons.append("MACD bullish crossover")
        else:
            score -= 1
            if indicators["MACD"]["histogram"] < 0:
                score -= 1
                reasons.append("MACD bearish + negative histogram")
            else:
                reasons.append("MACD bearish crossover")

        # 3. EMA Trend
        ema_trend = indicators["EMA"]["trend"]
        if "uptrend" in ema_trend.lower():
            score += 2 if "strong" in ema_trend.lower() else 1
            reasons.append("EMA trend bullish")
        elif "downtrend" in ema_trend.lower():
            score -= 2 if "strong" in ema_trend.lower() else 1
            reasons.append("EMA trend bearish")

        # 4. Stochastic
        stoch_signal = indicators["Stochastic"]["signal"]
        if "Oversold" in stoch_signal:
            score += 1
            reasons.append("Stochastic oversold")
        elif "Overbought" in stoch_signal:
            score -= 1
            reasons.append("Stochastic overbought")

        # 5. Pattern Signals
        for pattern in detected_patterns:
            if pattern["type"] == "bullish":
                score += 2
                reasons.append(f"Pattern: {pattern['pattern']} (bullish)")
            elif pattern["type"] == "bearish":
                score -= 2
                reasons.append(f"Pattern: {pattern['pattern']} (bearish)")

        # 6. Support/Resistance proximity
        current = ta_result["price"]
        nearest_support = sr_levels["support"][0] if sr_levels.get("support") else None
        nearest_resistance = sr_levels["resistance"][0] if sr_levels.get("resistance") else None

        if nearest_support and (current - nearest_support) < 0.0010:
            score += 1
            reasons.append(f"Near support {nearest_support}")
        if nearest_resistance and (nearest_resistance - current) < 0.0010:
            score -= 1
            reasons.append(f"Near resistance {nearest_resistance}")

        # Determine signal
        if score >= 4:
            signal = "STRONG BUY"
            emoji = "🟢🟢"
        elif score >= 2:
            signal = "BUY"
            emoji = "🟢"
        elif score <= -4:
            signal = "STRONG SELL"
            emoji = "🔴🔴"
        elif score <= -2:
            signal = "SELL"
            emoji = "🔴"
        else:
            signal = "NEUTRAL"
            emoji = "⚪"

        return {
            "signal": signal,
            "emoji": emoji,
            "score": score,
            "timeframe": timeframe,
            "price": current,
            "reasons": reasons,
            "patterns": detected_patterns,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
        }

    def format_signal(self, result: dict) -> str:
        """Format signal for Telegram display."""
        if result["signal"] == "NONE":
            return f"⚠️ {result.get('reason', 'No signal available')}"

        lines = [
            f"🎯 *EUR/USD Signal ({result['timeframe']})*\n",
            f"{result['emoji']} *{result['signal']}* (score: {result['score']:+d})",
            f"💰 Price: `{result['price']}`\n",
        ]

        if result.get("nearest_support"):
            lines.append(f"🟢 Nearest Support: `{result['nearest_support']}`")
        if result.get("nearest_resistance"):
            lines.append(f"🔴 Nearest Resistance: `{result['nearest_resistance']}`")

        lines.append(f"\n📋 *Reasoning:*")
        for reason in result["reasons"]:
            lines.append(f"  • {reason}")

        if result.get("patterns"):
            lines.append(f"\n🔍 *Patterns:*")
            for p in result["patterns"]:
                icon = {"bullish": "🟢", "bearish": "🔴"}.get(p["type"], "⚪")
                lines.append(f"  {icon} {p['pattern']}")

        return "\n".join(lines)
