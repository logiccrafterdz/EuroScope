"""
Capital.com Data Provider Wrapper

Bridges the trading layer's CapitalProvider to the data layer 
for use in MultiSourceProvider.
"""

import logging
from typing import Optional
import pandas as pd
from datetime import datetime, UTC

from ..trading.capital_provider import CapitalProvider
from ..utils.resilience import async_retry

logger = logging.getLogger("euroscope.data.capital")

class CapitalDataProvider:
    """Provides EUR/USD price data using the Capital.com API."""

    def __init__(self, api_key: str, identifier: str, password: str):
        self.provider = CapitalProvider(api_key, identifier, password)
        self._last_known_price: Optional[dict] = None

    @async_retry(max_attempts=2, delay=1.0, exceptions=(Exception,))
    async def get_price(self) -> dict:
        """Get current EUR/USD price via Capital.com."""
        try:
            # We fetch H1 candles to get high/low/open for the day roughly
            # Capital.com API doesn't have a simple 'get_ticker' for stats 
            # as cleanly as OANDA or yfinance, so we use recent candles.
            df = await self.provider.get_candles("EURUSD", timeframe="H1", count=24)
            if df is None or df.empty:
                return {"error": "No data from Capital.com"}

            latest = df.iloc[-1]
            prev_close = df.iloc[0]["Close"]
            current = float(latest["Close"])
            
            day_open = float(df.iloc[0]["Open"])
            day_high = float(df["High"].max())
            day_low = float(df["Low"].min())
            
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
            self._last_known_price = result.copy()
            return result
        except Exception as e:
            logger.error(f"Capital.com price fetch error: {e}")
            if self._last_known_price:
                cached = self._last_known_price.copy()
                cached["cached"] = True
                return cached
            return {"error": str(e)}

    @async_retry(max_attempts=2, delay=1.0, exceptions=(Exception,))
    async def get_candles(self, timeframe: str = "H1", count: int = 100) -> Optional[pd.DataFrame]:
        """Fetch OHLCV candles from Capital.com."""
        return await self.provider.get_candles("EURUSD", timeframe=timeframe, count=count)
