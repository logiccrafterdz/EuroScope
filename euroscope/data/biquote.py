"""
BiQuote Real-Time Data Provider

Free API for real-time forex data without API key.
Provides EUR/USD live prices via REST API.
"""

import asyncio
import logging
from datetime import datetime, UTC
from typing import Optional

import requests

logger = logging.getLogger("euroscope.data.biquote")


class BiQuoteProvider:
    """Real-time EUR/USD price data from BiQuote free API."""

    def __init__(self):
        self.base_url = "https://biquote.io/api"
        self._last_known_price: Optional[dict] = None
        self._session = requests.Session()

    async def get_price(self) -> dict:
        """Get current EUR/USD price from BiQuote API."""
        try:
            url = f"{self.base_url}/EURUSD"
            response = self._session.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                # BiQuote returns: symbol, bid, ask, last (0.0), mid, spread, etc.
                bid = float(data.get("bid", 0))
                ask = float(data.get("ask", 0))
                mid = float(data.get("mid", (bid + ask) / 2 if bid and ask else 0))
                spread = float(data.get("spread", ask - bid))
                
                # Use mid price as the main price (bid/ask are 0.0 in some cases)
                price = mid if mid > 0 else bid
                
                # Get daily high/low from API
                day_high = float(data.get("high", ask))
                day_low = float(data.get("low", bid))
                
                # Calculate change from day high/low
                change_pct = float(data.get("dayDiffPercent", 0))
                change = price * change_pct / 100 if price else 0
                
                result = {
                    "symbol": "EUR/USD",
                    "price": round(price, 5),
                    "bid": round(bid, 5),
                    "ask": round(ask, 5),
                    "spread": round(spread * 10000, 1),  # in pips
                    "open": round(price, 5),  # BiQuote doesn't provide open directly
                    "high": round(day_high, 5),
                    "low": round(day_low, 5),
                    "change": round(change, 5),
                    "change_pct": round(change_pct, 3),
                    "direction": "UP" if change >= 0 else "DOWN",
                    "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
                    "source": "biquote"
                }
                
                self._last_known_price = result.copy()
                return result
            else:
                logger.warning(f"BiQuote API returned status {response.status_code}")
                return {"error": f"API returned status {response.status_code}"}
                
        except requests.exceptions.Timeout:
            logger.warning("BiQuote API timeout")
            return {"error": "Request timeout"}
        except requests.exceptions.ConnectionError:
            logger.warning("BiQuote API connection error")
            return {"error": "Connection error"}
        except Exception as e:
            logger.error(f"BiQuote API error: {e}")
            return {"error": str(e)}

    async def get_candles(self, timeframe: str = "H1", count: int = 100, **kwargs):
        """
        Build synthetic candles from BiQuote live price data.

        BiQuote doesn't provide historical candles, so we fetch the current
        price snapshot and build a single live candle from it.  The real
        historical data comes from yfinance (via MultiSourceProvider).
        """
        import pandas as pd
        from datetime import datetime, timedelta, UTC

        try:
            price_data = await self.get_price()
            if "error" in price_data:
                logger.warning("BiQuote: cannot build candles, price fetch failed")
                return None

            now = datetime.now(UTC)
            price = price_data["price"]
            high = price_data["high"]
            low = price_data["low"]
            bid = price_data.get("bid", price)
            ask = price_data.get("ask", price)

            # Build a single candle representing the current live snapshot
            candle = pd.DataFrame(
                [{
                    "Open": round(low, 5),
                    "High": round(high, 5),
                    "Low": round(low, 5),
                    "Close": round(price, 5),
                    "Volume": 0,
                }],
                index=pd.DatetimeIndex([now], name="Datetime"),
            )

            logger.debug(f"BiQuote: built 1 live candle at {price}")
            return candle

        except Exception as e:
            logger.error(f"BiQuote: candle build failed: {e}")
            return None

    async def close(self):
        """Close the session."""
        self._session.close()
