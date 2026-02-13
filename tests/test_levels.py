"""
Tests for euroscope.analysis.levels module.
"""

import numpy as np
import pandas as pd
import pytest

from euroscope.analysis.levels import LevelAnalyzer


class TestSupportResistance:
    """Test support/resistance level detection."""

    def test_returns_dict_with_keys(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.find_support_resistance(sample_ohlcv)
        assert "support" in result
        assert "resistance" in result

    def test_levels_are_sorted(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.find_support_resistance(sample_ohlcv)
        # Support descending (nearest first)
        if len(result["support"]) >= 2:
            assert result["support"][0] >= result["support"][1]
        # Resistance ascending (nearest first)
        if len(result["resistance"]) >= 2:
            assert result["resistance"][0] <= result["resistance"][1]

    def test_support_below_price(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.find_support_resistance(sample_ohlcv)
        current = float(sample_ohlcv["Close"].iloc[-1])
        for s in result["support"]:
            assert s < current

    def test_resistance_above_price(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.find_support_resistance(sample_ohlcv)
        current = float(sample_ohlcv["Close"].iloc[-1])
        for r in result["resistance"]:
            assert r > current

    def test_empty_dataframe(self):
        analyzer = LevelAnalyzer()
        result = analyzer.find_support_resistance(pd.DataFrame())
        assert result == {"support": [], "resistance": []}

    def test_num_levels_parameter(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.find_support_resistance(sample_ohlcv, num_levels=3)
        assert len(result["support"]) <= 3
        assert len(result["resistance"]) <= 3


class TestFibonacci:
    """Test Fibonacci retracement calculation."""

    def test_returns_levels(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.fibonacci_retracement(sample_ohlcv)
        assert "levels" in result or "error" in result

    def test_fib_levels_count(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.fibonacci_retracement(sample_ohlcv)
        if "levels" in result:
            assert len(result["levels"]) >= 5  # Standard Fibonacci ratios

    def test_fib_direction(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.fibonacci_retracement(sample_ohlcv)
        if "direction" in result:
            assert result["direction"] in ("uptrend", "downtrend")

    def test_fib_range_pips(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.fibonacci_retracement(sample_ohlcv)
        if "range_pips" in result:
            assert result["range_pips"] > 0


class TestPivotPoints:
    """Test classic pivot point calculation."""

    def test_returns_all_levels(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.pivot_points(sample_ohlcv)
        for key in ["R3", "R2", "R1", "Pivot", "S1", "S2", "S3"]:
            assert key in result

    def test_pivot_ordering(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        result = analyzer.pivot_points(sample_ohlcv)
        if "Pivot" in result:
            assert result["R3"] > result["R2"] > result["R1"] > result["Pivot"]
            assert result["Pivot"] > result["S1"] > result["S2"] > result["S3"]

    def test_insufficient_data(self):
        analyzer = LevelAnalyzer()
        df = pd.DataFrame({"Open": [1.0], "High": [1.1], "Low": [0.9], "Close": [1.05]},
                          index=pd.date_range("2024-01-01", periods=1, freq="h"))
        result = analyzer.pivot_points(df)
        assert "error" in result


class TestLevelClustering:
    """Test the level clustering static method."""

    def test_clusters_nearby_levels(self):
        levels = [1.0800, 1.0802, 1.0801, 1.0900, 1.0901]
        result = LevelAnalyzer._cluster_levels(levels, tolerance=0.001)
        # Should cluster into 2 groups
        assert len(result) == 2

    def test_empty_levels(self):
        result = LevelAnalyzer._cluster_levels([], tolerance=0.001)
        assert result == []

    def test_single_level(self):
        result = LevelAnalyzer._cluster_levels([1.0850], tolerance=0.001)
        assert len(result) == 1


class TestFormatLevels:
    """Test level formatting for Telegram."""

    def test_format_basic(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        sr = analyzer.find_support_resistance(sample_ohlcv)
        formatted = analyzer.format_levels(sr)
        assert isinstance(formatted, str)
        assert "EUR/USD" in formatted

    def test_format_with_fib(self, sample_ohlcv):
        analyzer = LevelAnalyzer()
        sr = analyzer.find_support_resistance(sample_ohlcv)
        fib = analyzer.fibonacci_retracement(sample_ohlcv)
        formatted = analyzer.format_levels(sr, fib_data=fib)
        assert isinstance(formatted, str)
        if "levels" in fib:
            assert "Fibonacci" in formatted
