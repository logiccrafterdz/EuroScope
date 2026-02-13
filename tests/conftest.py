"""
Shared pytest fixtures for EuroScope tests.
"""

import os
import tempfile
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv():
    """Generate a realistic EUR/USD OHLCV DataFrame (~100 candles)."""
    np.random.seed(42)
    n = 100
    base_price = 1.0850

    # Random walk for price
    returns = np.random.normal(0, 0.0005, n)
    close = base_price + np.cumsum(returns)

    high = close + np.abs(np.random.normal(0.0003, 0.0002, n))
    low = close - np.abs(np.random.normal(0.0003, 0.0002, n))
    open_prices = close + np.random.normal(0, 0.0002, n)
    volume = np.random.randint(1000, 50000, n).astype(float)

    dates = pd.date_range(end=datetime.utcnow(), periods=n, freq="1h")

    df = pd.DataFrame({
        "Open": open_prices,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)

    return df


@pytest.fixture
def small_ohlcv():
    """Small OHLCV DataFrame (10 candles) for edge-case testing."""
    np.random.seed(99)
    n = 10
    base_price = 1.0900

    returns = np.random.normal(0, 0.0003, n)
    close = base_price + np.cumsum(returns)
    high = close + 0.0005
    low = close - 0.0005
    open_prices = close + np.random.normal(0, 0.0001, n)
    volume = np.random.randint(100, 5000, n).astype(float)

    dates = pd.date_range(end=datetime.utcnow(), periods=n, freq="1h")

    return pd.DataFrame({
        "Open": open_prices,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)


@pytest.fixture
def uptrend_ohlcv():
    """OHLCV with a clear uptrend for testing bullish signals."""
    n = 60
    base = 1.0800
    close = np.array([base + i * 0.0005 for i in range(n)])
    high = close + 0.0003
    low = close - 0.0003
    open_prices = close - 0.0002
    volume = np.full(n, 10000.0)

    dates = pd.date_range(end=datetime.utcnow(), periods=n, freq="1h")

    return pd.DataFrame({
        "Open": open_prices,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)


@pytest.fixture
def downtrend_ohlcv():
    """OHLCV with a clear downtrend for testing bearish signals."""
    n = 60
    base = 1.1100
    close = np.array([base - i * 0.0005 for i in range(n)])
    high = close + 0.0003
    low = close - 0.0003
    open_prices = close + 0.0002
    volume = np.full(n, 10000.0)

    dates = pd.date_range(end=datetime.utcnow(), periods=n, freq="1h")

    return pd.DataFrame({
        "Open": open_prices,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)


@pytest.fixture
def temp_db_path():
    """Provide a temporary database path that is cleaned up after the test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        if os.path.exists(path):
            os.unlink(path)
    except PermissionError:
        pass  # Windows may still lock the file
