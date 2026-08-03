"""
Tests for institutional-grade strategy upgrades:
ATR data flow, volatile defensive mode, mean-reversion statistical
entries + trend filter, trend no-chase/pullback, breakout ATR expansion,
and session-aware gating.
"""

import pandas as pd
import pytest
import numpy as np

from euroscope.trading.strategy_engine import StrategyEngine
from euroscope.analysis.technical import TechnicalAnalyzer, zscore
from euroscope.skills.base import SkillContext
from euroscope.skills.trading_strategy.skill import TradingStrategySkill


@pytest.fixture
def engine():
    return StrategyEngine()


# ── ATR data-flow fixes ────────────────────────────────────

class TestAtrDataFlow:

    def test_detect_regime_sees_atr_dict_value(self, engine):
        """The ATR dict from TechnicalAnalyzer must reach the regime engine."""
        indicators = {"adx": 15, "atr": {"value": 0.003, "sma": 0.0015}}
        result = engine._detect_regime(indicators)
        assert result.regime == "volatile"  # vol ratio 2.0 > 1.8

    def test_trend_following_atr_expansion_fires(self, engine):
        indicators = {
            "adx": 35, "rsi": 55, "overall_bias": "bullish",
            "macd": {"histogram_latest": 0.002},
            "atr": {"value": 0.003, "sma": 0.002},  # ratio 1.5 -> expansion
            "zscore": 0.5,
        }
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "trend_following"
        assert any("ATR Expansion" in r for r in sig.entry_rules)

    def test_breakout_atr_expansion_fires(self, engine):
        indicators = {
            "adx": 18, "rsi": 60,
            "macd": {"histogram_latest": 0.001},
            "atr": {"value": 0.003, "sma": 0.002},  # ratio 1.5
            "tick_volume_5m": 80,
            "bollinger": {"upper": 1.0910, "lower": 1.0905, "current_price": 1.1010},
        }
        levels = {"current_price": 1.1010, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "breakout"
        assert sig.direction == "BUY"
        assert any("ATR Expansion" in r for r in sig.entry_rules)


# ── Volatile regime → defensive ────────────────────────────

class TestVolatileDefensive:

    def test_volatile_stands_aside(self, engine):
        indicators = {"adx": 15, "rsi": 50, "atr": {"value": 0.003, "sma": 0.0015}}
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "volatile_defensive"
        assert sig.direction == "WAIT"

    def test_volatile_with_strong_trend_rides_reduced(self, engine):
        indicators = {
            "adx": 35, "rsi": 55, "overall_bias": "bullish",
            "macd": {"histogram_latest": 0.002},
            "atr": {"value": 0.003, "sma": 0.0015},
            "zscore": 0.5,
        }
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.direction == "BUY"
        assert sig.confidence <= 60
        assert "reduced confidence" in sig.reasoning


# ── Mean Reversion (institutional) ─────────────────────────

class TestMeanReversionInstitutional:

    def test_deep_zscore_buy_without_rsi_extreme(self, engine):
        indicators = {"adx": 15, "rsi": 50, "zscore": -2.3, "overall_bias": "neutral"}
        levels = {"current_price": 1.0905, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "mean_reversion"
        assert sig.direction == "BUY"
        assert sig.confidence >= 60
        assert any("z-score" in r for r in sig.entry_rules)

    def test_double_confirmation_boosts_confidence(self, engine):
        single = {"adx": 15, "rsi": 28, "zscore": -1.2, "overall_bias": "neutral"}
        double = {"adx": 15, "rsi": 28, "zscore": -2.4, "overall_bias": "neutral"}
        levels = {"current_price": 1.0905, "support": [1.0900], "resistance": [1.1000]}
        sig_single = engine.detect_strategy(single, levels)
        sig_double = engine.detect_strategy(double, levels)
        assert sig_single.direction == "BUY"
        assert sig_double.direction == "BUY"
        assert sig_double.confidence > sig_single.confidence
        assert any("Double confirmation" in r for r in sig_double.entry_rules)

    def test_trend_filter_suppresses_fading(self, engine):
        """Never fade a strong trend — ADX >= 25 forces WAIT even at RSI extreme."""
        sig = engine._mean_reversion({"adx": 26, "rsi": 28, "zscore": -2.0}, {
            "current_price": 1.0905, "support": [1.0900], "resistance": [1.1000]
        }, [])
        assert sig.direction == "WAIT"
        assert any("Trend filter" in r for r in sig.entry_rules)

    def test_time_stop_in_exit_rules(self, engine):
        sig = engine._mean_reversion({"adx": 15, "rsi": 28, "zscore": -2.0}, {
            "current_price": 1.0905, "support": [1.0900], "resistance": [1.1000]
        }, [])
        assert any("Time stop" in r for r in sig.exit_rules)

    def test_exit_targets_the_mean(self, engine):
        sig = engine._mean_reversion({"adx": 15, "rsi": 72, "zscore": 2.0}, {
            "current_price": 1.0995, "support": [1.0900], "resistance": [1.1000]
        }, [])
        assert sig.direction == "SELL"
        assert any("middle Bollinger" in r for r in sig.exit_rules)


# ── Trend following: no-chase ──────────────────────────────

class TestTrendNoChase:

    def test_overextended_penalized(self, engine):
        base = {
            "adx": 35, "rsi": 60, "overall_bias": "bullish",
            "macd": {"histogram_latest": 0.002},
            "atr": {"value": 0.003, "sma": 0.002},
        }
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        pullback = engine.detect_strategy({**base, "zscore": 0.5}, levels)
        extended = engine.detect_strategy({**base, "zscore": 2.6}, levels)
        assert pullback.direction == "BUY"
        assert extended.direction == "BUY"
        assert extended.confidence < pullback.confidence
        assert any("overextended" in r for r in extended.entry_rules)


# ── Session gating ─────────────────────────────────────────

class TestSessionGating:

    def test_no_trade_session_blocks(self, engine):
        indicators = {"adx": 35, "rsi": 55, "overall_bias": "bullish"}
        levels = {"current_price": 1.0950}
        sig = engine.detect_strategy(indicators, levels, session="weekend")
        assert sig.direction == "WAIT"
        assert sig.confidence == 0

    def test_asian_session_penalizes_breakout(self, engine):
        indicators = {
            "adx": 18, "rsi": 60,
            "macd": {"histogram_latest": 0.001},
            "atr": {"value": 0.003, "sma": 0.002},
            "tick_volume_5m": 80,
            "bollinger": {"upper": 1.0910, "lower": 1.0905, "current_price": 1.1010},
        }
        levels = {"current_price": 1.1010, "support": [1.0900], "resistance": [1.1000]}
        asian = engine.detect_strategy(indicators, levels, session="asian")
        london = engine.detect_strategy(indicators, levels, session="london")
        assert asian.direction == "BUY"
        assert london.direction == "BUY"
        assert asian.confidence < london.confidence
        assert any("Breakout penalized" in r for r in asian.reasoning.split(" | "))

    def test_overlap_boost(self, engine):
        indicators = {
            "adx": 28, "rsi": 55, "overall_bias": "bullish",
            "zscore": 0.5,  # deliberately below the 95 cap so the boost is visible
        }
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        overlap = engine.detect_strategy(indicators, levels, session="overlap")
        default = engine.detect_strategy(indicators, levels)
        assert overlap.direction == "BUY"
        assert default.confidence < 95
        assert overlap.confidence > default.confidence


# ── TechnicalAnalyzer additions ────────────────────────────

class TestZScoreExposure:

    def test_analyze_includes_zscore_and_bandwidth(self):
        rng = np.random.default_rng(7)
        close = 1.09 + np.cumsum(rng.normal(0, 0.0006, 300))
        close[-5:] = close[-5:] - 0.006  # recent pullback for negative z-score
        df = pd.DataFrame({
            "Open": close * 0.9999,
            "High": close + 0.001,
            "Low": close - 0.001,
            "Close": close,
            "Volume": 100,
        })
        result = TechnicalAnalyzer().analyze(df)
        ind = result["indicators"]
        assert "ZScore" in ind
        assert ind["ZScore"]["value"] is not None
        assert ind["ZScore"]["period"] == 20
        assert "bandwidth" in ind["Bollinger"]

    def test_zscore_function_output(self):
        close = pd.Series([1.0] * 20 + [1.01])
        z = zscore(close)
        assert not z.isna().all()
        assert z.iloc[-1] > 0


# ── Production contract: TechnicalAnalyzer output shape ─────
# The live pipeline feeds TechnicalAnalyzer output (capitalized bias,
# "histogram" key, Bollinger without current_price) into StrategyEngine.
# The engine must be tolerant of that contract — otherwise the bot can
# never produce BUY/SELL in production even though backtests pass.

class TestProductionContract:

    def test_capitalized_bias_bullish_produces_buy(self, engine):
        indicators = {
            "adx": 35, "rsi": 60, "overall_bias": "Bullish",
            "macd": {"histogram": 0.0004},
            "atr": {"value": 0.0012, "sma": 0.0010},
            "zscore": 0.4,
            "bollinger": {"upper": 1.0965, "middle": 1.0945, "lower": 1.0925},
        }
        levels = {"current_price": 1.0950, "support": [1.0930], "resistance": [1.0970]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "trend_following"
        assert sig.direction == "BUY"

    def test_capitalized_bias_bearish_produces_sell(self, engine):
        indicators = {
            "adx": 35, "rsi": 40, "overall_bias": "Bearish",
            "macd": {"histogram": -0.0004},
            "atr": {"value": 0.0012, "sma": 0.0010},
            "zscore": -0.4,
            "bollinger": {"upper": 1.0965, "middle": 1.0945, "lower": 1.0925},
        }
        levels = {"current_price": 1.0950, "support": [1.0930], "resistance": [1.0970]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.strategy == "trend_following"
        assert sig.direction == "SELL"

    def test_macd_histogram_key_confirms(self, engine):
        """TechnicalAnalyzer emits 'histogram' (not 'histogram_latest'); engine must read it."""
        indicators = {
            "adx": 35, "rsi": 55, "overall_bias": "bullish",
            "macd": {"histogram": 0.002},
            "atr": {"value": 0.003, "sma": 0.002},
            "zscore": 0.5,
        }
        levels = {"current_price": 1.0950, "support": [1.0900], "resistance": [1.1000]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.direction == "BUY"
        assert any("MACD histogram confirms" in r for r in sig.entry_rules)

    def test_bb_bandwidth_from_price_fallback_enables_breakout(self, engine):
        """Bollinger without current_price must still allow squeeze detection via indicators['price']."""
        indicators = {
            "adx": 15, "rsi": 80, "overall_bias": "neutral",
            "price": 1.0908,
            "bollinger": {"upper": 1.0910, "lower": 1.0905},
        }
        levels = {"current_price": 1.0908, "support": [1.0890], "resistance": [1.0920]}
        sig = engine.detect_strategy(indicators, levels)
        assert sig.regime == "breakout"

    @pytest.mark.asyncio
    async def test_skill_accepts_technical_analyzer_format_buy(self):
        """End-to-end: TechnicalAnalyzer-shaped indicators through TradingStrategySkill must signal BUY."""
        ctx = SkillContext()
        ctx.analysis["indicators"] = {
            "price": 1.0950,
            "overall_bias": "Bullish",
            "indicators": {
                "RSI": {"value": 60.0, "signal": "x"},
                "MACD": {"macd": 0.0005, "signal": 0.0001, "histogram": 0.0004, "signal_text": "Bullish"},
                "Bollinger": {"upper": 1.0965, "middle": 1.0945, "lower": 1.0925,
                              "bandwidth": 0.0027, "position": "x"},
                "ZScore": {"value": 0.5, "period": 20},
                "EMA": {"ema20": 1.0948, "ema50": 1.0940, "ema200": 1.0910, "trend": "x"},
                "ATR": {"value": 0.0012, "sma": 0.0010, "pips": 12.0},
                "ADX": {"value": 35.0, "strength": "x"},
                "Stochastic": {"k": 60.0, "d": 55.0, "signal": "x"},
            },
        }
        ctx.analysis["levels"] = {"current_price": 1.0950, "support": [1.0930], "resistance": [1.0970]}
        ctx.analysis["patterns"] = []
        ctx.metadata["session_regime"] = "london"

        skill = TradingStrategySkill()
        skill.set_agent(object())
        result = await skill._detect(ctx)
        assert result.success
        assert result.data["direction"] == "BUY"
        assert result.data["strategy"] == "trend_following"

    @pytest.mark.asyncio
    async def test_skill_accepts_technical_analyzer_format_sell(self):
        ctx = SkillContext()
        ctx.analysis["indicators"] = {
            "price": 1.0950,
            "overall_bias": "Bearish",
            "indicators": {
                "RSI": {"value": 40.0, "signal": "x"},
                "MACD": {"macd": 0.0001, "signal": 0.0005, "histogram": -0.0004, "signal_text": "Bearish"},
                "Bollinger": {"upper": 1.0965, "middle": 1.0945, "lower": 1.0925,
                              "bandwidth": 0.0027, "position": "x"},
                "ZScore": {"value": -0.5, "period": 20},
                "EMA": {"ema20": 1.0948, "ema50": 1.0940, "ema200": 1.0910, "trend": "x"},
                "ATR": {"value": 0.0012, "sma": 0.0010, "pips": 12.0},
                "ADX": {"value": 35.0, "strength": "x"},
                "Stochastic": {"k": 40.0, "d": 45.0, "signal": "x"},
            },
        }
        ctx.analysis["levels"] = {"current_price": 1.0950, "support": [1.0930], "resistance": [1.0970]}
        ctx.analysis["patterns"] = []
        ctx.metadata["session_regime"] = "london"

        skill = TradingStrategySkill()
        skill.set_agent(object())
        result = await skill._detect(ctx)
        assert result.success
        assert result.data["direction"] == "SELL"
        assert result.data["strategy"] == "trend_following"
