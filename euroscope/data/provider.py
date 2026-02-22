"""
EUR/USD Price Data Provider

Fetches real-time and historical OHLCV data for EUR/USD
using yfinance with local caching.
"""

import asyncio
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional

import pandas as pd
import yfinance as yf

from ..utils.resilience import async_retry

logger = logging.getLogger("euroscope.data")

# Yahoo Finance symbol for EUR/USD
EURUSD_SYMBOL = "EURUSD=X"

# Timeframe mappings: our label → yfinance args
TIMEFRAMES = {
    "M1":  {"interval": "1m",  "period": "2d"},
    "M15": {"interval": "15m", "period": "5d"},
    "H1":  {"interval": "1h",  "period": "30d"},
    "H4":  {"interval": "1h",  "period": "60d"},  # We resample H1 → H4
    "D1":  {"interval": "1d",  "period": "1y"},
    "W1":  {"interval": "1wk", "period": "2y"},
}


class PriceProvider:
    """Fetches and caches EUR/USD price data."""

    def __init__(self):
        self._cache: dict[str, tuple[pd.DataFrame, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._last_known_price: Optional[dict] = None  # Fallback for weekends

    @async_retry(max_attempts=3, delay=1.0, exceptions=(Exception,))
    async def get_price(self) -> dict:
        """Get current EUR/USD price and daily stats."""
        try:
            ticker = yf.Ticker(EURUSD_SYMBOL)
            info = ticker.fast_info

            # Get today's 1-minute data for latest price
            hist = ticker.history(period="2d", interval="1h")
            if hist.empty:
                # Return last known price if available (weekend/offline fallback)
                if self._last_known_price:
                    cached = self._last_known_price.copy()
                    cached["cached"] = True
                    cached["timestamp"] = f"{cached.get('timestamp', '')} (CACHED)"
                    return cached
                return {"error": "Unable to fetch price data"}

            current = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[0])
            day_open = float(hist["Open"].iloc[-24]) if len(hist) >= 24 else prev_close
            day_high = float(hist["High"].tail(24).max()) if len(hist) >= 24 else float(hist["High"].max())
            day_low = float(hist["Low"].tail(24).min()) if len(hist) >= 24 else float(hist["Low"].min())

            change = current - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0

            result = {
                "symbol": "EUR/USD",
                "price": round(current, 5),
                "open": round(day_open, 5),
                "high": round(day_high, 5),
                "low": round(day_low, 5),
                "change": round(change, 5),
                "change_pct": round(change_pct, 3),
                "direction": "🟢" if change >= 0 else "🔴",
                "spread_pips": round(abs(day_high - day_low) * 10000, 1),
                "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            }
            # Store as fallback for offline/weekend periods
            self._last_known_price = result.copy()
            return result
        except Exception as e:
            logger.error(f"Error fetching price: {e}")
            # Return cached price if available
            if self._last_known_price:
                cached = self._last_known_price.copy()
                cached["cached"] = True
                cached["timestamp"] = f"{cached.get('timestamp', '')} (CACHED)"
                return cached
            return {"error": str(e)}

    @async_retry(max_attempts=3, delay=1.0, exceptions=(Exception,))
    async def get_candles(self, timeframe: str = "H1", count: int = 100) -> Optional[pd.DataFrame]:
        """
        Get OHLCV candle data for the specified timeframe.

        Args:
            timeframe: One of M15, H1, H4, D1, W1
            count: Number of candles to return

        Returns:
            DataFrame with Open, High, Low, Close, Volume columns
        """
        tf = timeframe.upper()
        if tf not in TIMEFRAMES:
            logger.warning(f"Unknown timeframe: {tf}, falling back to H1")
            tf = "H1"

        # Check cache
        cache_key = f"candles_{tf}"
        if cache_key in self._cache:
            df, cached_at = self._cache[cache_key]
            if datetime.now(UTC) - cached_at < self._cache_ttl:
                return df.tail(count).copy()

        try:
            params = TIMEFRAMES[tf]
            ticker = yf.Ticker(EURUSD_SYMBOL)
            df = ticker.history(period=params["period"], interval=params["interval"])

            if df.empty:
                logger.warning(f"No data returned for {tf}")
                return None

            # Clean up columns
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.index = pd.to_datetime(df.index)

            # For H4: resample from H1
            if tf == "H4":
                df = df.resample("4h").agg({
                    "Open": "first",
                    "High": "max",
                    "Low": "min",
                    "Close": "last",
                    "Volume": "sum",
                }).dropna()

            # Cache it
            self._cache[cache_key] = (df, datetime.now(UTC))

            logger.info(f"Fetched {len(df)} candles for {tf}")
            return df.tail(count).copy()

        except Exception as e:
            logger.error(f"Error fetching {tf} candles: {e}")
            return None

    async def get_multi_timeframe(self) -> dict[str, Optional[pd.DataFrame]]:
        tasks: dict[str, object] = {}
        for tf in TIMEFRAMES:
            try:
                tasks[tf] = self.get_candles(tf)
            except Exception as e:
                logger.warning(f"Failed to create task for {tf}: {e}")
                tasks[tf] = None

        valid_tasks = {k: v for k, v in tasks.items() if v is not None}
        if not valid_tasks:
            logger.error("No valid timeframe tasks created")
            return {}

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*valid_tasks.values(), return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error("Multi-timeframe fetch timed out after 30s")
            return {}

        output: dict[str, Optional[pd.DataFrame]] = {}
        for tf, result in zip(valid_tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch {tf}: {result}")
                output[tf] = None
            else:
                output[tf] = result

        return output

    def clear_cache(self):
        """Clear the price data cache."""
        self._cache.clear()
