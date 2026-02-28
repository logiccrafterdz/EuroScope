"""
OANDA Data Provider

Fetches real-time and historical OHLCV data for EUR/USD
using the OANDA REST API (v20) for zero-latency, reliable forex ticks.
"""

import asyncio
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional

import pandas as pd
import aiohttp

from ..utils.resilience import async_retry

logger = logging.getLogger("euroscope.data.oanda")

# OANDA v20 REST API URLs
OANDA_PRACTICE_URL = "https://api-fxpractice.oanda.com/v3"
OANDA_LIVE_URL = "https://api-fxtrade.oanda.com/v3"

OANDA_INSTRUMENT = "EUR_USD"

# Timeframe mappings: our label → OANDA granularity
TIMEFRAMES = {
    "M1": "M1",
    "M15": "M15",
    "H1": "H1",
    "H4": "H4",
    "D1": "D",
    "W1": "W",
}


class OandaProvider:
    """Fetches EUR/USD price data directly from OANDA."""

    def __init__(self, api_key: str, account_id: str = "", is_practice: bool = True):
        self.api_key = api_key
        self.account_id = account_id
        self.base_url = OANDA_PRACTICE_URL if is_practice else OANDA_LIVE_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept-Datetime-Format": "RFC3339"
        }
        self._cache: dict[str, tuple[pd.DataFrame, datetime]] = {}
        self._cache_ttl = timedelta(minutes=1) # Fast cache for tick data
        self._last_known_price: Optional[dict] = None

    @async_retry(max_attempts=3, delay=1.0, exceptions=(Exception,))
    async def get_price(self) -> dict:
        """Get current EUR/USD precise price."""
        if not self.api_key:
            return {"error": "OANDA API key not configured"}
            
        url = f"{self.base_url}/instruments/{OANDA_INSTRUMENT}/candles"
        params = {
            "count": 2, # Need current and previous to calculate change
            "granularity": "D", # Daily to get day open/high/low
            "price": "M" # Midpoint price
        }

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status != 200:
                        err_txt = await response.text()
                        logger.error(f"OANDA API error: {response.status} - {err_txt}")
                        return {"error": f"OANDA API error {response.status}"}
                        
                    data = await response.json()
                    
                    if not data.get("candles"):
                        return {"error": "No price data returned"}
                        
                    candles = data["candles"]
                    latest = candles[-1]
                    prev = candles[0] if len(candles) > 1 else latest
                    
                    if not latest.get("complete", False) and len(candles) > 0:
                        # Use the current forming daily candle for real-time midpoint
                        pass
                        
                    current = float(latest["mid"]["c"])
                    prev_close = float(prev["mid"]["c"])
                    day_open = float(latest["mid"]["o"])
                    day_high = float(latest["mid"]["h"])
                    day_low = float(latest["mid"]["l"])
                    
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
            logger.error(f"OANDA fetch error: {e}")
            if self._last_known_price:
                cached = self._last_known_price.copy()
                cached["cached"] = True
                cached["timestamp"] = f"{cached.get('timestamp', '')} (CACHED)"
                return cached
            return {"error": str(e)}

    @async_retry(max_attempts=3, delay=1.0, exceptions=(Exception,))
    async def get_candles(self, timeframe: str = "H1", count: int = 100) -> Optional[pd.DataFrame]:
        """Get precise OHLCV tick data from OANDA."""
        if not self.api_key:
            return None
            
        tf = timeframe.upper()
        oanda_granularity = TIMEFRAMES.get(tf, "H1")
        
        cache_key = f"candles_{tf}"
        if cache_key in self._cache:
            df, cached_at = self._cache[cache_key]
            if datetime.now(UTC) - cached_at < self._cache_ttl:
                return df.tail(count).copy()

        url = f"{self.base_url}/instruments/{OANDA_INSTRUMENT}/candles"
        
        # Determine how many candles we really need
        fetch_count = count
        if tf == "M1": fetch_count = min(count, 500)
        
        params = {
            "count": fetch_count,
            "granularity": oanda_granularity,
            "price": "M" # Midpoint price
        }

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, params=params, timeout=15) as response:
                    if response.status != 200:
                        logger.error(f"OANDA candle fetch failed: {response.status}")
                        return None
                        
                    data = await response.json()
                    candles = data.get("candles", [])
                    
                    if not candles:
                        return None
                        
                    records = []
                    for c in candles:
                        records.append({
                            "time": pd.to_datetime(c["time"]),
                            "Open": float(c["mid"]["o"]),
                            "High": float(c["mid"]["h"]),
                            "Low": float(c["mid"]["l"]),
                            "Close": float(c["mid"]["c"]),
                            "Volume": float(c["volume"])  # Tick volume
                        })
                        
                    df = pd.DataFrame(records)
                    df.set_index("time", inplace=True)
                    
                    self._cache[cache_key] = (df, datetime.now(UTC))
                    return df.copy()

        except Exception as e:
            logger.error(f"Error fetching OANDA {tf} candles: {e}")
            return None

    async def close(self):
        """No persistent session held, but added for API consistency."""
        pass
