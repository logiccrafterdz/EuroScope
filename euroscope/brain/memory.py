"""
Self-Learning Memory

Tracks prediction accuracy over time and adjusts the agent's context
to learn from past mistakes.
"""

import json
import logging
from datetime import datetime, UTC
from typing import Optional

from ..data.storage import Storage

logger = logging.getLogger("euroscope.brain.memory")


class Memory:
    """Self-learning memory system for EuroScope."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def record_prediction(self, direction: str, confidence: float,
                          reasoning: str, target_price: float = None,
                          timeframe: str = "D1") -> int:
        """Record a new prediction for future accuracy tracking."""
        pred_id = self.storage.save_prediction(
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            target_price=target_price,
        )
        logger.info(f"Recorded prediction #{pred_id}: {direction} ({confidence}% confidence)")
        return pred_id

    def evaluate_prediction(self, pred_id: int, actual_direction: str, actual_price: float):
        """Evaluate a past prediction against actual outcome."""
        # Get the prediction
        preds = self.storage.get_unresolved_predictions()
        pred = next((p for p in preds if p["id"] == pred_id), None)
        if not pred:
            return

        # Calculate accuracy
        predicted = pred["direction"].upper()
        actual = actual_direction.upper()

        if predicted == actual:
            accuracy = 1.0
        elif predicted == "NEUTRAL":
            accuracy = 0.5
        else:
            accuracy = 0.0

        self.storage.resolve_prediction(pred_id, actual_direction, accuracy)
        logger.info(f"Prediction #{pred_id}: predicted={predicted}, actual={actual}, accuracy={accuracy}")

    def get_accuracy_report(self, days: int = 30) -> str:
        """Generate human-readable accuracy report."""
        stats = self.storage.get_accuracy_stats(days)

        if stats["total"] == 0:
            return "📊 *Prediction Accuracy*\n\nNo predictions tracked yet. Start using /forecast!"

        lines = [
            f"📊 *Prediction Accuracy (Last {days} Days)*\n",
            f"Total Predictions: {stats['total']}",
            f"Correct: {stats['correct']}",
            f"Accuracy: {stats['accuracy']}%\n",
        ]

        if stats.get("by_direction"):
            lines.append("*By Direction:*")
            for direction, data in stats["by_direction"].items():
                icon = "🟢" if direction.upper() == "BULLISH" else "🔴" if direction.upper() == "BEARISH" else "⚪"
                lines.append(f"  {icon} {direction}: {data['accuracy']}% ({data['correct']}/{data['total']})")

        return "\n".join(lines)

    def get_learning_context(self) -> str:
        """Generate context from past learnings for the AI prompt."""
        stats = self.storage.get_accuracy_stats(30)

        if stats["total"] < 3:
            return "No sufficient prediction history yet."

        lines = [f"Your prediction accuracy over last 30 days: {stats['accuracy']}% ({stats['total']} predictions)"]

        by_dir = stats.get("by_direction", {})
        for direction, data in by_dir.items():
            if data["accuracy"] < 50 and data["total"] >= 2:
                lines.append(f"⚠️ Your {direction} predictions are weak ({data['accuracy']}%). Be more cautious with {direction} calls.")
            elif data["accuracy"] >= 70 and data["total"] >= 3:
                lines.append(f"✅ Your {direction} predictions are strong ({data['accuracy']}%). Good confidence here.")

        # Load any stored insights
        insights = self.storage.get_memory("learning_insights")
        if insights:
            lines.append(f"\nPast insights: {insights}")

        return "\n".join(lines)

    def save_insight(self, insight: str):
        """Save a learning insight for future reference."""
        existing = self.storage.get_memory("learning_insights") or ""
        # Keep last 5 insights
        entries = existing.split("\n") if existing else []
        entries.append(f"[{datetime.now(UTC).strftime('%Y-%m-%d')}] {insight}")
        entries = entries[-5:]
        self.storage.set_memory("learning_insights", "\n".join(entries))

    def resolve_pending_predictions(self, current_price: float, min_move_pips: float = 5.0) -> dict:
        preds = self.storage.get_unresolved_predictions()
        resolved = 0
        skipped = 0
        for p in preds:
            entry = p.get("target_price")
            if not entry:
                skipped += 1
                continue
            move_pips = (current_price - entry) * 10000
            if abs(move_pips) < min_move_pips:
                continue
            direction = p.get("direction", "").upper()
            if direction == "BULLISH":
                actual = "BULLISH" if move_pips > 0 else "BEARISH"
            elif direction == "BEARISH":
                actual = "BEARISH" if move_pips < 0 else "BULLISH"
            else:
                actual = "NEUTRAL"
            self.evaluate_prediction(p["id"], actual, current_price)
            resolved += 1
        return {"resolved": resolved, "skipped": skipped}
