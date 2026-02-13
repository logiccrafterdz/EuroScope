"""
Tests for euroscope.analysis.patterns module.
"""

import numpy as np
import pandas as pd
import pytest

from euroscope.analysis.patterns import PatternDetector, find_swing_points


class TestSwingPoints:
    """Test swing point detection."""

    def test_finds_swing_highs(self, sample_ohlcv):
        highs, lows = find_swing_points(sample_ohlcv["Close"], window=5)
        assert isinstance(highs, list)
        assert len(highs) > 0
        # Each swing high should be a tuple (index, price)
        for idx, price in highs:
            assert isinstance(price, (float, np.floating))

    def test_finds_swing_lows(self, sample_ohlcv):
        highs, lows = find_swing_points(sample_ohlcv["Close"], window=5)
        assert isinstance(lows, list)
        assert len(lows) > 0

    def test_small_data_no_crash(self, small_ohlcv):
        highs, lows = find_swing_points(small_ohlcv["Close"], window=3)
        assert isinstance(highs, list)
        assert isinstance(lows, list)

    def test_window_parameter_affects_result(self, sample_ohlcv):
        highs_3, _ = find_swing_points(sample_ohlcv["Close"], window=3)
        highs_7, _ = find_swing_points(sample_ohlcv["Close"], window=7)
        # Larger window should find fewer or equal swing points
        assert len(highs_7) <= len(highs_3)


class TestPatternDetector:
    """Test pattern detection."""

    def test_detect_all_returns_list(self, sample_ohlcv):
        detector = PatternDetector()
        patterns = detector.detect_all(sample_ohlcv)
        assert isinstance(patterns, list)

    def test_pattern_dict_structure(self, sample_ohlcv):
        detector = PatternDetector()
        patterns = detector.detect_all(sample_ohlcv)
        for p in patterns:
            assert "pattern" in p
            assert "type" in p  # "bullish" or "bearish"
            assert p["type"] in ("bullish", "bearish", "neutral")

    def test_empty_dataframe(self):
        detector = PatternDetector()
        patterns = detector.detect_all(pd.DataFrame())
        assert patterns == []

    def test_insufficient_data(self, small_ohlcv):
        detector = PatternDetector()
        patterns = detector.detect_all(small_ohlcv)
        assert isinstance(patterns, list)

    def test_format_patterns_no_patterns(self):
        detector = PatternDetector()
        formatted = detector.format_patterns([])
        assert isinstance(formatted, str)

    def test_format_patterns_with_patterns(self, sample_ohlcv):
        detector = PatternDetector()
        patterns = detector.detect_all(sample_ohlcv)
        formatted = detector.format_patterns(patterns)
        assert isinstance(formatted, str)

    def test_tolerance_parameter(self):
        d1 = PatternDetector(tolerance=0.0005)
        d2 = PatternDetector(tolerance=0.002)
        assert d1.tolerance != d2.tolerance
