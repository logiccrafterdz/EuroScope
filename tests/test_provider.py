import asyncio
from unittest.mock import AsyncMock

import pytest

from euroscope.data.provider import PriceProvider, TIMEFRAMES


@pytest.mark.asyncio
async def test_get_multi_timeframe_concurrent():
    provider = PriceProvider()

    async def fake_get_candles(timeframe: str, count: int = 100):
        return timeframe

    provider.get_candles = AsyncMock(side_effect=fake_get_candles)
    result = await provider.get_multi_timeframe()

    assert set(result.keys()) == set(TIMEFRAMES.keys())
    for tf in TIMEFRAMES:
        assert result[tf] == tf


@pytest.mark.asyncio
async def test_get_multi_timeframe_timeout(monkeypatch):
    provider = PriceProvider()
    provider.get_candles = AsyncMock(side_effect=lambda tf, count=100: asyncio.sleep(60))

    original_wait_for = asyncio.wait_for

    async def fake_wait_for(awaitable, timeout):
        return await original_wait_for(awaitable, timeout=0)

    monkeypatch.setattr("euroscope.data.provider.asyncio.wait_for", fake_wait_for)
    result = await provider.get_multi_timeframe()

    assert result == {}
