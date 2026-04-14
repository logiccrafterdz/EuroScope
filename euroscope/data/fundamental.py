"""
Fundamental Data Provider

Fetches macroeconomic indicators from FRED and ECB that drive EUR/USD:
interest rates, CPI, GDP, bond yields, and rate differentials.
"""

import logging
import asyncio
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger("euroscope.data.fundamental")

# FRED series IDs for key indicators
FRED_SERIES = {
    "fed_funds_rate": "FEDFUNDS",        # Federal Funds Effective Rate
    "us_cpi": "CPIAUCSL",                # US Consumer Price Index
    "us_10y_treasury": "DGS10",          # US 10-Year Treasury Yield
    "german_10y_bund": "IRLTLT01DEM156N", # Germany 10Y Government Bond Yield
    "us_gdp": "GDP",                      # US Gross Domestic Product
    "us_unemployment": "UNRATE",          # US Unemployment Rate
    "eur_usd_rate": "DEXUSEU",           # EUR/USD Exchange Rate (FRED)
    "ecb_main_rate": "ECBMRRFR",         # ECB Main Refinancing Operations Rate
    "ecb_deposit_rate": "ECBDFR",        # ECB Deposit Facility Rate
    "eurozone_hicp": "CP0000EZCCM086NEST", # Euro Area HICP (CPI)
}

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FundamentalDataProvider:
    """Fetches key macroeconomic data for EUR/USD analysis with high resilience."""

    def __init__(self, fred_api_key: str = ""):
        self.fred_api_key = fred_api_key
        self._cache: dict[str, tuple[dict, datetime]] = {}
        self._cache_ttl = timedelta(hours=24)  # Extended for fallback
        self.session = httpx.AsyncClient(timeout=10)
        from euroscope.utils.resilience import AsyncCircuitBreaker
        self.breaker = AsyncCircuitBreaker(exceptions=(httpx.HTTPError, asyncio.TimeoutError), failure_threshold=3, recovery_timeout=120)
        self.last_quality = "complete"
        self.warnings = []

    def _get_cached(self, key: str) -> Optional[dict]:
        """Return cached data if still valid."""
        if key in self._cache:
            data, cached_at = self._cache[key]
            if datetime.now(UTC) - cached_at < self._cache_ttl:
                return data
        return None

    def _set_cache(self, key: str, data: dict):
        """Store data in cache."""
        self._cache[key] = (data, datetime.now(UTC))

    # ─── Data Fetching Logic ─────────────────────────────────

    async def _fetch_series(self, series_id: str, limit: int = 5) -> List[Dict]:
        """Fetch latest observations with retry logic and caching fallback."""
        if not self.fred_api_key:
            return []

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = await self.breaker.call(
                    self.session.get,
                    FRED_BASE_URL,
                    params={
                        "series_id": series_id,
                        "api_key": self.fred_api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": limit,
                    }
                )
                resp.raise_for_status()
                data = resp.json()

                observations = []
                for obs in data.get("observations", []):
                    value = obs.get("value", ".")
                    if value != ".":
                        observations.append({
                            "date": obs["date"],
                            "value": float(value),
                        })
                
                # Success!
                return observations

            except Exception as e:
                from euroscope.utils.resilience import CircuitBreakerOpenException
                if isinstance(e, CircuitBreakerOpenException):
                    logger.warning(f"FRED circuit breaker OPEN for {series_id}")
                    break
                logger.warning(f"Fetch attempt {attempt+1} failed for {series_id}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"All retries failed for {series_id}. Attempting cache fallback.")
        
        return []

    async def _get_series_data(self, key: str, series_id: str, field_name: str = "value") -> Optional[Dict]:
        """Unified fetcher with caching and quality tracking."""
        data = await self._fetch_series(series_id)
        
        if data:
            result = {
                field_name: data[0]["value"],
                "date": data[0]["date"],
                "source": "FRED",
                "quality": "reliable"
            }
            # Special logic for CPI (needs 2 points)
            if key in ("us_cpi", "eu_cpi") and len(data) >= 2:
                current = data[0]["value"]
                previous = data[1]["value"]
                result["previous"] = previous
                result["yoy_change"] = round((current - previous) / previous * 100, 2)
                
            self._set_cache(key, result)
            return result
        
        # Fallback to cache
        cached = self._get_cached(key)
        if cached:
            cached["quality"] = "cached"
            self.warnings.append(f"Using cached data for {key} (stale)")
            return cached
            
        self.warnings.append(f"Data unavailable for {key}")
        return None

    async def get_fed_funds_rate(self) -> Optional[Dict]:
        """Get the current Federal Funds Rate."""
        return await self._get_series_data("fed_funds_rate", FRED_SERIES["fed_funds_rate"], "rate")

    async def get_us_10y_yield(self) -> Optional[Dict]:
        """Get the US 10-Year Treasury yield."""
        return await self._get_series_data("us_10y_treasury", FRED_SERIES["us_10y_treasury"], "yield")

    async def get_us_cpi(self) -> Optional[Dict]:
        """Get the latest US CPI reading."""
        return await self._get_series_data("us_cpi", FRED_SERIES["us_cpi"])

    async def get_eu_cpi(self) -> Optional[Dict]:
        """Get the latest Eurozone HICP (CPI) reading."""
        return await self._get_series_data("eu_cpi", FRED_SERIES["eurozone_hicp"])

    async def get_ecb_main_rate(self) -> Optional[Dict]:
        """Get the ECB Main Refinancing Rate."""
        return await self._get_series_data("ecb_main_rate", FRED_SERIES["ecb_main_rate"])

    async def get_ecb_deposit_rate(self) -> Optional[Dict]:
        """Get the ECB Deposit Facility Rate."""
        return await self._get_series_data("ecb_deposit_rate", FRED_SERIES["ecb_deposit_rate"])

    # ─── Derived Metrics ─────────────────────────────────────

    async def get_interest_rate_differential(self) -> Optional[Dict]:
        """Calculate the interest rate differential and its 90-day trend."""
        fed = await self.get_fed_funds_rate()
        ecb = await self.get_ecb_main_rate()

        if not fed or not ecb:
            return None

        current_fed = fed["rate"]
        current_ecb = ecb["value"]
        current_diff = round(current_fed - current_ecb, 2)
        
        # ----- Trend Calculation -----
        # Fetch up to 90 days (roughly 60-65 trading days, but FRED drops weekends, so let's get 65 points)
        trend = "neutral"
        try:
            fed_hist = await self._fetch_series(FRED_SERIES["fed_funds_rate"], limit=65)
            ecb_hist = await self._fetch_series(FRED_SERIES["ecb_main_rate"], limit=65)
            
            if fed_hist and ecb_hist and len(fed_hist) > 10 and len(ecb_hist) > 10:
                # Simple average of the historical observations
                avg_fed = sum(x["value"] for x in fed_hist) / len(fed_hist)
                avg_ecb = sum(x["value"] for x in ecb_hist) / len(ecb_hist)
                historical_diff = avg_fed - avg_ecb
                
                # If the current differential is significantly different from the 90-day avg, there's a trend
                if current_diff > historical_diff + 0.10:
                    trend = "widening_for_usd"
                elif current_diff < historical_diff - 0.10:
                    trend = "narrowing_for_eur"
                else:
                    trend = "stable"
        except Exception as e:
            logger.warning(f"Failed to calculate rate differential trend: {e}")

        bias = "USD stronger" if current_diff > 0 else "EUR stronger" if current_diff < 0 else "neutral"

        return {
            "fed_rate": current_fed,
            "ecb_rate": current_ecb,
            "differential": current_diff,
            "trend": trend,
            "bias": bias,
            "interpretation": (
                f"Fed {current_fed}% vs ECB {current_ecb}% → "
                f"Spread: {current_diff:+.2f}% favoring {'USD' if current_diff > 0 else 'EUR'} (Trend: {trend})"
            ),
        }

    async def get_yield_spread(self) -> Optional[Dict]:
        """Calculate US 10Y vs German 10Y bond yield spread."""
        us_yield = await self.get_us_10y_yield()
        
        # Proxy or direct fetch for German yields
        german_data = await self._fetch_series(FRED_SERIES["german_10y_bund"])
        
        if not us_yield or not german_data:
            # Try cache for yield spread
            cached = self._get_cached("yield_spread")
            if cached: return cached
            return None

        german_yield = german_data[0]["value"]
        spread = round(us_yield["yield"] - german_yield, 2)

        result = {
            "us_10y": us_yield["yield"],
            "german_10y": german_yield,
            "spread": spread,
            "interpretation": (
                f"US 10Y {us_yield['yield']}% vs DE 10Y {german_yield}% → "
                f"Spread: {spread:+.2f}% ({'supports USD' if spread > 0 else 'supports EUR'})"
            ),
        }
        self._set_cache("yield_spread", result)
        return result

    # ─── AI Context ──────────────────────────────────────────

    async def get_macro_context_for_ai(self) -> str:
        """Get formatted macro summary."""
        lines = ["📊 Current Macroeconomic Context (EUR/USD):\n"]

        rate_diff = await self.get_interest_rate_differential()
        if rate_diff:
            lines.append(f"🏦 Interest Rates: {rate_diff['interpretation']}")
        else:
            lines.append("🏦 Interest Rates: Data unavailable")

        yield_spread = await self.get_yield_spread()
        if yield_spread:
            lines.append(f"📈 Bond Yields: {yield_spread['interpretation']}")

        cpi = await self.get_us_cpi()
        if cpi:
            lines.append(f"📉 US CPI: {cpi['value']} (YoY: {cpi['yoy_change']}%)")

        ecb_deposit = await self.get_ecb_deposit_rate()
        if ecb_deposit:
            lines.append(f"🇪🇺 ECB Deposit Rate: {ecb_deposit['value']}%")

        if len(lines) <= 1:
            return "Macroeconomic data currently unavailable."

        return "\n".join(lines)

    async def fetch_complete_macro_data(self) -> Dict[str, Any]:
        """
        Fetches all macro data and returns with quality flags.
        Phase 2 implementation.
        """
        self.warnings = []
        fed = await self.get_fed_funds_rate()
        ecb = await self.get_ecb_main_rate()
        us_cpi = await self.get_us_cpi()
        eu_cpi = await self.get_eu_cpi()
        yields = await self.get_yield_spread()
        
        # Determine quality
        us_ok = all(x is not None for x in [fed, us_cpi])
        eu_ok = all(x is not None for x in [ecb, eu_cpi])
        
        quality = "complete"
        if not us_ok and not eu_ok: quality = "minimal"
        elif not us_ok: quality = "partial_us"
        elif not eu_ok: quality = "partial_eu"
        
        return {
            "us_data": {"fed": fed, "cpi": us_cpi},
            "eu_data": {"ecb": ecb, "cpi": eu_cpi, "yield_spread": yields},
            "quality": quality,
            "warnings": list(set(self.warnings))
        }

    async def close(self):
        """Close the httpx session."""
        await self.session.aclose()

    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
