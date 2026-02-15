"""
Tiingo Price Data Provider

High-fidelity historical and real-time EUR/USD data.
Free tier: 1,000 requests per day, 50 per hour.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger("euroscope.data.tiingo")

BASE_URL = "https://api.tiingo.com/tiingo/fx"

# Map our timeframes to Tiingo intervals
TIINGO_INTERVALS = {
    "M1": "1min",
    "M15": "15min",
    "H1": "1hour",
    "H4": "4hour",
    "D1": "1day",
}

class TiingoProvider:
    """Fetches EUR/USD data from Tiingo API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._cache: dict[str, tuple[pd.DataFrame, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._last_call = 0.0

    def _rate_limit(self):
        """Tiingo free tier has hourly/daily limits, but we add a small safety buffer."""
        elapsed = time.time() - self._last_call
        if elapsed < 1.0:  # 1 second between calls safety
            time.sleep(1.0 - elapsed)
        self._last_call = time.time()

    async def get_price(self) -> dict:
        """Get current EUR/USD price via Tiingo Top of Book."""
        if not self.api_key:
            return {"error": "Tiingo API key not configured"}

        try:
            self._rate_limit()
            headers = {"Content-Type": "application/json", "Authorization": f"Token {self.api_key}"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{BASE_URL}/top", params={"tickers": "eurusd"}, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            if not data or not isinstance(data, list):
                return {"error": "Invalid response from Tiingo"}

            item = data[0]
            price = float(item.get("last", 0))
            bid = float(item.get("bidPrice", price))
            ask = float(item.get("askPrice", price))

            return {
                "symbol": "EUR/USD",
                "price": round(price, 5),
                "bid": round(bid, 5),
                "ask": round(ask, 5),
                "spread_pips": round((ask - bid) * 10000, 1),
                "source": "tiingo",
                "timestamp": item.get("quoteTimestamp", ""),
            }
        except Exception as e:
            logger.error(f"Tiingo price error: {e}")
            return {"error": str(e)}

    async def get_candles(self, timeframe: str = "H1", count: int = 100, 
                          start_date: Optional[datetime] = None, 
                          end_date: Optional[datetime] = None) -> Optional[pd.DataFrame]:
        """Get OHLCV candle data from Tiingo."""
        if not self.api_key:
            logger.warning("Tiingo API key not set")
            return None

        tf = timeframe.upper()
        interval = TIINGO_INTERVALS.get(tf, "1hour")

        # Use cache only if no custom date range
        cache_key = f"tiingo_candles_{tf}_{count}"
        if not start_date and not end_date:
            if cache_key in self._cache:
                df, cached_at = self._cache[cache_key]
                if datetime.utcnow() - cached_at < self._cache_ttl:
                    return df.tail(count).copy()

        try:
            self._rate_limit()
            headers = {"Content-Type": "application/json", "Authorization": f"Token {self.api_key}"}
            
            params = {
                "tickers": "eurusd",
                "resampleFreq": interval,
            }
            
            if start_date:
                params["startDate"] = start_date.isoformat()
            if end_date:
                params["endDate"] = end_date.isoformat()

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{BASE_URL}/prices", params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            if not data or not isinstance(data, list):
                logger.warning(f"No data returned from Tiingo for {tf}")
                return None

            # Parse Tiingo response
            records = []
            for item in data:
                # Tiingo returns prices as a list of points
                records.append({
                    "datetime": pd.to_datetime(item.get("date")),
                    "Open": float(item.get("open", 0)),
                    "High": float(item.get("high", 0)),
                    "Low": float(item.get("low", 0)),
                    "Close": float(item.get("close", 0)),
                    "Volume": float(item.get("volume", 0))
                })

            df = pd.DataFrame(records)
            if df.empty:
                return None
                
            df.set_index("datetime", inplace=True)
            df.sort_index(inplace=True)
            
            # Remove timezone if present for consistency
            if getattr(df.index, "tz", None) is not None:
                df.index = df.index.tz_localize(None)

            if not start_date and not end_date:
                self._cache[cache_key] = (df, datetime.utcnow())
                return df.tail(count).copy()
            
            return df.copy()

        except Exception as e:
            logger.error(f"Tiingo candle error for {tf}: {e}")
            return None

    def clear_cache(self):
        self._cache.clear()
