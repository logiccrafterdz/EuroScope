"""
Tests for the verified ForexFeed provider (TrueFX + Swissquote)
and its integration into MultiSourceProvider.
"""

import asyncio

import httpx
import pandas as pd
import pytest

from euroscope.data.forexfeed import ForexFeedProvider
from euroscope.data.multi_provider import MultiSourceProvider

TRUEFX_CSV = (
    "EUR/USD,1785510452836,1.15,006,1.15,007,1.14548,1.15343,1.15263\r\n"
    "GBP/USD,1785510452836,1.26,991,1.26,996,1.26100,1.26900,1.26980\r\n"
)

SWISSQUOTE_JSON = [
    {
        "topo": {"platform": "SwissquoteCapitalMarkets", "server": "Live7"},
        "spreadProfilePrices": [
            {"spreadProfile": "premium", "bidSpread": 0.65, "askSpread": 0.65,
             "bid": 1.15033, "ask": 1.15042},
        ],
    }
]


def _provider_with_handler(handler):
    """Build a ForexFeedProvider whose session uses the given handler."""
    provider = ForexFeedProvider()
    transport = httpx.MockTransport(handler)
    provider._session = httpx.AsyncClient(
        transport=transport,
        timeout=6.0,
        follow_redirects=True,
    )
    return provider


def _text_response(url, text, status=200):
    return httpx.Response(status, text=text)


def _json_response(url, data, status=200):
    return httpx.Response(status, json=data)


def test_truefx_csv_parsing():
    async def handler(request: httpx.Request) -> httpx.Response:
        if "webrates.truefx.com" in str(request.url):
            return _text_response(str(request.url), TRUEFX_CSV)
        return _json_response(str(request.url), SWISSQUOTE_JSON)

    async def run():
        provider = _provider_with_handler(handler)
        try:
            quote = await provider._truefx()
            assert quote["bid"] == pytest.approx(1.15006)
            assert quote["ask"] == pytest.approx(1.15007)
            assert quote["mid"] == pytest.approx(1.150065)
        finally:
            await provider.close()

    asyncio.run(run())


def test_swissquote_parsing():
    async def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(str(request.url), SWISSQUOTE_JSON)

    async def run():
        provider = _provider_with_handler(handler)
        try:
            quote = await provider._swissquote()
            assert quote["bid"] == pytest.approx(1.15033)
            assert quote["ask"] == pytest.approx(1.15042)
        finally:
            await provider.close()

    asyncio.run(run())


def test_verified_consensus_price():
    async def handler(request: httpx.Request) -> httpx.Response:
        if "webrates.truefx.com" in str(request.url):
            return _text_response(str(request.url), TRUEFX_CSV)
        return _json_response(str(request.url), SWISSQUOTE_JSON)

    async def run():
        provider = _provider_with_handler(handler)
        try:
            result = await provider.get_price()
            assert "error" not in result
            assert result["source"] == "forexfeed"
            expected = (1.150065 + 1.150375) / 2
            assert result["price"] == pytest.approx(expected, abs=1e-5)
            assert result["verification"]["status"] == "verified"
            assert set(result["verification"]["sources"]) == {
                "truefx",
                "swissquote",
            }
            assert result["verification"]["deviation_pips"] < 5.0
        finally:
            await provider.close()

    asyncio.run(run())


def test_divergent_sources_flagged():
    divergent_swiss = [{
        "topo": {"platform": "SwissquoteCapitalMarkets", "server": "Live7"},
        "spreadProfilePrices": [
            {"spreadProfile": "premium", "bidSpread": 0.65, "askSpread": 0.65,
             "bid": 1.15550, "ask": 1.15560},
        ],
    }]

    async def handler(request: httpx.Request) -> httpx.Response:
        if "webrates.truefx.com" in str(request.url):
            return _text_response(str(request.url), TRUEFX_CSV)
        return _json_response(str(request.url), divergent_swiss)

    async def run():
        provider = _provider_with_handler(handler)
        try:
            result = await provider.get_price()
            assert result["verification"]["status"] == "divergent"
            assert result["verification"]["deviation_pips"] > 50
        finally:
            await provider.close()

    asyncio.run(run())


def test_degraded_when_one_source_fails():
    async def handler(request: httpx.Request) -> httpx.Response:
        if "webrates.truefx.com" in str(request.url):
            return httpx.Response(500)
        return _json_response(str(request.url), SWISSQUOTE_JSON)

    async def run():
        provider = _provider_with_handler(handler)
        try:
            result = await provider.get_price()
            assert "error" not in result
            assert result["verification"]["status"] == "degraded"
            assert list(result["verification"]["sources"]) == ["swissquote"]
            assert result["price"] == pytest.approx(1.150375, abs=1e-5)
        finally:
            await provider.close()

    asyncio.run(run())


def test_both_sources_fail_returns_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    async def run():
        provider = _provider_with_handler(handler)
        try:
            result = await provider.get_price()
            assert "error" in result
        finally:
            await provider.close()

    asyncio.run(run())


def test_cached_price_used_when_sources_down():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    async def run():
        provider = _provider_with_handler(handler)
        provider._last_known_price = {"price": 1.1501, "source": "forexfeed",
                                      "timestamp": "2026-07-31 16:00 UTC"}
        try:
            result = await provider.get_price()
            assert "error" not in result
            assert result["cached"] is True
        finally:
            await provider.close()

    asyncio.run(run())


def test_multi_provider_prefers_forexfeed():
    async def run():
        provider = MultiSourceProvider()
        try:
            provider.forexfeed.get_price = _fake_forexfeed_ok
            provider.biquote.get_price = _fake_biquote_ok
            result = await provider.get_price()
            assert result["source"] == "forexfeed"
            assert result["price"] == 1.1501
            assert result["verification"]["status"] == "verified"
        finally:
            provider.forexfeed.close = _noop
            provider.biquote.close = _noop
            await provider.close()

    asyncio.run(run())


def test_multi_provider_falls_back_when_forexfeed_down():
    async def run():
        provider = MultiSourceProvider()
        try:
            provider.forexfeed.get_price = _fake_forexfeed_err
            provider.biquote.get_price = _fake_biquote_ok
            result = await provider.get_price()
            assert result["source"] == "biquote"
        finally:
            provider.forexfeed.close = _noop
            provider.biquote.close = _noop
            await provider.close()

    asyncio.run(run())


def test_fetch_candles_hard_timeout():
    async def hang():
        await asyncio.sleep(60)

    async def run():
        provider = MultiSourceProvider()
        try:
            started = asyncio.get_running_loop().time()
            df = await provider._fetch_candles(hang(), "hangy", timeout=0.2)
            elapsed = asyncio.get_running_loop().time() - started
            assert df is None
            assert elapsed < 5.0
        finally:
            await provider.close()

    asyncio.run(run())


def test_fetch_candles_passes_data_through():
    df = pd.DataFrame({"Open": [1.15], "High": [1.151], "Low": [1.149],
                       "Close": [1.1505], "Volume": [100]})

    async def run():
        provider = MultiSourceProvider()
        try:
            async def ok():
                return df
            out = await provider._fetch_candles(ok(), "okay", timeout=5.0)
            assert out is not None
            assert not out.empty
        finally:
            await provider.close()

    asyncio.run(run())


# --- fakes -----------------------------------------------------------------

async def _fake_forexfeed_ok():
    return {
        "symbol": "EUR/USD", "price": 1.1501, "bid": 1.15005, "ask": 1.15015,
        "spread_pips": 1.0, "open": 1.1501, "high": 1.15015, "low": 1.15005,
        "change": 0.0, "change_pct": 0.0, "direction": "flat",
        "timestamp": "2026-07-31 16:00 UTC", "source": "forexfeed",
        "verification": {"status": "verified", "sources": {},
                         "deviation_pips": 0.5, "threshold_pips": 5.0},
    }


async def _fake_forexfeed_err():
    return {"error": "ForexFeed: both sources failed"}


async def _fake_biquote_ok():
    return {"symbol": "EUR/USD", "price": 1.1499, "bid": 1.1498, "ask": 1.1500,
            "spread_pips": 2.0, "open": 1.1499, "high": 1.15, "low": 1.1498,
            "change": 0.0, "change_pct": 0.0, "direction": "flat",
            "timestamp": "2026-07-31 16:00 UTC", "source": "biquote"}


async def _noop():
    return None
