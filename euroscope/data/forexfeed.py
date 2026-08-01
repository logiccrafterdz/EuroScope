"""
Verified EUR/USD feed from two independent institutional sources.

TrueFX (Integral OCX) and Swissquote public BBO quotes are both free,
keyless, institutional-grade feeds. They are fetched in parallel and
cross-verified: the consensus mid is returned together with per-source
values and the observed deviation between the two feeds.
"""

import asyncio
import logging
from datetime import datetime, UTC
from typing import Optional

import httpx

logger = logging.getLogger("euroscope.data.forexfeed")

REQUEST_TIMEOUT = 6.0
MAX_DEVIATION_PIPS = 5.0

TRUEFX_URL = "https://webrates.truefx.com/rates/connect.html"
_SWQ_BASE = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes"
SWISSQUOTE_URL = f"{_SWQ_BASE}/instrument/EUR/USD"


class ForexFeedProvider:
    """Cross-verified EUR/USD price from TrueFX + Swissquote (no API keys)."""

    def __init__(self):
        self._session = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, follow_redirects=True
        )
        self._last_known_price: Optional[dict] = None

    async def _truefx(self) -> dict:
        r = await self._session.get(
            TRUEFX_URL,
            params={"a": 1, "q": "eurusd", "f": "csv"},
        )
        r.raise_for_status()
        for line in r.text.splitlines():
            parts = line.split(",")
            if parts and parts[0] == "EUR/USD":
                bid = float(parts[2] + parts[3])
                ask = float(parts[4] + parts[5])
                return {"bid": bid, "ask": ask, "mid": (bid + ask) / 2}
        raise ValueError("EUR/USD not present in TrueFX snapshot")

    async def _swissquote(self) -> dict:
        r = await self._session.get(SWISSQUOTE_URL)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list) or not data:
            raise ValueError("Unexpected Swissquote response")
        profile = data[0]["spreadProfilePrices"][0]
        bid = float(profile["bid"])
        ask = float(profile["ask"])
        return {"bid": bid, "ask": ask, "mid": (bid + ask) / 2}

    async def get_price(self) -> dict:
        """Fetch both feeds in parallel and cross-verify them."""
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    self._truefx(), self._swissquote(), return_exceptions=True
                ),
                timeout=REQUEST_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("ForexFeed: parallel fetch timed out")
            results = [
                asyncio.TimeoutError("timeout"),
                asyncio.TimeoutError("timeout"),
            ]

        truefx, swissquote = results[0], results[1]
        quotes: dict[str, dict] = {}

        if isinstance(truefx, dict):
            quotes["truefx"] = truefx
        else:
            logger.warning(f"ForexFeed: TrueFX failed: {truefx}")

        if isinstance(swissquote, dict):
            quotes["swissquote"] = swissquote
        else:
            logger.warning(f"ForexFeed: Swissquote failed: {swissquote}")

        if not quotes:
            if self._last_known_price:
                cached = self._last_known_price.copy()
                cached["cached"] = True
                cached["timestamp"] = f"{cached.get('timestamp', '')} (CACHED)"
                return cached
            return {"error": "ForexFeed: both sources failed"}

        status = "verified" if len(quotes) == 2 else "degraded"
        mids = [q["mid"] for q in quotes.values()]
        bids = [q["bid"] for q in quotes.values()]
        asks = [q["ask"] for q in quotes.values()]

        if len(mids) > 1:
            deviation_pips = (max(mids) - min(mids)) * 10000
        else:
            deviation_pips = 0.0
        high = max(asks)
        low = min(bids)
        spread_pips = (high - low) * 10000

        sources_detail = {
            name: {"bid": q["bid"], "ask": q["ask"], "mid": q["mid"]}
            for name, q in quotes.items()
        }
        result = {
            "symbol": "EUR/USD",
            "price": round(sum(mids) / len(mids), 5),
            "bid": round(sum(bids) / len(bids), 5),
            "ask": round(sum(asks) / len(asks), 5),
            "spread_pips": round(spread_pips, 1),
            "open": round(sum(mids) / len(mids), 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "change": 0.0,
            "change_pct": 0.0,
            "direction": "flat",
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            "source": "forexfeed",
            "verification": {
                "status": status,
                "sources": sources_detail,
                "deviation_pips": round(deviation_pips, 2),
                "threshold_pips": MAX_DEVIATION_PIPS,
            },
        }

        if status == "verified" and deviation_pips > MAX_DEVIATION_PIPS:
            logger.warning(
                f"ForexFeed: sources diverge {deviation_pips:.2f} pips "
                f"(> {MAX_DEVIATION_PIPS} threshold): {quotes}"
            )
            result["verification"]["status"] = "divergent"

        self._last_known_price = result.copy()
        return result

    async def close(self):
        """Close the HTTP session."""
        await self._session.aclose()
