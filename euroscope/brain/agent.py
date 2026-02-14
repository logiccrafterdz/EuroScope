"""
AI Agent — LLM Integration

Connects to OpenRouter/OpenAI for intelligent EUR/USD analysis,
forecasting, and Q&A.
"""

import json
import logging
from typing import Optional

import httpx

from ..config import LLMConfig
from .prompts import SYSTEM_PROMPT, ANALYSIS_PROMPT, FORECAST_PROMPT, QUESTION_PROMPT
from .llm_router import LLMRouter
from .vector_memory import VectorMemory

logger = logging.getLogger("euroscope.brain.agent")


class Agent:
    """LLM-powered EUR/USD expert agent."""

    def __init__(self, config: LLMConfig, router: Optional[LLMRouter] = None,
                 vector_memory: Optional[VectorMemory] = None):
        self.config = config
        self.router = router
        self.vector_memory = vector_memory
        self.conversation_history: list[dict] = []
        self.max_history = 20

    async def chat(self, user_message: str, system_override: str = None) -> str:
        """Send a message to the LLM and get a response."""
        system = system_override or SYSTEM_PROMPT

        # Add vector memory context if available
        if self.vector_memory:
            context = self.vector_memory.get_relevant_context(user_message)
            if context:
                system += f"\n\n### LONG-TERM MEMORY (PAST CONTEXT)\n{context}"

        # Build messages
        messages = [{"role": "system", "content": system}]

        # Add recent conversation history for context
        messages.extend(self.conversation_history[-self.max_history:])
        messages.append({"role": "user", "content": user_message})

        # Use router if available
        if self.router:
            reply = await self.router.chat(messages)
            if not reply.startswith("❌"):
                # Save to history
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": reply})
                # Trim history
                if len(self.conversation_history) > self.max_history * 2:
                    self.conversation_history = self.conversation_history[-self.max_history:]
            return reply

        # Fallback to direct call if no router
        if not self.config.api_key:
            return "⚠️ AI features disabled — no API key configured."

        system = system_override or SYSTEM_PROMPT

        # Build messages
        messages = [{"role": "system", "content": system}]

        # Add recent conversation history for context
        messages.extend(self.conversation_history[-self.max_history:])
        messages.append({"role": "user", "content": user_message})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.config.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.model,
                        "messages": messages,
                        "max_tokens": self.config.max_tokens,
                        "temperature": self.config.temperature,
                    },
                )
                response.raise_for_status()
                data = response.json()

            reply = data["choices"][0]["message"]["content"]

            # Save to history
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": reply})

            # Trim history
            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history:]

            return reply

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.status_code} — {e.response.text[:500]}")
            return f"❌ AI error: {e.response.status_code}"
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return f"❌ AI unavailable: {str(e)[:100]}"

    async def analyze(self, market_data: str, technical_data: str,
                      patterns_data: str, levels_data: str,
                      news_data: str, calendar_context: str) -> str:
        """Generate comprehensive EUR/USD analysis."""
        prompt = ANALYSIS_PROMPT.format(
            market_data=market_data,
            technical_data=technical_data,
            patterns_data=patterns_data,
            levels_data=levels_data,
            news_data=news_data,
            calendar_context=calendar_context,
        )
        return await self.chat(prompt, system_override=SYSTEM_PROMPT)

    async def forecast(self, price_data: str, technical_summary: str,
                       patterns: str, levels: str, news: str,
                       prediction_history: str, timeframe: str = "24 hours") -> str:
        """Generate directional forecast."""
        prompt = FORECAST_PROMPT.format(
            price_data=price_data,
            technical_summary=technical_summary,
            patterns=patterns,
            levels=levels,
            news=news,
            prediction_history=prediction_history,
            timeframe=timeframe,
        )
        return await self.chat(prompt, system_override=SYSTEM_PROMPT)

    async def ask(self, question: str, current_price: str = "N/A",
                  current_bias: str = "N/A", support: str = "N/A",
                  resistance: str = "N/A") -> str:
        """Answer a free-form question about EUR/USD."""
        prompt = QUESTION_PROMPT.format(
            current_price=current_price,
            current_bias=current_bias,
            support=support,
            resistance=resistance,
            question=question,
        )
        return await self.chat(prompt)

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history.clear()
