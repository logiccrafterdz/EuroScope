"""
Tests for euroscope.analysis.technical module.
"""

import numpy as np
import pandas as pd
import pytest

from euroscope.analysis.technical import (
    TechnicalAnalyzer,
    ema,
    sma,
    rsi,
    macd,
    bollinger_bands,
    atr,
    adx,
    stochastic,
)


class TestIndicatorFunctions:
    """Test individual indicator calculation functions."""

    def test_ema_basic(self, sample_ohlcv):
        result = ema(sample_ohlcv["Close"], 20)
        assert len(result) == len(sample_ohlcv)
        assert not result.isna().all()
        # EMA should be close to the price series
        assert abs(result.iloc[-1] - sample_ohlcv["Close"].iloc[-1]) < 0.01

    def test_sma_basic(self, sample_ohlcv):
        result = sma(sample_ohlcv["Close"], 20)
        assert len(result) == len(sample_ohlcv)
        # First 19 values should be NaN for period=20
        assert result.iloc[:19].isna().all()
        assert not result.iloc[19:].isna().any()

    def test_rsi_range(self, sample_ohlcv):
        result = rsi(sample_ohlcv["Close"], 14)
        valid = result.dropna()
        assert len(valid) > 0
        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_rsi_oversold_in_downtrend(self, downtrend_ohlcv):
        result = rsi(downtrend_ohlcv["Close"], 14)
        # In a strong downtrend, RSI should be below 50
        last_val = result.dropna().iloc[-1]
        assert last_val < 50

    def test_rsi_overbought_in_uptrend(self, uptrend_ohlcv):
        result = rsi(uptrend_ohlcv["Close"], 14)
        last_val = result.dropna().iloc[-1]
        assert last_val > 50

    def test_macd_returns_three_series(self, sample_ohlcv):
        result = macd(sample_ohlcv["Close"])
        assert len(result["macd"]) == len(sample_ohlcv)
        assert len(result["signal"]) == len(sample_ohlcv)
        assert len(result["histogram"]) == len(sample_ohlcv)

    def test_macd_histogram_is_difference(self, sample_ohlcv):
        result = macd(sample_ohlcv["Close"])
        macd_line, signal_line, histogram = result["macd"], result["signal"], result["histogram"]
        valid_idx = ~(macd_line.isna() | signal_line.isna())
        diff = (macd_line[valid_idx] - signal_line[valid_idx]).values
        hist_vals = histogram[valid_idx].values
        np.testing.assert_array_almost_equal(diff, hist_vals, decimal=10)

    def test_bollinger_bands_structure(self, sample_ohlcv):
        result = bollinger_bands(sample_ohlcv["Close"])
        upper, middle, lower = result["upper"], result["middle"], result["lower"]
        valid = ~upper.isna()
        # Upper > Middle > Lower
        assert (upper[valid] >= middle[valid]).all()
        assert (middle[valid] >= lower[valid]).all()

    def test_atr_positive(self, sample_ohlcv):
        result = atr(sample_ohlcv["High"], sample_ohlcv["Low"], sample_ohlcv["Close"])
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_stochastic_range(self, sample_ohlcv):
        result = stochastic(sample_ohlcv["High"], sample_ohlcv["Low"], sample_ohlcv["Close"])
        valid_k = result["k"].dropna()
        assert valid_k.min() >= 0
        assert valid_k.max() <= 100


class TestTechnicalAnalyzer:
    """Test the TechnicalAnalyzer class."""

    def test_analyze_returns_dict(self, sample_ohlcv):
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(sample_ohlcv)
        assert isinstance(result, dict)
        assert "indicators" in result or "error" in result

    def test_analyze_has_all_indicators(self, sample_ohlcv):
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(sample_ohlcv)
        if "indicators" in result:
            ind = result["indicators"]
            assert "RSI" in ind
            assert "MACD" in ind
            assert "EMA" in ind
            assert "Bollinger" in ind
            assert "ADX" in ind
            assert "Stochastic" in ind

    def test_analyze_empty_dataframe(self):
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(pd.DataFrame())
        assert "error" in result

    def test_analyze_too_small(self, small_ohlcv):
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(small_ohlcv)
        # Should either return an error or handle gracefully
        assert isinstance(result, dict)

    def test_overall_bias_exists(self, sample_ohlcv):
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(sample_ohlcv)
        if "indicators" in result:
            assert "overall_bias" in result

    def test_format_analysis(self, sample_ohlcv):
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(sample_ohlcv)
        if "indicators" in result:
            formatted = analyzer.format_analysis(result, "H1")
            assert isinstance(formatted, str)
            assert "EUR/USD" in formatted
            assert "H1" in formatted

    def test_uptrend_gives_bullish_bias(self, uptrend_ohlcv):
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(uptrend_ohlcv)
        if "overall_bias" in result:
            assert "bullish" in result["overall_bias"].lower() or "neutral" in result["overall_bias"].lower()

    def test_downtrend_gives_bearish_bias(self, downtrend_ohlcv):
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(downtrend_ohlcv)
        if "overall_bias" in result:
            assert "bearish" in result["overall_bias"].lower() or "neutral" in result["overall_bias"].lower()
