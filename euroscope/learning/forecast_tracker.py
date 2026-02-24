"""
Forecast Tracker — Active Learning Loop

Records forecasts (direction + target + confidence), resolves them
against actual outcomes, and adjusts skill weights so that the system
progressively trusts its best-performing analysis sources.

Flow:
    1. register_forecast(skill, direction, target, confidence)
    2. cron resolves open forecasts against live price
    3. skill weights are updated (Bayesian-style exponential smoothing)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Optional

from ..data.storage import Storage

logger = logging.getLogger("euroscope.learning.forecast_tracker")

# Default weights for analysis sources
DEFAULT_WEIGHTS = {
    "technical_analysis": 1.0,
    "multi_timeframe_confluence": 1.0,
    "correlation_monitor": 1.0,
    "session_context": 0.8,
    "fundamental_analysis": 0.9,
    "risk_assessment": 0.7,
    "llm_sentiment": 0.6,
}

# Learning rate: how fast weights adapt (0.05 = conservative, 0.2 = aggressive)
LEARNING_RATE = 0.10

# Minimum and maximum weight bounds
WEIGHT_MIN = 0.2
WEIGHT_MAX = 2.0


@dataclass
class Forecast:
    """A single directional forecast from the system."""
    id: str
    skill: str  # which skill produced this forecast
    direction: str  # "BUY" or "SELL"
    target_price: float
    entry_price: float
    confidence: float  # 0-100
    stop_price: Optional[float] = None
    timeframe: str = "H1"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: Optional[datetime] = None
    resolved: bool = False
    outcome: Optional[str] = None  # "hit_target", "hit_stop", "expired", "partial"
    actual_price: Optional[float] = None
    resolved_at: Optional[datetime] = None
    pnl_pips: Optional[float] = None


class ForecastTracker:
    """
    Active learning loop: registers forecasts, resolves them,
    and adjusts skill weights based on accuracy.
    """

    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()
        self._weights = dict(DEFAULT_WEIGHTS)
        self._forecasts: list[Forecast] = []
        self._next_id = 1
        self._load_weights()

    # ── Registration ───────────────────────────────────────────

    def register_forecast(
        self,
        skill: str,
        direction: str,
        entry_price: float,
        target_price: float,
        confidence: float = 50.0,
        stop_price: float = None,
        timeframe: str = "H1",
        ttl_hours: int = 24,
    ) -> Forecast:
        """
        Register a new forecast from a skill.

        Args:
            skill: Name of the skill that generated this forecast
            direction: "BUY" or "SELL"
            entry_price: Price at time of forecast
            target_price: Expected price target
            confidence: Confidence 0-100
            stop_price: Optional invalidation price
            timeframe: Timeframe context
            ttl_hours: Hours until forecast expires
        """
        now = datetime.now(UTC)
        forecast = Forecast(
            id=f"fc_{self._next_id:04d}",
            skill=skill,
            direction=direction.upper(),
            entry_price=entry_price,
            target_price=target_price,
            confidence=confidence,
            stop_price=stop_price,
            timeframe=timeframe,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        self._next_id += 1
        self._forecasts.append(forecast)
        logger.info(
            f"📝 Forecast {forecast.id}: {skill} → {direction} "
            f"target={target_price:.5f} conf={confidence:.0f}%"
        )
        return forecast

    # ── Resolution ─────────────────────────────────────────────

    def resolve_all(self, current_price: float) -> list[Forecast]:
        """
        Check all open forecasts against the current price.

        Returns list of newly resolved forecasts.
        """
        resolved = []
        now = datetime.now(UTC)

        for fc in self._forecasts:
            if fc.resolved:
                continue

            outcome = self._check_outcome(fc, current_price, now)
            if outcome:
                fc.resolved = True
                fc.outcome = outcome
                fc.actual_price = current_price
                fc.resolved_at = now
                fc.pnl_pips = self._calculate_pnl_pips(fc, current_price)

                # Update skill weight
                self._update_weight(fc)
                resolved.append(fc)
                
                # Push the lesson to Vector Memory
                try:
                    from ..brain.vector_memory import VectorMemory
                    vm = VectorMemory()
                    lesson_text = (
                        f"Resolved Forecast [{fc.id}]: The {fc.skill} analysis predicted {fc.direction} "
                        f"with target {fc.target_price}. Outcome: {outcome} ({fc.pnl_pips:+.1f} pips)."
                    )
                    # We wrap this in a synchronous check or run, because resolve_all is synchronous.
                    # To keep it simple, we'll just log it. The cron job will pick it up or we can
                    # make resolve_all async if needed. Since cron is async, we'll let cron handle the memory push.
                    # Wait, memory adding is async, we can't do it here easily since resolve_all is sync.
                    # We will append the text to be handled by the caller.
                    fc._lesson_text = lesson_text
                except Exception as e:
                    logger.debug(f"Could not prepare lesson for vector memory: {e}")

                logger.info(
                    f"✅ Forecast {fc.id} resolved: {outcome} "
                    f"({fc.pnl_pips:+.1f} pips, skill={fc.skill})"
                )

        return resolved

    def _check_outcome(
        self, fc: Forecast, price: float, now: datetime
    ) -> Optional[str]:
        """Determine if a forecast has been resolved."""
        is_buy = fc.direction == "BUY"

        # Check target hit
        if is_buy and price >= fc.target_price:
            return "hit_target"
        if not is_buy and price <= fc.target_price:
            return "hit_target"

        # Check stop hit
        if fc.stop_price:
            if is_buy and price <= fc.stop_price:
                return "hit_stop"
            if not is_buy and price >= fc.stop_price:
                return "hit_stop"

        # Check expiry
        if fc.expires_at and now >= fc.expires_at:
            # Partial success if moved in the right direction
            if is_buy and price > fc.entry_price:
                return "partial"
            if not is_buy and price < fc.entry_price:
                return "partial"
            return "expired"

        return None  # Still open

    def _calculate_pnl_pips(self, fc: Forecast, price: float) -> float:
        """Calculate P/L in pips (1 pip = 0.0001 for EUR/USD)."""
        diff = price - fc.entry_price
        if fc.direction == "SELL":
            diff = -diff
        return round(diff * 10_000, 1)

    # ── Weight Adjustment ──────────────────────────────────────

    def _update_weight(self, fc: Forecast):
        """
        Update skill weight using exponential moving average.

        hit_target → reward (+)
        hit_stop   → penalize (-)
        expired    → slight penalize
        partial    → neutral
        """
        skill = fc.skill
        current = self._weights.get(skill, 1.0)

        # Score the outcome
        scores = {
            "hit_target": +1.0,
            "partial": +0.2,
            "expired": -0.3,
            "hit_stop": -0.8,
        }
        score = scores.get(fc.outcome, 0)

        # Scale by confidence (high-confidence misses hurt more)
        confidence_factor = fc.confidence / 100.0
        adjustment = LEARNING_RATE * score * confidence_factor

        new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, current + adjustment))
        self._weights[skill] = round(new_weight, 4)

        if abs(adjustment) > 0.01:
            logger.info(
                f"⚖️ Weight update: {skill} {current:.3f} → {new_weight:.3f} "
                f"(outcome={fc.outcome}, adj={adjustment:+.4f})"
            )

        self._save_weights()

    # ── Queries ────────────────────────────────────────────────

    def get_weights(self) -> dict:
        """Get current skill weights."""
        return dict(self._weights)

    def get_weight(self, skill: str) -> float:
        """Get weight for a specific skill."""
        return self._weights.get(skill, 1.0)

    def get_open_forecasts(self) -> list[Forecast]:
        """Get all unresolved forecasts."""
        return [fc for fc in self._forecasts if not fc.resolved]

    def get_resolved_forecasts(self, limit: int = 50) -> list[Forecast]:
        """Get recently resolved forecasts."""
        resolved = [fc for fc in self._forecasts if fc.resolved]
        return sorted(resolved, key=lambda f: f.resolved_at or f.created_at, reverse=True)[:limit]

    def get_skill_accuracy(self, skill: str) -> dict:
        """Get accuracy stats for a specific skill."""
        resolved = [fc for fc in self._forecasts if fc.resolved and fc.skill == skill]
        if not resolved:
            return {"total": 0, "accuracy": 0, "avg_pnl": 0}

        hits = sum(1 for fc in resolved if fc.outcome in ("hit_target", "partial"))
        total_pnl = sum(fc.pnl_pips or 0 for fc in resolved)

        return {
            "total": len(resolved),
            "accuracy": round(hits / len(resolved) * 100, 1),
            "avg_pnl": round(total_pnl / len(resolved), 1),
            "weight": self._weights.get(skill, 1.0),
        }

    def get_scoreboard(self) -> dict:
        """Get performance scoreboard for all skills."""
        skills = set(fc.skill for fc in self._forecasts if fc.resolved)
        return {skill: self.get_skill_accuracy(skill) for skill in sorted(skills)}

    # ── Formatting ─────────────────────────────────────────────

    def format_scoreboard(self) -> str:
        """Format skill weights and accuracy for Telegram display."""
        board = self.get_scoreboard()
        if not board:
            return "📊 *Forecast Scoreboard*\n\nNo resolved forecasts yet."

        lines = ["📊 *Forecast Scoreboard*", ""]
        for skill, stats in board.items():
            w = self._weights.get(skill, 1.0)
            icon = "🟢" if stats["accuracy"] >= 60 else "🔴" if stats["accuracy"] < 40 else "🟡"
            lines.append(
                f"{icon} `{skill}`: {stats['accuracy']}% accuracy "
                f"({stats['total']} forecasts, {stats['avg_pnl']:+.1f}p avg)"
            )
            lines.append(f"   Weight: `{w:.2f}`")

        open_count = len(self.get_open_forecasts())
        lines.append(f"\n📌 {open_count} open forecast(s)")
        return "\n".join(lines)

    # ── Persistence ────────────────────────────────────────────

    def _save_weights(self):
        """Save weights to storage."""
        try:
            self.storage.save_json("forecast_weights", self._weights)
        except Exception as e:
            logger.warning(f"Could not save forecast weights: {e}")

    def _load_weights(self):
        """Load weights from storage."""
        try:
            saved = self.storage.load_json("forecast_weights")
            if saved and isinstance(saved, dict):
                self._weights.update(saved)
        except Exception as e:
            logger.debug(f"No saved forecast weights: {e}")
