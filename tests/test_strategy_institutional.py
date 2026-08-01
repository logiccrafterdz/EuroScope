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
