"""
LLM Cost Tracker — Token counting and daily budget control.

Tracks API usage per session and per day, with configurable budget
caps and circuit breakers for runaway ReAct loops.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("euroscope.brain.cost_tracker")

# Approximate pricing per 1M tokens (USD) — OpenRouter / OpenAI
MODEL_PRICING = {
    # Format: (prompt_cost_per_1M, completion_cost_per_1M)
    "default": (1.0, 2.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "gpt-3.5-turbo": (0.50, 1.50),
    "claude-3-haiku": (0.25, 1.25),
    "claude-3-sonnet": (3.0, 15.0),
    "claude-3-opus": (15.0, 75.0),
    "deepseek-chat": (0.14, 0.28),
    "mistral-large": (2.0, 6.0),
}


@dataclass
class CallRecord:
    """A single LLM API call record."""
    timestamp: float
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float


@dataclass
class CostTracker:
    """
    Tracks LLM API usage and enforces budget limits.
    
    Features:
    - Per-call token tracking
    - Daily budget cap with throttling
    - Per-loop token circuit breaker
    - Cost estimation based on model pricing
    """
    daily_budget_usd: float = 5.0
    loop_token_limit: int = 10_000
    
    _calls: list = field(default_factory=list)
    _daily_totals: dict = field(default_factory=lambda: defaultdict(lambda: {"tokens": 0, "cost": 0.0, "calls": 0}))
    _current_loop_tokens: int = 0
    
    def record_call(self, model: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        """Record an LLM API call."""
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)
        total_tokens = prompt_tokens + completion_tokens
        
        record = CallRecord(
            timestamp=time.time(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost=cost,
        )
        self._calls.append(record)
        self._current_loop_tokens += total_tokens
        
        # Update daily totals
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._daily_totals[today]["tokens"] += total_tokens
        self._daily_totals[today]["cost"] += cost
        self._daily_totals[today]["calls"] += 1
        
        # Keep only last 7 days of data
        if len(self._daily_totals) > 7:
            oldest = sorted(self._daily_totals.keys())[0]
            del self._daily_totals[oldest]
        
        logger.debug(
            f"LLM call: {model} | {prompt_tokens}+{completion_tokens} tokens | "
            f"${cost:.4f} | daily total: ${self._daily_totals[today]['cost']:.4f}"
        )
    
    def reset_loop_counter(self):
        """Reset the per-loop token counter (call at start of each ReAct loop)."""
        self._current_loop_tokens = 0
    
    def should_throttle(self) -> bool:
        """Check if daily budget has been exceeded."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_cost = self._daily_totals[today]["cost"]
        if daily_cost >= self.daily_budget_usd:
            logger.warning(f"Daily LLM budget exceeded: ${daily_cost:.2f} >= ${self.daily_budget_usd:.2f}")
            return True
        return False
    
    def loop_limit_reached(self) -> bool:
        """Check if current ReAct loop has exceeded token limit."""
        if self._current_loop_tokens >= self.loop_token_limit:
            logger.warning(
                f"ReAct loop token limit reached: {self._current_loop_tokens} >= {self.loop_token_limit}"
            )
            return True
        return False
    
    def get_daily_summary(self) -> dict:
        """Get today's usage summary."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        totals = self._daily_totals[today]
        return {
            "date": today,
            "total_calls": totals["calls"],
            "total_tokens": totals["tokens"],
            "estimated_cost_usd": round(totals["cost"], 4),
            "budget_remaining_usd": round(max(0, self.daily_budget_usd - totals["cost"]), 4),
            "budget_pct_used": round(min(100.0, totals["cost"] / self.daily_budget_usd * 100), 1) if self.daily_budget_usd > 0 else 0,
            "throttled": self.should_throttle(),
        }
    
    def format_summary(self) -> str:
        """Format daily summary for display."""
        s = self.get_daily_summary()
        budget_bar = "█" * int(s["budget_pct_used"] / 10) + "░" * (10 - int(s["budget_pct_used"] / 10))
        return (
            f"📊 **LLM Usage Today** ({s['date']})\n"
            f"├ Calls: {s['total_calls']}\n"
            f"├ Tokens: {s['total_tokens']:,}\n"
            f"├ Cost: ${s['estimated_cost_usd']:.4f}\n"
            f"├ Budget: [{budget_bar}] {s['budget_pct_used']}%\n"
            f"└ Remaining: ${s['budget_remaining_usd']:.4f}"
        )
    
    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost based on model pricing."""
        # Try exact match, then partial match, then default
        pricing = MODEL_PRICING.get("default")
        model_lower = model.lower()
        for key, price in MODEL_PRICING.items():
            if key in model_lower:
                pricing = price
                break
        
        prompt_cost = (prompt_tokens / 1_000_000) * pricing[0]
        completion_cost = (completion_tokens / 1_000_000) * pricing[1]
        return prompt_cost + completion_cost
