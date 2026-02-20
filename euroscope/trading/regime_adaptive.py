"""
Regime-Adaptive Parameters — Auto-adjusts trading parameters
based on the current market regime.

When the market is TRENDING, parameters favor momentum:
  - Wider stops, higher R:R, momentum indicators weighted more
When RANGING, parameters favor mean-reversion:
  - Tighter stops, lower R:R, oscillators weighted more
When VOLATILE, parameters get defensive:
  - Wider stops, smaller position sizes, lower confidence thresholds
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("euroscope.trading.regime_adaptive")


# ── Regime Profiles ─────────────────────────────────────────

@dataclass
class RegimeProfile:
    """Trading parameters tuned for a specific market regime."""
    name: str
    stop_loss_multiplier: float  # ATR multiplier for SL
    take_profit_multiplier: float  # ATR multiplier for TP
    risk_per_trade: float  # % of account per trade
    confidence_threshold: float  # Min confidence to enter (0-100)
    indicator_weights: dict = field(default_factory=dict)
    description: str = ""


REGIME_PROFILES = {
    "trending": RegimeProfile(
        name="trending",
        stop_loss_multiplier=2.0,
        take_profit_multiplier=4.0,
        risk_per_trade=1.5,
        confidence_threshold=55,
        indicator_weights={
            "EMA": 1.3,
            "MACD": 1.2,
            "ADX": 1.4,
            "RSI": 0.7,
            "BB": 0.5,
        },
        description="Momentum-focused: wider targets, trend indicators weighted",
    ),
    "ranging": RegimeProfile(
        name="ranging",
        stop_loss_multiplier=1.2,
        take_profit_multiplier=1.8,
        risk_per_trade=1.0,
        confidence_threshold=65,
        indicator_weights={
            "EMA": 0.6,
            "MACD": 0.8,
            "ADX": 0.5,
            "RSI": 1.4,
            "BB": 1.3,
        },
        description="Mean-reversion: tighter targets, oscillators weighted",
    ),
    "breakout": RegimeProfile(
        name="breakout",
        stop_loss_multiplier=1.5,
        take_profit_multiplier=3.0,
        risk_per_trade=1.2,
        confidence_threshold=60,
        indicator_weights={
            "EMA": 1.0,
            "MACD": 1.1,
            "ADX": 1.3,
            "RSI": 0.9,
            "BB": 1.2,
        },
        description="Breakout-focused: moderate targets, volume/momentum weighted",
    ),
    "volatile": RegimeProfile(
        name="volatile",
        stop_loss_multiplier=2.5,
        take_profit_multiplier=3.5,
        risk_per_trade=0.5,
        confidence_threshold=75,
        indicator_weights={
            "EMA": 0.8,
            "MACD": 0.9,
            "ADX": 1.0,
            "RSI": 1.0,
            "BB": 1.0,
        },
        description="Defensive: wider stops, smaller size, higher entry bar",
    ),
}


class RegimeAdaptiveEngine:
    """
    Detects the current market regime and provides regime-tuned
    parameter sets for the strategy engine and risk manager.
    """

    def __init__(self):
        self._current_regime: str = "ranging"
        self._regime_history: list[dict] = []
        self._transition_count: int = 0

    # ── Regime Detection ───────────────────────────────────────

    def detect_regime(self, indicators: dict) -> str:
        """
        Detect market regime from technical indicators.

        Args:
            indicators: Dict with ADX, BB, ATR, EMA data

        Returns:
            "trending", "ranging", "breakout", or "volatile"
        """
        adx = self._safe_value(indicators.get("ADX", {}), "value", 20)
        atr = self._safe_value(indicators.get("ATR", {}), "value", 0)
        bb = indicators.get("BB", {})
        bb_width = self._safe_value(bb, "bandwidth", 0)

        # Volatility spike detection
        avg_atr = self._safe_value(indicators.get("ATR", {}), "average", atr)
        volatility_ratio = atr / avg_atr if avg_atr > 0 else 1.0

        if volatility_ratio > 1.8:
            regime = "volatile"
        elif adx > 25:
            regime = "trending"
        elif bb_width > 0.02 and adx > 20:
            regime = "breakout"
        else:
            regime = "ranging"

        # Track transitions
        if regime != self._current_regime:
            self._transition_count += 1
            self._regime_history.append({
                "from": self._current_regime,
                "to": regime,
                "adx": adx,
                "volatility_ratio": round(volatility_ratio, 2),
            })
            logger.info(
                f"🔄 Regime shift: {self._current_regime} → {regime} "
                f"(ADX={adx:.1f}, vol_ratio={volatility_ratio:.2f})"
            )
            self._current_regime = regime

        return regime

    # ── Parameter Access ───────────────────────────────────────

    def get_profile(self, regime: str = None) -> RegimeProfile:
        """Get the parameter profile for a regime (defaults to current)."""
        r = regime or self._current_regime
        return REGIME_PROFILES.get(r, REGIME_PROFILES["ranging"])

    def get_stop_multiplier(self, regime: str = None) -> float:
        """Get ATR stop loss multiplier for the current/given regime."""
        return self.get_profile(regime).stop_loss_multiplier

    def get_tp_multiplier(self, regime: str = None) -> float:
        """Get ATR take profit multiplier for the current/given regime."""
        return self.get_profile(regime).take_profit_multiplier

    def get_risk_per_trade(self, regime: str = None) -> float:
        """Get risk % per trade for the current/given regime."""
        return self.get_profile(regime).risk_per_trade

    def get_confidence_threshold(self, regime: str = None) -> float:
        """Get minimum confidence threshold for the current/given regime."""
        return self.get_profile(regime).confidence_threshold

    def get_indicator_weight(self, indicator: str, regime: str = None) -> float:
        """Get weight for a specific indicator in the current/given regime."""
        profile = self.get_profile(regime)
        return profile.indicator_weights.get(indicator, 1.0)

    @property
    def current_regime(self) -> str:
        return self._current_regime

    @property
    def transition_count(self) -> int:
        return self._transition_count

    # ── Formatting ─────────────────────────────────────────────

    def format_regime(self) -> str:
        """Format current regime info for Telegram display."""
        profile = self.get_profile()
        icons = {
            "trending": "📈", "ranging": "↔️",
            "breakout": "💥", "volatile": "⚡",
        }
        icon = icons.get(self._current_regime, "❓")

        lines = [
            f"{icon} *Market Regime: {self._current_regime.upper()}*",
            f"_{profile.description}_",
            "",
            f"SL Multiplier: `{profile.stop_loss_multiplier}x ATR`",
            f"TP Multiplier: `{profile.take_profit_multiplier}x ATR`",
            f"Risk/Trade: `{profile.risk_per_trade}%`",
            f"Min Confidence: `{profile.confidence_threshold}%`",
            f"Transitions: `{self._transition_count}`",
        ]
        return "\n".join(lines)

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _safe_value(data: dict, key: str, default: float) -> float:
        """Safely extract a numeric value from indicator data."""
        val = data.get(key, default)
        if isinstance(val, (int, float)):
            return float(val)
        return default
