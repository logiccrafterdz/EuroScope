"""
Multi-Source Data Provider

Aggregates price data from multiple sources with automatic failover.
Primary: yfinance | Fallback: Alpha Vantage
"""

import logging
from typing import Optional

import pandas as pd

from .provider import PriceProvider
from .alpha_vantage import AlphaVantageProvider
from .tiingo import TiingoProvider

logger = logging.getLogger("euroscope.data.multi")


class MultiSourceProvider:
    """
    Unified price provider that tries multiple data sources.

    Tries yfinance first, then Tiingo, then Alpha Vantage.
    """

    def __init__(self, alphavantage_key: str = "", tiingo_key: str = ""):
        self.primary = PriceProvider()
        self.tiingo = TiingoProvider(tiingo_key) if tiingo_key else None
        self.fallback = AlphaVantageProvider(alphavantage_key) if alphavantage_key else None
        self._last_source = "yfinance"

    @property
    def last_source(self) -> str:
        """Which data source was used for the last successful call."""
        return self._last_source

    async def get_price(self) -> dict:
        """Get current EUR/USD price with automatic failover."""
        # Try primary (yfinance)
        result = await self.primary.get_price()
        if "error" not in result:
            self._last_source = "yfinance"
            result["source"] = "yfinance"
            return result

        logger.warning(f"yfinance price failed: {result.get('error')}, trying Tiingo...")

        # Try Tiingo
        if self.tiingo:
            result = await self.tiingo.get_price()
            if "error" not in result:
                self._last_source = "tiingo"
                return result
            logger.warning(f"Tiingo price failed: {result.get('error')}, trying Alpha Vantage...")

        # Try fallback (Alpha Vantage)
        if self.fallback:
            result = self.fallback.get_price()
            if "error" not in result:
                self._last_source = "alphavantage"
                return result
            logger.error(f"Alpha Vantage also failed: {result.get('error')}")

        return {"error": "All price data sources failed"}

    async def get_candles(self, timeframe: str = "H1", count: int = 100) -> Optional[pd.DataFrame]:
        """Get OHLCV candles with automatic failover."""
        # Try primary
        df = await self.primary.get_candles(timeframe, count)
        if df is not None and not df.empty:
            df = self._validate_data(df)
            if df is not None:
                self._last_source = "yfinance"
                return df

        logger.warning(f"yfinance candles failed for {timeframe}, trying Tiingo...")

        # Try Tiingo
        if self.tiingo:
            df = await self.tiingo.get_candles(timeframe, count)
            if df is not None and not df.empty:
                df = self._validate_data(df)
                if df is not None:
                    self._last_source = "tiingo"
                    return df
                logger.error(f"Tiingo data failed validation for {timeframe}")

        logger.warning(f"Tiingo candles failed for {timeframe}, trying Alpha Vantage...")

        # Try fallback
        if self.fallback:
            df = self.fallback.get_candles(timeframe, count)
            if df is not None and not df.empty:
                df = self._validate_data(df)
                if df is not None:
                    self._last_source = "alphavantage"
                    return df
                logger.error(f"Alpha Vantage data failed validation for {timeframe}")

        return None

    def get_multi_timeframe(self) -> dict[str, Optional[pd.DataFrame]]:
        """Get candles for all standard timeframes."""
        timeframes = ["M15", "H1", "H4", "D1", "W1"]
        return {tf: self.get_candles(tf) for tf in timeframes}

    @staticmethod
    def _validate_data(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Validate OHLCV data quality.

        Checks:
        - No excessive NaN values (> 20% threshold)
        - OHLC relationships are valid (High >= Low)
        - Prices are in a reasonable range for EUR/USD
        """
        if df is None or df.empty:
            return None

        required = ["Open", "High", "Low", "Close"]
        for col in required:
            if col not in df.columns:
                logger.error(f"Missing column: {col}")
                return None

        # Check NaN ratio
        nan_ratio = df[required].isna().sum().sum() / (len(df) * len(required))
        if nan_ratio > 0.2:
            logger.warning(f"Data has {nan_ratio:.0%} NaN values — too many")
            return None

        # Drop rows with NaN
        df = df.dropna(subset=required)

        # Check High >= Low
        invalid = df[df["High"] < df["Low"]]
        if len(invalid) > 0:
            logger.warning(f"Found {len(invalid)} rows with High < Low — fixing")
            df.loc[df["High"] < df["Low"], ["High", "Low"]] = \
                df.loc[df["High"] < df["Low"], ["Low", "High"]].values

        # EUR/USD sanity range (0.80 - 1.60 is generous)
        price_range = df["Close"]
        if price_range.min() < 0.80 or price_range.max() > 1.60:
            logger.warning(f"Prices outside EUR/USD range: {price_range.min():.4f} - {price_range.max():.4f}")
            return None

        return df

    def clear_cache(self):
        """Clear all caches."""
        self.primary.clear_cache()
        if self.fallback:
            self.fallback.clear_cache()
