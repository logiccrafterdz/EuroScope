"""
Fundamental Data Provider

Fetches macroeconomic indicators from FRED and ECB that drive EUR/USD:
interest rates, CPI, GDP, bond yields, and rate differentials.
"""

import logging
from datetime import datetime, timedelta, UTC
from typing import Optional

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
    """Fetches key macroeconomic data for EUR/USD analysis."""

    def __init__(self, fred_api_key: str = ""):
        self.fred_api_key = fred_api_key
        self._cache: dict[str, tuple[dict, datetime]] = {}
        self._cache_ttl = timedelta(hours=4)  # Macro data updates infrequently

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

    # ─── FRED Data ───────────────────────────────────────────

    def _fetch_fred_series(self, series_id: str, limit: int = 5) -> list[dict]:
        """Fetch latest observations from a FRED series."""
        if not self.fred_api_key:
            return []

        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(FRED_BASE_URL, params={
                    "series_id": series_id,
                    "api_key": self.fred_api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": limit,
                })
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
            return observations

        except Exception as e:
            logger.error(f"FRED fetch error for {series_id}: {e}")
            return []

    def get_fed_funds_rate(self) -> Optional[dict]:
        """Get the current Federal Funds Rate."""
        cached = self._get_cached("fed_funds_rate")
        if cached:
            return cached

        data = self._fetch_fred_series(FRED_SERIES["fed_funds_rate"], limit=3)
        if data:
            result = {"rate": data[0]["value"], "date": data[0]["date"], "source": "FRED"}
            self._set_cache("fed_funds_rate", result)
            return result
        return None

    def get_us_10y_yield(self) -> Optional[dict]:
        """Get the US 10-Year Treasury yield."""
        cached = self._get_cached("us_10y_treasury")
        if cached:
            return cached

        data = self._fetch_fred_series(FRED_SERIES["us_10y_treasury"], limit=3)
        if data:
            result = {"yield": data[0]["value"], "date": data[0]["date"], "source": "FRED"}
            self._set_cache("us_10y_treasury", result)
            return result
        return None

    def get_us_cpi(self) -> Optional[dict]:
        """Get the latest US CPI reading."""
        cached = self._get_cached("us_cpi")
        if cached:
            return cached

        data = self._fetch_fred_series(FRED_SERIES["us_cpi"], limit=3)
        if len(data) >= 2:
            current = data[0]["value"]
            previous = data[1]["value"]
            yoy_change = round((current - previous) / previous * 100, 2)
            result = {
                "value": current, "previous": previous,
                "yoy_change": yoy_change, "date": data[0]["date"], "source": "FRED",
            }
            self._set_cache("us_cpi", result)
            return result
        return None

    # ─── Eurozone Data (via FRED) ────────────────────────────

    def get_ecb_main_rate(self) -> Optional[dict]:
        """Get the ECB Main Refinancing Rate (from FRED)."""
        cached = self._get_cached("ecb_main_rate")
        if cached:
            return cached

        data = self._fetch_fred_series(FRED_SERIES["ecb_main_rate"], limit=3)
        if data:
            result = {
                "value": data[0]["value"], "name": "ECB Main Refinancing Rate",
                "date": data[0]["date"], "source": "FRED (ECB Data)"
            }
            self._set_cache("ecb_main_rate", result)
            return result
        return None

    def get_ecb_deposit_rate(self) -> Optional[dict]:
        """Get the ECB Deposit Facility Rate (from FRED)."""
        cached = self._get_cached("ecb_deposit_rate")
        if cached:
            return cached

        data = self._fetch_fred_series(FRED_SERIES["ecb_deposit_rate"], limit=3)
        if data:
            result = {
                "value": data[0]["value"], "name": "ECB Deposit Rate",
                "date": data[0]["date"], "source": "FRED (ECB Data)"
            }
            self._set_cache("ecb_deposit_rate", result)
            return result
        return None

    # ─── Derived Metrics ─────────────────────────────────────

    def get_interest_rate_differential(self) -> Optional[dict]:
        """
        Calculate the interest rate differential between Fed and ECB.
        Positive = USD has higher rate (tends to support USD / bearish EUR/USD).
        """
        fed = self.get_fed_funds_rate()
        ecb = self.get_ecb_main_rate()

        if not fed or not ecb:
            return None

        diff = round(fed["rate"] - ecb["value"], 2)
        bias = "USD stronger" if diff > 0 else "EUR stronger" if diff < 0 else "neutral"

        return {
            "fed_rate": fed["rate"],
            "ecb_rate": ecb["value"],
            "differential": diff,
            "bias": bias,
            "interpretation": (
                f"Fed {fed['rate']}% vs ECB {ecb['value']}% → "
                f"Spread: {diff:+.2f}% favoring {'USD' if diff > 0 else 'EUR'}"
            ),
        }

    def get_yield_spread(self) -> Optional[dict]:
        """
        Calculate US 10Y vs German 10Y bond yield spread.
        Positive = higher US yields (supports USD / bearish EUR/USD).
        """
        us_yield = self.get_us_10y_yield()

        # Try FRED for German yields
        german_data = self._fetch_fred_series(FRED_SERIES["german_10y_bund"], limit=3)

        if not us_yield or not german_data:
            return None

        german_yield = german_data[0]["value"]
        spread = round(us_yield["yield"] - german_yield, 2)

        return {
            "us_10y": us_yield["yield"],
            "german_10y": german_yield,
            "spread": spread,
            "interpretation": (
                f"US 10Y {us_yield['yield']}% vs DE 10Y {german_yield}% → "
                f"Spread: {spread:+.2f}% ({'supports USD' if spread > 0 else 'supports EUR'})"
            ),
        }

    # ─── AI Context ──────────────────────────────────────────

    def get_macro_context_for_ai(self) -> str:
        """Get formatted macro summary for AI prompt injection."""
        lines = ["📊 Current Macroeconomic Context (EUR/USD):\n"]

        # Interest rates
        rate_diff = self.get_interest_rate_differential()
        if rate_diff:
            lines.append(f"🏦 Interest Rates: {rate_diff['interpretation']}")
        else:
            lines.append("🏦 Interest Rates: Data unavailable")

        # Bond yields
        yield_spread = self.get_yield_spread()
        if yield_spread:
            lines.append(f"📈 Bond Yields: {yield_spread['interpretation']}")

        # US CPI
        cpi = self.get_us_cpi()
        if cpi:
            lines.append(f"📉 US CPI: {cpi['value']} (YoY: {cpi['yoy_change']}%)")

        # ECB rates
        ecb_deposit = self.get_ecb_deposit_rate()
        if ecb_deposit:
            lines.append(f"🇪🇺 ECB Deposit Rate: {ecb_deposit['value']}%")

        if len(lines) <= 1:
            return "Macroeconomic data currently unavailable (API keys may not be configured)."

        return "\n".join(lines)

    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
