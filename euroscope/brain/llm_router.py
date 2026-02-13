"""
LLM Router — Multi-Provider Failover

Tries multiple LLM providers in order with retry logic.
Chain: DeepSeek → OpenAI → Groq (configurable)
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("euroscope.brain.llm_router")


@dataclass
class LLMProvider:
    """Configuration for a single LLM provider."""
    name: str
    api_key: str
    api_base: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.4

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


class LLMRouter:
    """
    Routes LLM requests through multiple providers with failover.

    Tries providers in order and falls back to the next one on failure.
    Tracks which provider was last used for transparency.
    """

    def __init__(self, providers: list[LLMProvider], max_retries: int = 2):
        self.providers = [p for p in providers if p.is_configured]
        self.max_retries = max_retries
        self._last_provider: str = ""
        self._call_count: int = 0
        self._failure_count: int = 0

    @classmethod
    def from_config(cls, primary_key: str = "", primary_base: str = "",
                    primary_model: str = "", fallback_key: str = "",
                    fallback_base: str = "", fallback_model: str = "") -> "LLMRouter":
        """Create router from configuration values."""
        providers = []

        if primary_key:
            providers.append(LLMProvider(
                name="primary",
                api_key=primary_key,
                api_base=primary_base or "https://api.deepseek.com",
                model=primary_model or "deepseek-chat",
            ))

        if fallback_key:
            providers.append(LLMProvider(
                name="fallback",
                api_key=fallback_key,
                api_base=fallback_base or "https://api.openai.com/v1",
                model=fallback_model or "gpt-4o-mini",
            ))

        return cls(providers)

    @property
    def last_provider(self) -> str:
        return self._last_provider

    @property
    def stats(self) -> dict:
        return {
            "total_calls": self._call_count,
            "failures": self._failure_count,
            "success_rate": round(
                (1 - self._failure_count / max(self._call_count, 1)) * 100, 1
            ),
            "providers_available": len(self.providers),
            "last_provider": self._last_provider,
        }

    async def chat(self, messages: list[dict], temperature: float = None) -> str:
        """
        Send chat completion request, trying providers in order.

        Args:
            messages: list of {"role": ..., "content": ...}
            temperature: override provider default

        Returns:
            LLM response text
        """
        if not self.providers:
            return "⚠️ No LLM providers configured. Set API keys in .env"

        self._call_count += 1
        last_error = None

        for provider in self.providers:
            for attempt in range(self.max_retries + 1):
                try:
                    result = await self._call_provider(provider, messages, temperature)
                    self._last_provider = provider.name
                    return result

                except httpx.HTTPStatusError as e:
                    last_error = e
                    status = e.response.status_code

                    # Don't retry on auth errors — move to next provider
                    if status in (401, 403):
                        logger.warning(f"{provider.name}: Auth failed ({status}), skipping")
                        break

                    # Rate limit — wait and retry
                    if status == 429:
                        wait = min(2 ** attempt * 2, 30)
                        logger.warning(f"{provider.name}: Rate limited, waiting {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    # Server error — retry
                    if status >= 500:
                        wait = 2 ** attempt
                        logger.warning(f"{provider.name}: Server error ({status}), retry in {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    # Other client errors — skip provider
                    logger.error(f"{provider.name}: HTTP {status}")
                    break

                except Exception as e:
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(f"{provider.name}: Error ({e}), retry in {wait}s")
                    if attempt < self.max_retries:
                        await asyncio.sleep(wait)

        # All providers failed
        self._failure_count += 1
        error_msg = str(last_error)[:200] if last_error else "Unknown error"
        logger.error(f"All LLM providers failed: {error_msg}")
        return f"❌ AI unavailable — all providers failed: {error_msg}"

    async def _call_provider(self, provider: LLMProvider,
                             messages: list[dict],
                             temperature: float = None) -> str:
        """Make a single API call to a provider."""
        temp = temperature if temperature is not None else provider.temperature

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{provider.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": provider.model,
                    "messages": messages,
                    "max_tokens": provider.max_tokens,
                    "temperature": temp,
                },
            )
            response.raise_for_status()
            data = response.json()

        reply = data["choices"][0]["message"]["content"]

        # Log usage if available
        usage = data.get("usage", {})
        if usage:
            logger.debug(
                f"{provider.name}: {usage.get('total_tokens', '?')} tokens "
                f"(prompt: {usage.get('prompt_tokens', '?')}, "
                f"completion: {usage.get('completion_tokens', '?')})"
            )

        return reply
