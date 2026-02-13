"""
Pattern Tracker — Tracks success rates of detected chart patterns.

Records pattern detections and their outcomes, building a confidence
multiplier for each pattern/timeframe combination.
"""

import logging
from typing import Optional

from ..data.storage import Storage

logger = logging.getLogger("euroscope.learning.pattern_tracker")


class PatternTracker:
    """
    Tracks detected chart patterns and their success rates.

    Usage:
        tracker = PatternTracker()
        pid = tracker.record_detection("double_bottom", "H4", "BUY", 1.0850)
        # ... later, when pattern plays out ...
        tracker.resolve(pid, "BUY", 1.0900, True)
        rates = tracker.get_success_rates()
    """

    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()

    def record_detection(self, pattern_name: str, timeframe: str,
                         predicted_direction: str,
                         price_at_detection: float) -> int:
        """Record a newly detected pattern."""
        pid = self.storage.save_pattern_detection(
            pattern_name=pattern_name,
            timeframe=timeframe,
            predicted_direction=predicted_direction,
            price_at_detection=price_at_detection,
        )
        logger.info(f"Pattern #{pid}: {pattern_name} ({timeframe}) → {predicted_direction}")
        return pid

    def resolve(self, pattern_id: int, actual_outcome: str,
                price_at_resolution: float, is_success: bool):
        """Resolve a pattern detection with actual outcome."""
        self.storage.resolve_pattern(
            pattern_id, actual_outcome, price_at_resolution, is_success
        )
        icon = "✅" if is_success else "❌"
        logger.info(f"Pattern #{pattern_id} resolved: {icon} {actual_outcome}")

    def get_success_rates(self) -> dict:
        """Get success rates grouped by pattern + timeframe."""
        return self.storage.get_pattern_success_rates()

    def get_confidence_multiplier(self, pattern_name: str,
                                   timeframe: str) -> float:
        """
        Get a confidence multiplier for a pattern/timeframe combo.

        Returns:
            1.0 if no data, >1.0 for high-success patterns, <1.0 for poor ones
        """
        rates = self.get_success_rates()
        key = f"{pattern_name}_{timeframe}"
        entry = rates.get(key)

        if not entry or entry["total"] < 3:
            return 1.0  # Not enough data

        rate = entry["success_rate"]
        # Map 0-100% to 0.5-1.5 multiplier
        return round(0.5 + rate / 100.0, 2)

    def get_unresolved(self, limit: int = 50) -> list[dict]:
        """Get patterns waiting for resolution."""
        return self.storage.get_unresolved_patterns(limit)

    def format_report(self) -> str:
        """Generate a human-readable pattern performance report."""
        rates = self.get_success_rates()

        if not rates:
            return "📊 *Pattern Tracker*\n\nNo resolved patterns yet."

        lines = ["📊 *Pattern Success Rates*\n"]

        # Sort by success rate descending
        sorted_patterns = sorted(
            rates.values(), key=lambda x: x["success_rate"], reverse=True
        )

        for p in sorted_patterns:
            rate = p["success_rate"]
            icon = "🟢" if rate >= 60 else "🟡" if rate >= 40 else "🔴"
            lines.append(
                f"{icon} `{p['pattern']}` ({p['timeframe']}): "
                f"{rate}% ({p['successes']}/{p['total']})"
            )

        return "\n".join(lines)
