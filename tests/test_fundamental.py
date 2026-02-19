"""
Tests for euroscope.data.fundamental module.

Uses mock API responses — no real FRED/ECB calls needed.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from euroscope.data.fundamental import FundamentalDataProvider


@pytest.fixture
def provider():
    """Provider with a dummy API key."""
    return FundamentalDataProvider(fred_api_key="test_key_123")


@pytest.fixture
def provider_no_key():
    """Provider without API key."""
    return FundamentalDataProvider(fred_api_key="")


class TestFredFetching:
    """Test FRED data fetching with mocked responses."""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty(self, provider_no_key):
        result = await provider_no_key._fetch_series("FEDFUNDS")
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_fred_success(self, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "observations": [
                {"date": "2025-01-01", "value": "5.33"},
                {"date": "2024-12-01", "value": "5.33"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        provider.session = MagicMock()
        provider.session.get = AsyncMock(return_value=mock_resp)

        data = await provider._fetch_series("FEDFUNDS")
        assert len(data) == 2
        assert data[0]["value"] == 5.33
        assert data[0]["date"] == "2025-01-01"

    @pytest.mark.asyncio
    async def test_fetch_fred_skips_missing_values(self, provider):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "observations": [
                {"date": "2025-01-01", "value": "."},  # missing
                {"date": "2024-12-01", "value": "5.33"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        provider.session = MagicMock()
        provider.session.get = AsyncMock(return_value=mock_resp)

        data = await provider._fetch_series("FEDFUNDS")
        assert len(data) == 1  # Missing "." was skipped

    @pytest.mark.asyncio
    async def test_fetch_fred_error_returns_empty(self, provider):
        provider.session = MagicMock()
        provider.session.get = AsyncMock(side_effect=Exception("Network error"))

        data = await provider._fetch_series("FEDFUNDS")
        assert data == []


class TestCaching:
    """Test the caching mechanism."""

    def test_cache_stores_and_retrieves(self, provider):
        provider._set_cache("test_key", {"rate": 5.0})
        result = provider._get_cached("test_key")
        assert result is not None
        assert result["rate"] == 5.0

    def test_cache_miss(self, provider):
        result = provider._get_cached("nonexistent")
        assert result is None

    def test_clear_cache(self, provider):
        provider._set_cache("test", {"value": 1})
        provider.clear_cache()
        assert provider._get_cached("test") is None


class TestDerivedMetrics:
    """Test interest rate differential and yield spread calculations."""

    @pytest.mark.asyncio
    async def test_interest_rate_differential(self, provider):
        # Mock internal methods
        provider.get_fed_funds_rate = AsyncMock(return_value={"rate": 5.33})
        provider.get_ecb_main_rate = AsyncMock(return_value={"value": 4.50})

        result = await provider.get_interest_rate_differential()
        assert result is not None
        assert result["differential"] == 0.83
        assert result["bias"] == "USD stronger"
        assert "Fed 5.33%" in result["interpretation"]
        assert "ECB 4.5%" in result["interpretation"]

    @pytest.mark.asyncio
    async def test_interest_rate_differential_eur_stronger(self, provider):
        provider.get_fed_funds_rate = AsyncMock(return_value={"rate": 3.0})
        provider.get_ecb_main_rate = AsyncMock(return_value={"value": 4.5})

        result = await provider.get_interest_rate_differential()
        assert result["differential"] == -1.5
        assert result["bias"] == "EUR stronger"

    @pytest.mark.asyncio
    async def test_interest_rate_diff_missing_data(self, provider):
        provider.get_fed_funds_rate = AsyncMock(return_value=None)
        provider.get_ecb_main_rate = AsyncMock(return_value={"value": 4.5})

        result = await provider.get_interest_rate_differential()
        assert result is None

    @pytest.mark.asyncio
    async def test_yield_spread(self, provider):
        provider.get_us_10y_yield = AsyncMock(return_value={"yield": 4.5})
        provider._fetch_series = AsyncMock(return_value=[{"value": 2.3, "date": "2025-01-01"}])

        result = await provider.get_yield_spread()
        assert result is not None
        assert result["spread"] == 2.2
        assert "supports USD" in result["interpretation"]


class TestAIContext:
    """Test AI context generation."""

    @pytest.mark.asyncio
    async def test_context_with_data(self, provider):
        provider.get_interest_rate_differential = AsyncMock(return_value={
            "interpretation": "Fed 5.33% vs ECB 4.50% → Spread: +0.83% favoring USD"
        })
        provider.get_yield_spread = AsyncMock(return_value={
            "interpretation": "US 10Y 4.5% vs DE 10Y 2.3% → Spread: +2.20% (supports USD)"
        })
        provider.get_us_cpi = AsyncMock(return_value={
            "value": 310.0, "yoy_change": 3.2
        })
        provider.get_ecb_deposit_rate = AsyncMock(return_value={
            "value": 3.75
        })

        context = await provider.get_macro_context_for_ai()
        assert "Interest Rates" in context
        assert "Bond Yields" in context
        assert "CPI" in context
        assert "ECB Deposit Rate" in context

    @pytest.mark.asyncio
    async def test_context_without_data(self, provider_no_key):
        context = await provider_no_key.get_macro_context_for_ai()
        assert "unavailable" in context.lower()
