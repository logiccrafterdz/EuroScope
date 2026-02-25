"""
Tests for strategy engine: regime detection and strategy recommendation.
"""

import asyncio
import time
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from euroscope.trading.strategy_engine import StrategyEngine, StrategySignal
from euroscope.skills.base import SkillContext
from euroscope.skills.deviation_monitor import DeviationMonitorSkill
from euroscope.skills.trading_strategy.skill import TradingStrategySkill


@pytest.fixture
def engine():
    return StrategyEngine()


# ── Regime Detection ──────────────────────────────────────

class TestRegimeDetection:

    def test_trending_high_adx(self, engine):
        indicators = {"adx": 30, "rsi": 55, "overall_bias": "bullish"}
        assert engine._detect_regime(indicators) == "trending"

    def test_ranging_low_adx(self, engine):
        indicators = {"adx": 15, "rsi": 50, "overall_bias": "neutral"}
        assert engine._detect_regime(indicators) == "ranging"

    def test_breakout_bb_squeeze(self, engine):
        indicators = {
            "adx": 18, "rsi": 50,
            "bollinger": {"upper": 1.0910, "lower": 1.0905, "current_price": 1.0908}
        }
        assert engine._detect_regime(indicators) == "breakout"

    def test_breakout_extreme_rsi(self, engine):
        indicators = {"adx": 18, "rsi": 80}
        assert engine._detect_regime(indicators) == "breakout"

    def test_no_indicators(self, engine):
        assert engine._detect_regime({}) == "ranging"


# ── Trend Following ──────────────────────────────────────

class TestTrendFollowing:

    def test_bullish_trend(self, engine):
        indicators = {
            "adx": 35, "rsi": 55, "overall_bias": "bullish",
            "macd": {"histogram_latest": 0.002},
        }
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "trend_following"
        assert sig.direction == "BUY"
        assert sig.confidence > 50

    def test_bearish_trend(self, engine):
        indicators = {
            "adx": 35, "rsi": 40, "overall_bias": "bearish",
            "macd": {"histogram_latest": -0.003},
        }
        levels = {"current_price": 1.0850, "support": [1.0800], "resistance": [1.0900]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "trend_following"
        assert sig.direction == "SELL"

    def test_has_entry_exit_rules(self, engine):
        indicators = {"adx": 30, "rsi": 55, "overall_bias": "bullish"}
        levels = {"current_price": 1.0950}
        sig = engine.detect_strategy(indicators, levels)
        assert len(sig.entry_rules) > 0
        assert len(sig.exit_rules) > 0

    def test_neutral_bias_waits(self, engine):
        indicators = {"adx": 30, "rsi": 50, "overall_bias": "neutral"}
        levels = {"current_price": 1.0900}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.direction == "WAIT"


# ── Mean Reversion ────────────────────────────────────────

class TestMeanReversion:

    def test_oversold_buy(self, engine):
        indicators = {"adx": 15, "rsi": 28, "overall_bias": "neutral"}
        levels = {"current_price": 1.0905, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "mean_reversion"
        assert sig.direction == "BUY"

    def test_overbought_sell(self, engine):
        indicators = {"adx": 15, "rsi": 72, "overall_bias": "neutral"}
        levels = {"current_price": 1.0995, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "mean_reversion"
        assert sig.direction == "SELL"

    def test_neutral_rsi_waits(self, engine):
        indicators = {"adx": 15, "rsi": 50}
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.direction == "WAIT"


# ── Breakout ─────────────────────────────────────────────

class TestBreakout:

    def test_breakout_above_resistance(self, engine):
        indicators = {
            "adx": 18, "rsi": 60,
            "bollinger": {"upper": 1.0910, "lower": 1.0905, "current_price": 1.0912},
            "macd": {"histogram_latest": 0.001},
        }
        levels = {"current_price": 1.1010, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "breakout"
        assert sig.direction == "BUY"

    def test_breakdown_below_support(self, engine):
        indicators = {
            "adx": 18, "rsi": 35,
            "bollinger": {"upper": 1.0910, "lower": 1.0905, "current_price": 1.0903},
            "macd": {"histogram_latest": -0.002},
        }
        levels = {"current_price": 1.0890, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "breakout"
        assert sig.direction == "SELL"


# ── Formatting ───────────────────────────────────────────

class TestFormatting:

    def test_format_strategy(self, engine):
        sig = StrategySignal(
            strategy="trend_following", direction="BUY",
            confidence=75, regime="trending",
            entry_rules=["EMA aligned"], exit_rules=["Trailing stop"],
        )
        formatted = engine.format_strategy(sig)
        assert "Trend Following" in formatted
        assert "BUY" in formatted

    def test_confidence_range(self, engine):
        indicators = {"adx": 35, "rsi": 55, "overall_bias": "bullish",
                       "macd": {"histogram_latest": 0.01}}
        levels = {"current_price": 1.0950}
        sig = engine.detect_strategy(indicators, levels, [
            {"name": "Double Bottom", "bias": "bullish"},
            {"name": "Hammer", "bias": "bullish"},
        ])
        assert 0 <= sig.confidence <= 95

    def test_high_uncertainty_blocks_without_macro(self, engine):
        indicators = {"adx": 35, "rsi": 55, "overall_bias": "bullish",
                      "macd": {"histogram_latest": 0.01}}
        levels = {"current_price": 1.0950}
        uncertainty = {"high_uncertainty": True, "confidence_adjustment": 0.8}
        sig = engine.detect_strategy(indicators, levels, uncertainty=uncertainty, macro_data={})
        assert sig.direction == "WAIT"

    def test_high_uncertainty_allows_with_macro(self, engine):
        indicators = {"adx": 35, "rsi": 55, "overall_bias": "bullish",
                      "macd": {"histogram_latest": 0.01}}
        levels = {"current_price": 1.0950}
        uncertainty = {"high_uncertainty": True, "confidence_adjustment": 0.8}
        macro_data = {"differential": {"bias": "EUR stronger"}}
        sig = engine.detect_strategy(indicators, levels, uncertainty=uncertainty, macro_data=macro_data)
        assert sig.direction == "BUY"


class TestTradingStrategyFallback:

    @pytest.mark.asyncio
    async def test_emergency_mode_triggers_fallback(self):
        """When emergency_mode is active, skill should use technical_fallback without calling LLM."""
        skill = TradingStrategySkill()
        skill.set_agent(object())

        skill._generate_llm_signal = AsyncMock(return_value=None)
        skill._llm_refine_strategy = AsyncMock(return_value=None)

        ctx = SkillContext()
        ctx.metadata["emergency_mode"] = True
        ctx.analysis["indicators"] = {
            "overall_bias": "bullish",
            "indicators": {
                "ADX": {"value": 30},
                "RSI": {"value": 60},
                "MACD": {"histogram": 0.01},
            },
        }
        ctx.analysis["levels"] = {"current_price": 1.0950}

        result = await skill._detect(ctx)

        assert result.success
        assert result.data.get("source") == "technical_fallback"
        assert skill._generate_llm_signal.await_count == 0

    @pytest.mark.asyncio
    async def test_emergency_mode_skips_llm(self):
        df = pd.DataFrame({
            "High": [1.1] * 20,
            "Low": [1.0] * 20,
            "Close": [1.05] * 20,
            "Volume": [100] * 19 + [1000],
        })

        class BufferSkill:
            def get_buffer(self):
                return {"candles": df, "timeframe": "M1"}

        ctx = SkillContext()
        ctx.metadata["session_regime"] = "asian"
        monitor = DeviationMonitorSkill(market_data_skill=BufferSkill(), global_context=ctx)
        await monitor._check_once()
        assert ctx.metadata.get("emergency_mode") is True

        skill = TradingStrategySkill()
        skill.set_agent(object())
        skill._generate_llm_signal = AsyncMock(return_value=None)
        skill._llm_refine_strategy = AsyncMock(return_value=None)

        ctx.analysis["indicators"] = {
            "overall_bias": "bullish",
            "indicators": {
                "ADX": {"value": 30},
                "RSI": {"value": 60},
                "MACD": {"histogram": 0.01},
            },
        }
        ctx.analysis["levels"] = {"current_price": 1.0950}

        result = await skill._detect(ctx)
        assert result.success
        assert result.data.get("source") == "technical_fallback"
        assert skill._generate_llm_signal.await_count == 0

    @pytest.mark.asyncio
    async def test_sideways_market_returns_neutral(self):
        skill = TradingStrategySkill()

        ctx = SkillContext()
        ctx.metadata["emergency_mode"] = True
        ctx.analysis["indicators"] = {
            "overall_bias": "neutral",
            "indicators": {
                "ADX": {"value": 15},
                "RSI": {"value": 50},
                "MACD": {"histogram": 0.0},
            },
        }
        ctx.analysis["levels"] = {"current_price": 1.0900}

        result = await skill._detect(ctx)
        assert result.success
        assert result.data.get("strategy") == "NEUTRAL"
        assert result.data.get("direction") == "WAIT"

