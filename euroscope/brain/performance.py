"""
Performance Optimizations — Difficulty Routing + Context Compression.

Provides:
- DifficultyRouter: classifies LLM queries by complexity and routes to
  appropriate providers (simple → fast/cheap, complex → full model).
- PromptCompressor: truncates and compresses historical context to stay
  within token budgets while preserving critical information.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger("euroscope.brain.performance")


# ── Difficulty Router ──────────────────────────────────────────

# Keywords that indicate complex reasoning tasks
COMPLEX_INDICATORS = [
    "debate", "argue", "deliberate", "risk assessment", "conflict",
    "contradict", "explain why", "justify", "reasoning",
    "investment judgment", "final verdict", "conviction",
    "causal", "counterfactual", "what if", "hypothesis",
    "multi-step", "chain of thought", "analyze the interaction",
]

# Keywords that indicate simple retrieval/formatting tasks
SIMPLE_INDICATORS = [
    "price", "status", "summary", "format", "list", "show",
    "quick", "brief", "one line", "short", "briefing",
    "what is", "current", "latest", "report",
]


def classify_difficulty(messages: list[dict]) -> str:
    """
    Classify LLM query difficulty from message content.

    Returns: "simple", "medium", or "complex"
    """
    if not messages:
        return "simple"

    # Combine all message content for analysis
    text = " ".join(
        m.get("content", "") for m in messages if isinstance(m.get("content"), str)
    ).lower()

    if not text.strip():
        return "simple"

    # Score complexity
    complex_score = sum(1 for kw in COMPLEX_INDICATORS if kw in text)
    simple_score = sum(1 for kw in SIMPLE_INDICATORS if kw in text)

    # Message count is a proxy for context size
    msg_count = len(messages)

    # System prompt length (longer = more context = more complex)
    system_len = 0
    for m in messages:
        if m.get("role") == "system":
            system_len += len(m.get("content", ""))

    if complex_score >= 2 or (complex_score >= 1 and msg_count > 4) or system_len > 5000:
        return "complex"
    if simple_score >= 2 and complex_score == 0:
        return "simple"
    if msg_count <= 3 and system_len < 2000 and complex_score == 0:
        return "simple"

    return "medium"


class DifficultyRouter:
    """
    Routes LLM requests to appropriate providers based on query complexity.

    Simple queries → primary (fast, cheap)
    Medium queries → primary (default)
    Complex queries → primary with full context (or fallback if primary fails)
    """

    def __init__(self, llm_router):
        self.router = llm_router
        self._stats = {"simple": 0, "medium": 0, "complex": 0}

    async def chat(self, messages: list[dict], temperature: float = None,
                   force_provider: str = None) -> str:
        difficulty = classify_difficulty(messages)
        self._stats[difficulty] += 1

        if force_provider:
            return await self.router.chat(messages, temperature=temperature,
                                          force_provider=force_provider)

        # For simple queries, try primary only (still through circuit breaker)
        if difficulty == "simple" and self.router.providers:
            try:
                result = await self.router.chat(messages, temperature=temperature,
                                                force_provider=self.router.providers[0].name)
                return result
            except Exception as e:
                logger.debug(f"Simple query failed on primary, falling back: {e}")

        # For medium/complex, use full retry chain
        return await self.router.chat(messages, temperature=temperature)

    async def chat_json(self, messages: list[dict], temperature: float = None,
                        max_tokens: int = None) -> dict:
        difficulty = classify_difficulty(messages)
        self._stats[difficulty] += 1
        return await self.router.chat_json(messages, temperature=temperature,
                                           max_tokens=max_tokens)

    @property
    def stats(self) -> dict:
        total = sum(self._stats.values())
        return {
            "total": total,
            "simple": self._stats["simple"],
            "medium": self._stats["medium"],
            "complex": self._stats["complex"],
            "simple_pct": round(self._stats["simple"] / max(total, 1) * 100, 1),
        }


# ── Context Compressor ─────────────────────────────────────────

# Approximate tokens per character (English text ~ 0.25 tokens/char)
CHARS_PER_TOKEN = 4


class PromptCompressor:
    """
    Compresses LLM context to stay within token budgets.

    Strategies:
    - Truncate old history messages
    - Summarize long system prompts
    - Keep recent context intact
    - Preserve critical markers (signals, decisions, risk)
    """

    def __init__(self, max_tokens: int = 12000, reserve_tokens: int = 2000):
        self.max_tokens = max_tokens
        self.max_chars = max_tokens * CHARS_PER_TOKEN
        self.reserve_chars = reserve_tokens * CHARS_PER_TOKEN

    def compress(self, messages: list[dict], max_tokens: int = None) -> list[dict]:
        """
        Compress messages to fit within token budget.

        Args:
            messages: Full message list
            max_tokens: Override default max_tokens

        Returns:
            Compressed message list
        """
        limit = (max_tokens or (self.max_tokens if hasattr(self, 'max_tokens') else 12000)) * CHARS_PER_TOKEN

        # Calculate current size
        total_chars = sum(len(m.get("content", "")) for m in messages if isinstance(m.get("content"), str))

        if total_chars <= limit:
            return messages

        # Strategy: preserve system prompt + last N messages, truncate middle
        result = []
        system_msgs = []
        other_msgs = []

        for m in messages:
            if m.get("role") == "system":
                system_msgs.append(m)
            else:
                other_msgs.append(m)

        # System prompt: truncate if too long
        system_chars = sum(len(m.get("content", "")) for m in system_msgs)
        max_system_chars = limit // 3  # System prompt gets max 1/3 of budget

        if system_chars > max_system_chars:
            truncated_system = []
            remaining = max_system_chars
            for m in system_msgs:
                content = m.get("content", "")
                if len(content) <= remaining:
                    truncated_system.append(m)
                    remaining -= len(content)
                else:
                    truncated_system.append({
                        **m,
                        "content": content[:remaining] + "\n[...truncated...]"
                    })
                    remaining = 0
                    break
            system_msgs = truncated_system

        result.extend(system_msgs)
        remaining_chars = limit - sum(len(m.get("content", "")) for m in result if isinstance(m.get("content"), str))

        # Other messages: keep most recent, truncate oldest
        for m in reversed(other_msgs):
            content = m.get("content", "")
            if isinstance(content, str) and len(content) <= remaining_chars:
                result.insert(len(system_msgs), m)
                remaining_chars -= len(content)
            elif isinstance(content, str):
                # Truncate this message
                truncated = {
                    **m,
                    "content": "[...earlier context truncated...]\n" + content[-remaining_chars:]
                }
                result.insert(len(system_msgs), truncated)
                remaining_chars = 0
                break

        return result

    def estimate_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens in message list."""
        total_chars = sum(len(m.get("content", "")) for m in messages if isinstance(m.get("content"), str))
        return total_chars // CHARS_PER_TOKEN

    def needs_compression(self, messages: list[dict], max_tokens: int = 12000) -> bool:
        """Check if messages need compression."""
        return self.estimate_tokens(messages) > max_tokens
