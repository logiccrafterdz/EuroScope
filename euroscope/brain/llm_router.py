"""
LLM Router — Multi-Provider Failover

Tries multiple LLM providers in order with retry logic.
Chain: DeepSeek → OpenAI → Groq (configurable)
"""

import asyncio
import json
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
        self._warned_identical_keys: bool = False

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

    # ─── Shared retry logic ──────────────────────────────────

    async def _retry_with_fallback(self, call_fn, fail_result):
        """
        Shared retry + fallback logic for all provider call methods.

        Args:
            call_fn: async callable(provider) -> result
            fail_result: value to return when all providers fail
        """
        if not self._warned_identical_keys and len(self.providers) >= 2:
            if self.providers[0].api_key and self.providers[0].api_key == self.providers[1].api_key:
                logger.warning("Fallback key identical to primary key — true redundancy disabled")
                self._warned_identical_keys = True

        last_error = None

        for provider in self.providers:
            for attempt in range(self.max_retries + 1):
                try:
                    result = await call_fn(provider)
                    self._last_provider = provider.name
                    return result

                except httpx.HTTPStatusError as e:
                    last_error = e
                    status = e.response.status_code
                    error_preview = ""
                    try:
                        error_preview = e.response.text[:200]
                    except Exception:
                        error_preview = ""

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
                    if status == 400 and provider.name == "primary" and attempt < self.max_retries:
                        wait = 2 ** attempt
                        logger.warning(f"{provider.name}: HTTP {status}, retry in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    if error_preview:
                        logger.error(f"{provider.name}: HTTP {status} — {error_preview}")
                    else:
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
        if isinstance(last_error, httpx.HTTPStatusError):
            status = last_error.response.status_code
            if status in (401, 403):
                error_msg = "Authentication failed (401/403). Check provider API keys."
            else:
                error_msg = str(last_error)[:200]
        else:
            error_msg = str(last_error)[:200] if last_error else "Unknown error"
        logger.error(f"All LLM providers failed: {error_msg}")
        return fail_result(error_msg)

    # ─── Public API ──────────────────────────────────────────

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

        async def call_fn(provider):
            return await self._call_provider(provider, messages, temperature)

        return await self._retry_with_fallback(
            call_fn,
            lambda err: f"❌ AI unavailable — all providers failed: {err}",
        )

    async def chat_with_functions(
        self,
        messages: list[dict],
        functions: list[dict] = None,
        function_call: str = "auto",
        temperature: float = None,
        max_tokens: int = None,
    ) -> dict:
        if not self.providers:
            return {"content": "⚠️ No LLM providers configured. Set API keys in .env", "function_calls": []}

        self._call_count += 1
        if not functions:
            from .function_schema import get_all_function_schemas

            functions = get_all_function_schemas()

        async def call_fn(provider):
            return await self._call_provider_payload(
                provider=provider,
                messages=messages,
                functions=functions,
                function_call=function_call,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        response = await self._retry_with_fallback(
            call_fn,
            lambda err: {"choices": [{"message": {"content": f"❌ AI unavailable — all providers failed: {err}"}}]},
        )

        message = response.get("choices", [{}])[0].get("message", {}) if isinstance(response, dict) else {}
        content = message.get("content")
        function_calls = []

        function_call_response = message.get("function_call")
        if function_call_response:
            args = function_call_response.get("arguments", "{}")
            try:
                parsed_args = json.loads(args) if isinstance(args, str) else args
            except Exception:
                parsed_args = {}
            function_calls.append({
                "name": function_call_response.get("name"),
                "arguments": parsed_args,
            })

        tool_calls = message.get("tool_calls") or []
        for tool_call in tool_calls:
            func = tool_call.get("function", {})
            args = func.get("arguments", "{}")
            try:
                parsed_args = json.loads(args) if isinstance(args, str) else args
            except Exception:
                parsed_args = {}
            function_calls.append({
                "id": tool_call.get("id"),
                "name": func.get("name"),
                "arguments": parsed_args,
            })

        return {"content": content, "function_calls": function_calls, "raw_message": message}

    # ─── Provider call methods ───────────────────────────────

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
        self._log_usage(provider.name, data)
        return reply

    async def _call_provider_payload(
        self,
        provider: LLMProvider,
        messages: list[dict],
        functions: list[dict],
        function_call: str,
        temperature: float = None,
        max_tokens: int = None,
    ) -> dict:
        temp = temperature if temperature is not None else provider.temperature
        payload = {
            "model": provider.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else provider.max_tokens,
            "temperature": temp,
        }
        if functions:
            payload["functions"] = functions
            payload["function_call"] = function_call

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                response = await client.post(
                    f"{provider.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {provider.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400 and functions:
                    tools_payload = {
                        "model": provider.model,
                        "messages": messages,
                        "max_tokens": max_tokens if max_tokens is not None else provider.max_tokens,
                        "temperature": temp,
                        "tools": [{"type": "function", "function": f} for f in functions],
                    }
                    if function_call is not None:
                        tools_payload["tool_choice"] = function_call
                    response = await client.post(
                        f"{provider.api_base}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {provider.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=tools_payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                else:
                    raise

        self._log_usage(provider.name, data)
        return data

    @staticmethod
    def _log_usage(provider_name: str, data: dict):
        """Log token usage if available."""
        usage = data.get("usage", {})
        if usage:
            logger.debug(
                f"{provider_name}: {usage.get('total_tokens', '?')} tokens "
                f"(prompt: {usage.get('prompt_tokens', '?')}, "
                f"completion: {usage.get('completion_tokens', '?')})"
            )
