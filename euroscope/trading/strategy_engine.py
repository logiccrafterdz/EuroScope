"""
Strategy Engine — Market Regime Detection

Identifies the current market regime and recommends the best
trading strategy: Trend Following, Mean Reversion, or Breakout.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("euroscope.trading.strategy_engine")


@dataclass
class StrategySignal:
    """Strategy recommendation with entry/exit rules."""
    strategy: str                    # "trend_following", "mean_reversion", "breakout"
    direction: str                   # "BUY", "SELL", "WAIT"
    confidence: float                # 0-100
    entry_rules: list[str] = field(default_factory=list)
    exit_rules: list[str] = field(default_factory=list)
    reasoning: str = ""
    regime: str = ""                 # "trending", "ranging", "breakout"


class StrategyEngine:
    """
    Detects market regime and recommends the optimal strategy.

    Strategies:
    - Trend Following: ride established trends with EMAs + ADX
    - Mean Reversion: fade extremes at key levels
    - Breakout: trade level breaks with momentum
    """

    def detect_strategy(self, indicators: dict, levels: dict,
                        patterns: list = None) -> StrategySignal:
        """
        Analyze market conditions and recommend a strategy.

        Args:
            indicators: Technical indicator data (RSI, MACD, EMA, ADX, BB, ATR)
            levels: {"current_price", "support", "resistance"}
            patterns: Detected chart patterns

        Returns:
            StrategySignal with recommended action
        """
        regime = self._detect_regime(indicators)
        patterns = patterns or []

        if regime == "trending":
            return self._trend_following(indicators, levels, patterns)
        elif regime == "breakout":
            return self._breakout_strategy(indicators, levels, patterns)
        else:
            return self._mean_reversion(indicators, levels, patterns)

    def _detect_regime(self, indicators: dict) -> str:
        """
        Determine market regime from indicators.

        - trending: ADX > 25, clear EMA alignment
        - ranging: ADX < 20, price between BBands
        - breakout: price at extremes with momentum
        """
        adx = indicators.get("adx")
        rsi = indicators.get("rsi")
        bb = indicators.get("bollinger", {})
        overall_bias = indicators.get("overall_bias", "neutral")

        # Strong trend
        if adx is not None and adx > 25:
            return "trending"

        # Check for breakout conditions
        bb_upper = bb.get("upper")
        bb_lower = bb.get("lower")
        current = bb.get("current_price", 0)

        if bb_upper and bb_lower and current:
            bb_width = (bb_upper - bb_lower) / current * 100 if current else 0
            if bb_width < 0.3:  # Tight squeeze
                return "breakout"
            if current > bb_upper or current < bb_lower:
                return "breakout"

        # RSI extremes can signal breakout too
        if rsi is not None and (rsi > 75 or rsi < 25):
            return "breakout"

        return "ranging"

    # ─── Trend Following ─────────────────────────────────────

    def _trend_following(self, indicators: dict, levels: dict,
                         patterns: list) -> StrategySignal:
        """
        Trend Following strategy — ride the trend with EMAs.

        Entry: EMA crossover + ADX confirmation
        Exit: EMA cross back or trailing stop
        """
        bias = indicators.get("overall_bias", "neutral")
        adx = indicators.get("adx", 0)
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", {})

        confidence = 40.0
        entry_rules = []
        exit_rules = []
        direction = "WAIT"

        # Determine direction
        if bias == "bullish":
            direction = "BUY"
            entry_rules.append("Price above EMA 20 & 50 (uptrend aligned)")
            confidence += 15
        elif bias == "bearish":
            direction = "SELL"
            entry_rules.append("Price below EMA 20 & 50 (downtrend aligned)")
            confidence += 15

        # ADX confirmation
        if adx > 30:
            entry_rules.append(f"ADX strong ({adx:.0f} > 30)")
            confidence += 15
        elif adx > 25:
            entry_rules.append(f"ADX moderate ({adx:.0f} > 25)")
            confidence += 8

        # MACD alignment
        hist = macd.get("histogram_latest")
        if hist is not None:
            if (direction == "BUY" and hist > 0) or (direction == "SELL" and hist < 0):
                entry_rules.append("MACD histogram confirms direction")
                confidence += 10

        # RSI not extreme (trend has room)
        if 35 < rsi < 65:
            entry_rules.append(f"RSI has room to move ({rsi:.0f})")
            confidence += 5

        # Bullish patterns in uptrend
        for p in patterns:
            if p.get("bias") == bias:
                entry_rules.append(f"Pattern confirms: {p.get('name', 'unknown')}")
                confidence += 8

        exit_rules = [
            "Trailing stop: 1.5× ATR below/above entry",
            "EMA 20 crosses back against direction",
            "ADX drops below 20 (trend weakening)",
        ]

        return StrategySignal(
            strategy="trend_following",
            direction=direction,
            confidence=min(confidence, 95),
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            reasoning=f"Market in strong trend (ADX: {adx:.0f}), bias: {bias}",
            regime="trending",
        )

    # ─── Mean Reversion ──────────────────────────────────────

    def _mean_reversion(self, indicators: dict, levels: dict,
                        patterns: list) -> StrategySignal:
        """
        Mean Reversion — fade extremes at key levels.

        Entry: RSI extreme + price at support/resistance + BB band touch
        Exit: RSI returns to 50 or price reaches mid-BB
        """
        rsi = indicators.get("rsi", 50)
        bb = indicators.get("bollinger", {})
        current_price = levels.get("current_price", 0)
        support = levels.get("support", [])
        resistance = levels.get("resistance", [])

        confidence = 35.0
        entry_rules = []
        direction = "WAIT"

        # Oversold at support → BUY
        if rsi < 35:
            direction = "BUY"
            entry_rules.append(f"RSI oversold ({rsi:.0f})")
            confidence += 15

            if support and current_price:
                nearest_s = support[0]
                dist_pips = (current_price - nearest_s) * 10000
                if dist_pips < 20:
                    entry_rules.append(f"Near support {nearest_s} ({dist_pips:.0f} pips)")
                    confidence += 15

            bb_lower = bb.get("lower")
            if bb_lower and current_price and current_price <= bb_lower * 1.001:
                entry_rules.append("Price at/below lower Bollinger Band")
                confidence += 10

        # Overbought at resistance → SELL
        elif rsi > 65:
            direction = "SELL"
            entry_rules.append(f"RSI overbought ({rsi:.0f})")
            confidence += 15

            if resistance and current_price:
                nearest_r = resistance[0]
                dist_pips = (nearest_r - current_price) * 10000
                if dist_pips < 20:
                    entry_rules.append(f"Near resistance {nearest_r} ({dist_pips:.0f} pips)")
                    confidence += 15

            bb_upper = bb.get("upper")
            if bb_upper and current_price and current_price >= bb_upper * 0.999:
                entry_rules.append("Price at/above upper Bollinger Band")
                confidence += 10

        # Reversal patterns
        for p in patterns:
            p_bias = p.get("bias", "")
            if direction == "BUY" and p_bias == "bullish":
                entry_rules.append(f"Reversal pattern: {p.get('name', 'unknown')}")
                confidence += 10
            elif direction == "SELL" and p_bias == "bearish":
                entry_rules.append(f"Reversal pattern: {p.get('name', 'unknown')}")
                confidence += 10

        exit_rules = [
            "RSI returns to 45-55 range",
            "Price reaches middle Bollinger Band",
            "Stop loss: below nearest support / above nearest resistance",
        ]

        return StrategySignal(
            strategy="mean_reversion",
            direction=direction,
            confidence=min(confidence, 90),
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            reasoning=f"Ranging market, RSI at {rsi:.0f} — looking for mean reversion",
            regime="ranging",
        )

    # ─── Breakout ────────────────────────────────────────────

    def _breakout_strategy(self, indicators: dict, levels: dict,
                           patterns: list) -> StrategySignal:
        """
        Breakout — trade level breaks with momentum.

        Entry: Price breaks S/R with RSI/MACD confirmation
        Exit: Opposite level hit or momentum fades
        """
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", {})
        current_price = levels.get("current_price", 0)
        support = levels.get("support", [])
        resistance = levels.get("resistance", [])

        confidence = 35.0
        entry_rules = []
        direction = "WAIT"

        # Breakout above resistance
        if resistance and current_price:
            nearest_r = resistance[0]
            if current_price > nearest_r:
                direction = "BUY"
                entry_rules.append(f"Price broke above resistance {nearest_r}")
                confidence += 20

                # Momentum confirmation
                hist = macd.get("histogram_latest")
                if hist and hist > 0:
                    entry_rules.append("MACD momentum confirms breakout")
                    confidence += 10

                if rsi > 50:
                    entry_rules.append(f"RSI bullish ({rsi:.0f})")
                    confidence += 5

        # Breakdown below support
        if direction == "WAIT" and support and current_price:
            nearest_s = support[0]
            if current_price < nearest_s:
                direction = "SELL"
                entry_rules.append(f"Price broke below support {nearest_s}")
                confidence += 20

                hist = macd.get("histogram_latest")
                if hist and hist < 0:
                    entry_rules.append("MACD momentum confirms breakdown")
                    confidence += 10

                if rsi < 50:
                    entry_rules.append(f"RSI bearish ({rsi:.0f})")
                    confidence += 5

        # Breakout patterns
        for p in patterns:
            if "breakout" in p.get("name", "").lower():
                entry_rules.append(f"Pattern: {p.get('name')}")
                confidence += 10

        exit_rules = [
            "Next major S/R level as target",
            "Stop loss: back below/above broken level + 5 pip buffer",
            "Trail stop after 20+ pip move in favor",
        ]

        return StrategySignal(
            strategy="breakout",
            direction=direction,
            confidence=min(confidence, 90),
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            reasoning="Potential breakout detected at key level",
            regime="breakout",
        )

    # ─── Formatting ──────────────────────────────────────────

    def format_strategy(self, sig: StrategySignal) -> str:
        """Format strategy signal for Telegram display."""
        strategy_names = {
            "trend_following": "📈 Trend Following",
            "mean_reversion": "🔄 Mean Reversion",
            "breakout": "💥 Breakout",
        }

        dir_icon = "🟢" if sig.direction == "BUY" else "🔴" if sig.direction == "SELL" else "⚪"
        strat_name = strategy_names.get(sig.strategy, sig.strategy)

        lines = [
            f"🧠 *Strategy Recommendation*\n",
            f"📊 Regime: *{sig.regime.title()}*",
            f"🎯 Strategy: *{strat_name}*",
            f"{dir_icon} Direction: *{sig.direction}* ({sig.confidence:.0f}% confidence)\n",
        ]

        if sig.entry_rules:
            lines.append("✅ *Entry Rules:*")
            for rule in sig.entry_rules:
                lines.append(f"  • {rule}")

        if sig.exit_rules:
            lines.append("\n🚪 *Exit Rules:*")
            for rule in sig.exit_rules:
                lines.append(f"  • {rule}")

        return "\n".join(lines)
