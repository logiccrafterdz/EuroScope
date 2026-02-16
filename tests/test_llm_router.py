"""
Tests for LLM Router failover logic.
"""

import logging
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from euroscope.brain.llm_router import LLMRouter, LLMProvider


@pytest.fixture
def mock_providers():
    return [
        LLMProvider(name="primary", api_key="key1",
                    api_base="https://api.primary.com", model="model-1"),
        LLMProvider(name="fallback", api_key="key2",
                    api_base="https://api.fallback.com", model="model-2"),
    ]


@pytest.fixture
def router(mock_providers):
    return LLMRouter(mock_providers, max_retries=1)


class TestLLMProvider:

    def test_is_configured_with_key(self):
        p = LLMProvider(name="test", api_key="key", api_base="url", model="m")
        assert p.is_configured is True

    def test_not_configured_without_key(self):
        p = LLMProvider(name="test", api_key="", api_base="url", model="m")
        assert p.is_configured is False


class TestLLMRouter:

    def test_no_providers(self):
        router = LLMRouter([])
        assert router.providers == []

    def test_filters_unconfigured(self):
        providers = [
            LLMProvider(name="good", api_key="key", api_base="url", model="m"),
            LLMProvider(name="empty", api_key="", api_base="url", model="m"),
        ]
        router = LLMRouter(providers)
        assert len(router.providers) == 1

    def test_from_config(self):
        router = LLMRouter.from_config(
            primary_key="pk", primary_base="pb", primary_model="pm",
            fallback_key="fk",
        )
        assert len(router.providers) == 2

    def test_from_config_no_keys(self):
        router = LLMRouter.from_config()
        assert len(router.providers) == 0

    def test_stats_initial(self, router):
        stats = router.stats
        assert stats["total_calls"] == 0
        assert stats["failures"] == 0
        assert stats["providers_available"] == 2


class TestLLMRouterFailover:

    @pytest.mark.asyncio
    async def test_primary_success(self, router):
        router._call_provider = AsyncMock(return_value="Hello from primary")
        result = await router.chat([{"role": "user", "content": "test"}])
        assert result == "Hello from primary"
        assert router.last_provider == "primary"

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, router):
        call_count = 0
        keys_used = []

        async def mock_call(provider, messages, temperature=None):
            nonlocal call_count
            call_count += 1
            keys_used.append(provider.api_key)
            if provider.name == "primary":
                raise Exception("Primary down")
            return "Hello from fallback"

        router._call_provider = mock_call
        result = await router.chat([{"role": "user", "content": "test"}])
        assert result == "Hello from fallback"
        assert router.last_provider == "fallback"
        assert keys_used[0] == "key1"
        assert keys_used[-1] == "key2"
        assert keys_used.count("key2") == 1

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, router):
        async def mock_fail(provider, messages, temperature=None):
            raise Exception(f"{provider.name} error")

        router._call_provider = mock_fail
        result = await router.chat([{"role": "user", "content": "test"}])
        assert "unavailable" in result or "failed" in result
        assert router.stats["failures"] == 1

    @pytest.mark.asyncio
    async def test_no_providers_message(self):
        router = LLMRouter([])
        result = await router.chat([{"role": "user", "content": "test"}])
        assert "No LLM providers" in result

    @pytest.mark.asyncio
    async def test_call_count_tracking(self, router):
        router._call_provider = AsyncMock(return_value="ok")
        await router.chat([{"role": "user", "content": "1"}])
        await router.chat([{"role": "user", "content": "2"}])
        assert router.stats["total_calls"] == 2

    @pytest.mark.asyncio
    async def test_fallback_with_identical_keys_logs_warning(self, caplog):
        providers = [
            LLMProvider(name="primary", api_key="same-key",
                        api_base="https://api.primary.com", model="model-1"),
            LLMProvider(name="fallback", api_key="same-key",
                        api_base="https://api.fallback.com", model="model-2"),
        ]
        router = LLMRouter(providers)
        router._call_provider = AsyncMock(return_value="ok")
        with caplog.at_level(logging.WARNING, logger="euroscope.brain.llm_router"):
            await router.chat([{"role": "user", "content": "test"}])
        assert "Fallback key identical to primary key" in caplog.text
