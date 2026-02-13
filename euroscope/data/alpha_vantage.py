"""
Alpha Vantage Price Data Provider

Fallback data source for EUR/USD OHLCV data using Alpha Vantage Forex API.
Free tier: 5 API calls per minute, 500 per day.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger("euroscope.data.alphavantage")

BASE_URL = "https://www.alphavantage.co/query"

# Map our timeframes to Alpha Vantage intervals
AV_TIMEFRAMES = {
    "M15": {"function": "FX_INTRADAY", "interval": "15min", "outputsize": "compact"},
    "H1":  {"function": "FX_INTRADAY", "interval": "60min", "outputsize": "full"},
    "H4":  {"function": "FX_INTRADAY", "interval": "60min", "outputsize": "full"},  # resample
    "D1":  {"function": "FX_DAILY",    "interval": None,    "outputsize": "compact"},
    "W1":  {"function": "FX_WEEKLY",   "interval": None,    "outputsize": None},
}


class AlphaVantageProvider:
    """Fetches EUR/USD data from Alpha Vantage as a fallback source."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._cache: dict[str, tuple[pd.DataFrame, datetime]] = {}
        self._cache_ttl = timedelta(minutes=10)
        self._last_call = 0.0  # rate limiting

    def _rate_limit(self):
        """Enforce rate limit: minimum 12s between calls (5/min)."""
        elapsed = time.time() - self._last_call
        if elapsed < 12:
            time.sleep(12 - elapsed)
        self._last_call = time.time()

    def get_price(self) -> dict:
        """Get current EUR/USD price via Alpha Vantage."""
        if not self.api_key:
            return {"error": "Alpha Vantage API key not configured"}

        try:
            self._rate_limit()
            with httpx.Client(timeout=15) as client:
                resp = client.get(BASE_URL, params={
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": "EUR",
                    "to_currency": "USD",
                    "apikey": self.api_key,
                })
                resp.raise_for_status()
                data = resp.json()

            rate_data = data.get("Realtime Currency Exchange Rate", {})
            if not rate_data:
                return {"error": "No data returned from Alpha Vantage"}

            price = float(rate_data.get("5. Exchange Rate", 0))
            bid = float(rate_data.get("8. Bid Price", price))
            ask = float(rate_data.get("9. Ask Price", price))

            return {
                "symbol": "EUR/USD",
                "price": round(price, 5),
                "bid": round(bid, 5),
                "ask": round(ask, 5),
                "spread_pips": round((ask - bid) * 10000, 1),
                "source": "alphavantage",
                "timestamp": rate_data.get("6. Last Refreshed", ""),
            }

        except Exception as e:
            logger.error(f"Alpha Vantage price error: {e}")
            return {"error": str(e)}

    def get_candles(self, timeframe: str = "H1", count: int = 100) -> Optional[pd.DataFrame]:
        """Get OHLCV candle data from Alpha Vantage."""
        tf = timeframe.upper()
        if tf not in AV_TIMEFRAMES:
            logger.warning(f"Unknown timeframe: {tf}, falling back to H1")
            tf = "H1"

        if not self.api_key:
            logger.warning("Alpha Vantage API key not set")
            return None

        # Check cache
        cache_key = f"av_candles_{tf}"
        if cache_key in self._cache:
            df, cached_at = self._cache[cache_key]
            if datetime.utcnow() - cached_at < self._cache_ttl:
                return df.tail(count).copy()

        try:
            self._rate_limit()
            params = AV_TIMEFRAMES[tf]

            request_params = {
                "function": params["function"],
                "from_symbol": "EUR",
                "to_symbol": "USD",
                "apikey": self.api_key,
            }
            if params["interval"]:
                request_params["interval"] = params["interval"]
            if params["outputsize"]:
                request_params["outputsize"] = params["outputsize"]

            with httpx.Client(timeout=30) as client:
                resp = client.get(BASE_URL, params=request_params)
                resp.raise_for_status()
                data = resp.json()

            # Find the time series key
            ts_key = None
            for key in data:
                if "Time Series" in key:
                    ts_key = key
                    break

            if not ts_key or not data.get(ts_key):
                logger.warning(f"No time series data returned for {tf}")
                return None

            # Parse into DataFrame
            records = []
            for date_str, values in data[ts_key].items():
                records.append({
                    "datetime": pd.to_datetime(date_str),
                    "Open": float(values.get("1. open", 0)),
                    "High": float(values.get("2. high", 0)),
                    "Low": float(values.get("3. low", 0)),
                    "Close": float(values.get("4. close", 0)),
                    "Volume": 0.0,  # Forex doesn't have real volume in AV
                })

            df = pd.DataFrame(records)
            df.set_index("datetime", inplace=True)
            df.sort_index(inplace=True)

            # Resample for H4
            if tf == "H4":
                df = df.resample("4h").agg({
                    "Open": "first", "High": "max",
                    "Low": "min", "Close": "last",
                    "Volume": "sum",
                }).dropna()

            # Cache
            self._cache[cache_key] = (df, datetime.utcnow())
            logger.info(f"Alpha Vantage: fetched {len(df)} candles for {tf}")
            return df.tail(count).copy()

        except Exception as e:
            logger.error(f"Alpha Vantage candle error for {tf}: {e}")
            return None

    def clear_cache(self):
        """Clear cached data."""
        self._cache.clear()
