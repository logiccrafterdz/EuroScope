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
class RegimeInfo:
    """Market regime classification with strength and evidence."""
    regime: str          # "trending", "ranging", "breakout"
    strength: float      # 0.0 - 1.0 (confidence in the classification)
    direction: str       # "bullish", "bearish", "neutral"
    details: dict = field(default_factory=dict)  # supporting evidence


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
    regime_strength: float = 0.0     # 0.0 - 1.0


class StrategyEngine:
    """
    Detects market regime and recommends the optimal strategy.

    Strategies:
    - Trend Following: ride established trends with EMAs + ADX
    - Mean Reversion: fade extremes at key levels
    - Breakout: trade level breaks with momentum
    """

    def detect_strategy(self, indicators: dict, levels: dict,
                        patterns: list = None, uncertainty: Optional[dict] = None,
                        macro_data: Optional[dict] = None) -> StrategySignal:
        """
        Analyze market conditions and recommend a strategy.

        Args:
            indicators: Technical indicator data (RSI, MACD, EMA, ADX, BB, ATR)
            levels: {"current_price", "support", "resistance"}
            patterns: Detected chart patterns

        Returns:
            StrategySignal with recommended action
        """
        regime_info = self._detect_regime(indicators)
        patterns = patterns or []

        if regime_info.regime == "trending":
            sig = self._trend_following(indicators, levels, patterns)
        elif regime_info.regime == "breakout":
            sig = self._breakout_strategy(indicators, levels, patterns)
        else:
            sig = self._mean_reversion(indicators, levels, patterns)

        # Attach regime metadata to signal
        sig.regime_strength = regime_info.strength
        if regime_info.strength < 0.4:
            sig.confidence *= 0.85  # Lower confidence in ambiguous regimes

        if uncertainty:
            sig = self._apply_uncertainty(sig, uncertainty, macro_data or {})

        return sig

    def _apply_uncertainty(self, sig: StrategySignal, uncertainty: dict, macro_data: dict) -> StrategySignal:
        confidence_adjustment = uncertainty.get("confidence_adjustment", 1.0)
        try:
            confidence_adjustment = float(confidence_adjustment)
        except (TypeError, ValueError):
            confidence_adjustment = 1.0

        sig.confidence = min(95, max(0, sig.confidence * confidence_adjustment))

        if uncertainty.get("high_uncertainty"):
            if not self._macro_confirmation(sig.direction, macro_data):
                return StrategySignal(
                    strategy="uncertain",
                    direction="WAIT",
                    confidence=0,
                    entry_rules=[],
                    exit_rules=[],
                    reasoning="High uncertainty without macro confirmation",
                    regime=sig.regime or "ranging",
                )

        return sig

    @staticmethod
    def _macro_confirmation(direction: str, macro_data: dict) -> bool:
        if direction not in ("BUY", "SELL"):
            return True
        differential = macro_data.get("differential", {}) if macro_data else {}
        bias = differential.get("bias") or differential.get("interpretation")
        if not bias:
            return False
        bias_text = str(bias).lower()
        if direction == "BUY" and ("eur stronger" in bias_text or "usd weaker" in bias_text):
            return True
        if direction == "SELL" and ("usd stronger" in bias_text or "eur weaker" in bias_text):
            return True
        return False

    def _detect_regime(self, indicators: dict) -> RegimeInfo:
        """
        Determine market regime using RegimeAdaptiveEngine as the single source of truth.
        """
        if not hasattr(self, '_regime_engine'):
            from .regime_adaptive import RegimeAdaptiveEngine
            self._regime_engine = RegimeAdaptiveEngine()
            
        # Map StrategyEngine indicators to the format expected by RegimeAdaptiveEngine
        bb = indicators.get("bollinger", {})
        mapped_inds = {
            "ADX": {"value": indicators.get("adx", 20)},
            "ATR": {"value": indicators.get("atr", 0), "average": indicators.get("atr_avg", 0)},
            "BB": {
                "upper": bb.get("upper", 0),
                "lower": bb.get("lower", 0),
                "current_price": bb.get("current_price", 0),
            }
        }
        
        # Calculate bandwidth if possible
        if mapped_inds["BB"]["upper"] and mapped_inds["BB"]["lower"] and mapped_inds["BB"]["current_price"]:
            width = (mapped_inds["BB"]["upper"] - mapped_inds["BB"]["lower"]) / mapped_inds["BB"]["current_price"] * 100
            mapped_inds["BB"]["bandwidth"] = width
            
        regime_name = self._regime_engine.detect_regime(mapped_inds)
        
        # Determine direction
        overall_bias = indicators.get("overall_bias", "neutral")
        ema_20 = indicators.get("ema_20")
        ema_50 = indicators.get("ema_50")
        
        if overall_bias == "bullish" or (ema_20 and ema_50 and ema_20 > ema_50):
            direction = "bullish"
        elif overall_bias == "bearish" or (ema_20 and ema_50 and ema_20 < ema_50):
            direction = "bearish"
        else:
            direction = "neutral"
            
        # Proxy strength from ADX (0-50 normalized to 0.1-1.0)
        adx = indicators.get("adx", 20)
        strength = min(1.0, max(0.1, adx / 50.0))
        
        logger.debug(f"Regime detection via RegimeAdaptiveEngine: {regime_name} (strength={strength:.2f})")
        
        return RegimeInfo(
            regime=regime_name,
            strength=strength,
            direction=direction,
            details={"source": "RegimeAdaptiveEngine"}
        )

    # ─── Trend Following ─────────────────────────────────────

    def _trend_following(self, indicators: dict, levels: dict,
                         patterns: list) -> StrategySignal:
        """
        Trend Following strategy — ride the trend with Market Structure & Momentum.

        Entry: Break of Structure (BOS) / Moving Averages alignment + Volume + ADX.
        Exit: CHoCH (Change of Character) or trailing stop.
        """
        bias = indicators.get("overall_bias", "neutral")
        adx = indicators.get("adx", 0)
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", {})

        confidence = 40.0
        entry_rules = []
        exit_rules = []
        direction = "WAIT"

        # Determine direction using Market Structure / EMAs
        if bias == "bullish":
            direction = "BUY"
            entry_rules.append("Market Structure: Bullish (BOS detected / Price > EMA 50)")
            confidence += 15
        elif bias == "bearish":
            direction = "SELL"
            entry_rules.append("Market Structure: Bearish (BOS detected / Price < EMA 50)")
            confidence += 15

        # Volume/Volatility Expansion Confirmation (ATR proxy instead of pseudo-volume)
        atr_data = indicators.get("atr", {})
        current_atr = atr_data.get("current", 0)
        avg_atr = atr_data.get("avg_14", 1)  # Using 14-period avg as baseline
        
        atr_expansion = False
        if current_atr and avg_atr and avg_atr > 0:
            if current_atr / avg_atr > 1.25:
                atr_expansion = True
                entry_rules.append("ATR Expansion: High momentum supports trend")
                confidence += 10
            elif current_atr / avg_atr < 0.75:
                entry_rules.append("ATR Compression: Low volatility, risk of fake-out")
                confidence -= 5

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
            "Change of Character (CHoCH): Price breaks swing point against direction",
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
        if rsi < 30:
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
        elif rsi > 70:
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

                # Momentum & Volatility confirmation
                hist = macd.get("histogram_latest")
                atr_data = indicators.get("atr", {})
                current_atr = atr_data.get("current", 0)
                avg_atr = atr_data.get("avg_14", 1)
                
                if hist and hist > 0:
                    entry_rules.append("MACD momentum confirms breakout")
                    confidence += 10
                
                if current_atr and avg_atr and avg_atr > 0 and current_atr / avg_atr > 1.25:
                    entry_rules.append("ATR Expansion validates breakout momentum")
                    confidence += 15

                if rsi > 50:
                    entry_rules.append(f"RSI bullish ({rsi:.0f})")
                    confidence += 5

                tick_vol = indicators.get("tick_volume_5m", 0)
                if tick_vol > 60:
                    entry_rules.append(f"Strong tick momentum validates breakout ({tick_vol} ticks/5m)")
                    confidence += 15

        # Breakdown below support
        if direction == "WAIT" and support and current_price:
            nearest_s = support[0]
            if current_price < nearest_s:
                direction = "SELL"
                entry_rules.append(f"Price broke below support {nearest_s}")
                confidence += 20

                hist = macd.get("histogram_latest")
                atr_data = indicators.get("atr", {})
                current_atr = atr_data.get("current", 0)
                avg_atr = atr_data.get("avg_14", 1)
                
                if hist and hist < 0:
                    entry_rules.append("MACD momentum confirms breakdown")
                    confidence += 10
                
                if current_atr and avg_atr and avg_atr > 0 and current_atr / avg_atr > 1.25:
                    entry_rules.append("ATR Expansion validates breakdown momentum")
                    confidence += 15

                if rsi < 50:
                    entry_rules.append(f"RSI bearish ({rsi:.0f})")
                    confidence += 5
                    
                tick_vol = indicators.get("tick_volume_5m", 0)
                if tick_vol > 60:
                    entry_rules.append(f"Strong tick momentum validates breakdown ({tick_vol} ticks/5m)")
                    confidence += 15

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
